"""One experiment spanning public-input analysis and calibration modules."""
from dataclasses import dataclass
from pathlib import Path
import json
import os
import shlex
import signal
import subprocess
import sys
import time

from .storage import ROOT, output_lock, read_json, separate_output, source_identity, write_json

STAGES = ('study', 'design', 'counts', 'tails')
MODULES = dict(study='pipeline.study_runner', design='design_benchmark.driver',
               counts='paired_count_calibration.driver', tails='paired_tail_diagnostics.driver')


@dataclass
class WorkflowConfig:
    output: Path
    stages: tuple = STAGES
    profile: str = 'full'
    workers: int = 36
    data_work: Path | None = None
    raw_cache: tuple = ()
    python: str = sys.executable
    rscript: str = 'Rscript'
    r_library: tuple = ()
    python_package_path: tuple = ()

    def specification(self):
        return dict(stages=list(self.stages), profile=self.profile,
                    data_work=str(Path(self.data_work).resolve()) if self.data_work else None,
                    raw_cache=[str(Path(p).resolve()) for p in self.raw_cache],
                    python=str(self.python), rscript=str(self.rscript),
                    r_library=list(map(str, self.r_library)),
                    python_package_path=list(map(str, self.python_package_path)))

    def validate(self):
        if self.data_work is not None:
            self.data_work = Path(self.data_work).expanduser().resolve()
        self.raw_cache = tuple(Path(p).expanduser().resolve() for p in self.raw_cache)
        self.r_library = tuple(str(Path(p).expanduser().resolve()) for p in self.r_library)
        self.python_package_path = tuple(str(Path(p).expanduser().resolve()) for p in self.python_package_path)
        if not self.stages or len(set(self.stages)) != len(self.stages) or any(s not in STAGES for s in self.stages):
            raise ValueError('Choose distinct workflow stages: ' + ', '.join(STAGES))
        self.stages = tuple(s for s in STAGES if s in self.stages)
        if isinstance(self.workers, bool) or not isinstance(self.workers, int) or self.workers < 1:
            raise ValueError('workers must be a positive integer')
        if self.profile not in ('full', 'pilot', 'smoke'):
            raise ValueError('profile must be full, pilot or smoke')
        if 'study' in self.stages and self.profile != 'full':
            raise ValueError('Public-input study has no reduced profile. Use --stages design/counts/tails for a pilot.')
        if 'design' in self.stages and 'study' not in self.stages and self.data_work is None:
            raise ValueError('Design stage requires --data-work or the study stage in this workflow')
        if 'study' in self.stages and self.data_work is not None:
            raise ValueError('A full study uses its own newly prepared inputs, not --data-work')
        self.output = separate_output(self.output, self.data_work, *self.raw_cache)
        return self


def stage_command(config, stage, *, resume=False):
    output = config.output / stage
    command = [str(config.python), '-B', '-m', MODULES[stage], '--output', str(output),
               '--workers', str(config.workers), '--rscript', str(config.rscript)]
    if stage == 'study':
        if config.r_library:
            command += ['--r-library', str(config.r_library[0])]
        for cache in config.raw_cache:
            command += ['--raw-cache', str(cache)]
        marker = output / 'fresh_run.json'
    else:
        profile = 'pilot' if stage == 'design' and config.profile == 'smoke' else config.profile
        command += ['--profile', profile]
        for library in config.r_library:
            command += ['--r-library', str(library)]
        if stage == 'design':
            source = config.data_work or config.output / 'study/core'
            command += ['--data-work', str(source)]
        marker = output / 'protocol.json'
    if resume and marker.is_file():
        command.append('--resume')
    if config.python_package_path:
        bootstrap = ('import sys,runpy,json; sys.path.extend(json.loads(sys.argv.pop(1))); '
                     'module=sys.argv.pop(1); sys.argv[0]=module; runpy.run_module(module,run_name="__main__")')
        command = [str(config.python), '-B', '-c', bootstrap,
                   json.dumps(list(config.python_package_path)), MODULES[stage], *command[4:]]
    return command


def plan(config):
    config.validate()
    return [dict(stage=s, command=stage_command(config, s)) for s in config.stages]


def run_stage(command, env, log):
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open('a', encoding='utf-8') as stream:
        process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True, encoding='utf-8',
                                   errors='replace', start_new_session=os.name == 'posix')
        try:
            for line in process.stdout:
                stream.write(line)
                stream.flush()
                print(line, end='', flush=True)
            result = process.wait()
            if result:
                raise RuntimeError(f'Stage exited with code {result}; see {log}')
        except BaseException:
            if process.poll() is None:
                if os.name == 'posix':
                    os.killpg(process.pid, signal.SIGTERM)
                else:
                    process.terminate()
                try:
                    process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    if os.name == 'posix':
                        os.killpg(process.pid, signal.SIGKILL)
                    else:
                        process.kill()
                    process.wait()
            raise


def publish_results(config, env):
    code = ('import sys,json; sys.path.extend(json.loads(sys.argv[1])); '
            'from adjscope_tx.reports import finalize_workflow; '
            'finalize_workflow(sys.argv[2], sys.executable)')
    run_stage([str(config.python), '-B', '-c', code,
               json.dumps(list(config.python_package_path)), str(config.output)],
              env, config.output / 'logs' / 'publication.log')


def run_workflow(config, *, resume=False, executor=run_stage):
    """Run all requested stages; stage receipts control dataset-level reuse."""
    config.validate()
    output = config.output
    marker = output / 'workflow.json'
    digest = source_identity()
    if resume and not marker.is_file():
        raise ValueError('Resume requires workflow.json from this framework. Keep older experiments with their original source.')
    if not resume and output.exists() and any(output.iterdir()):
        raise ValueError('New workflow requires an empty output')
    with output_lock(output):
        if resume:
            record = read_json(marker)
            if record['output'] != str(output) or record['source_sha256'] != digest:
                raise ValueError('Workflow source or output changed; use a new output')
            if record['specification'] != config.specification():
                raise ValueError('Scientific/environment settings changed; only workers may change on resume')
        else:
            if marker.exists() or any(p.name != '.framework.lock' for p in output.iterdir()):
                raise ValueError('Output is no longer empty')
            record = dict(format=1, output=str(output), source_sha256=digest,
                          specification=config.specification(), started=time.time(), stages={})
        env = os.environ.copy()
        env.update({k: '1' for k in ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS',
                                    'NUMEXPR_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS')})
        env['PYTHONPATH'] = str(ROOT) + os.pathsep + env.get('PYTHONPATH', '')
        env['PYTHONIOENCODING'] = 'utf-8'
        if config.r_library:
            env['R_LIBS'] = os.pathsep.join(map(str, config.r_library))
        if config.python_package_path:
            env['PAPER1_OPTIONAL_PACKAGE_PATHS'] = json.dumps(list(config.python_package_path))
        record.update(status='RUNNING', workers=config.workers, pid=os.getpid())
        write_json(marker, record)
        try:
            for stage in config.stages:
                if source_identity() != digest:
                    raise ValueError('Source changed during execution')
                command = stage_command(config, stage, resume=resume)
                record['stages'][stage] = dict(status='RUNNING', started=time.time())
                write_json(marker, record)
                print('STAGE', stage, shlex.join(command), flush=True)
                executor(command, env, output / 'logs' / (stage + '.log'))
                if source_identity() != digest:
                    raise ValueError('Source changed during execution')
                record['stages'][stage].update(status='COMPLETE', finished=time.time())
                write_json(marker, record)
            record.update(status='FINALIZING')
            write_json(marker, record)
            print('PUBLICATION manuscript CSVs and figures', flush=True)
            publish_results(config, env)
            if source_identity() != digest:
                raise ValueError('Source changed during publication export')
            record.update(status='COMPLETE', finished=time.time())
            record.pop('error', None)
            write_json(marker, record)
        except BaseException as exc:
            record.update(status='INTERRUPTED' if isinstance(exc, KeyboardInterrupt) else 'FAILED',
                          error=str(exc), finished=time.time())
            write_json(marker, record)
            raise
    return output


def status(output, *, details=True):
    output = Path(output).expanduser().resolve()
    record = read_json(output / 'workflow.json')
    print('WORKFLOW', record['status'], output)
    for stage in record['specification']['stages']:
        print(stage, record['stages'].get(stage, {}).get('status', 'NOT_STARTED'))
        folder = output / stage
        if details and (folder / ('fresh_run.json' if stage == 'study' else 'protocol.json')).is_file():
            spec = record['specification']
            command = [spec['python'], '-B', '-m', MODULES[stage], '--status', '--output', str(folder)]
            env = os.environ.copy()
            env['PYTHONPATH'] = os.pathsep.join([str(ROOT), *spec.get('python_package_path', []), env.get('PYTHONPATH','')])
            if spec.get('r_library'):
                env['R_LIBS'] = os.pathsep.join(spec['r_library'])
            subprocess.run(command, cwd=ROOT, env=env, check=True)
    return record
