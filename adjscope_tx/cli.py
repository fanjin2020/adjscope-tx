"""Public commands for analysis, diagnostics, reporting and figures."""
import argparse
import csv
import json
from pathlib import Path
import shlex
import os
import subprocess
import sys

from . import __version__
from .storage import ROOT, read_json, separate_output, write_json, sha256


def parser():
    p = argparse.ArgumentParser(prog='adjscope-tx', description='AdjScope-Tx reproducible analysis framework')
    p.add_argument('--version', action='version', version=__version__)
    commands = p.add_subparsers(dest='command', required=True)
    setup = commands.add_parser('setup-python', help='Explicitly install dependencies in an isolated Python 3.12 runtime')
    setup.add_argument('--output', type=Path, required=True)
    setup.add_argument('--check-only', action='store_true', help='Validate an existing isolated runtime without installing')
    run = commands.add_parser('run', help='Run or resume the computational study')
    run.add_argument('--output', type=Path, required=True)
    run.add_argument('--workers', type=int, default=36)
    run.add_argument('--stages', nargs='+', choices=('study', 'design', 'counts', 'tails'))
    run.add_argument('--profile', choices=('full', 'pilot', 'smoke'))
    run.add_argument('--data-work', type=Path)
    run.add_argument('--raw-cache', type=Path, action='append')
    run.add_argument('--python')
    run.add_argument('--rscript')
    run.add_argument('--r-library', action='append')
    run.add_argument('--python-package-path', action='append')
    run.add_argument('--resume', action='store_true')
    run.add_argument('--plan', action='store_true', help='Print the execution graph without downloads or fits')
    run.add_argument('--check-env', action='store_true', help='Check installed software only')
    status = commands.add_parser('status', help='Show workflow and verified batch progress')
    status.add_argument('--output', type=Path, required=True)
    status.add_argument('--brief', action='store_true')
    finalize = commands.add_parser('finalize', help='Finish figures from verified computed CSVs; never refit models')
    finalize.add_argument('--output', type=Path, required=True)
    finalize.add_argument('--python')
    finalize.add_argument('--analysis-source-manifest', type=Path,
                          help='Original source-file hashes for a legacy run, verified against its recorded source identity')
    report = commands.add_parser('report', help='Export compact final results without fitting')
    report.add_argument('--kind', choices=('workflow', 'publication'), default='workflow')
    report.add_argument('--source', type=Path)
    for stage in ('study','design','counts','tails'):
        report.add_argument('--'+stage, type=Path, help='Completed '+stage+' results directory')
    report.add_argument('--rscript', default='Rscript', help='Only needed for a missing saved Gaussian-geometry summary')
    report.add_argument('--output', type=Path, required=True)
    figures = commands.add_parser('figures', help='Draw manuscript figures from an exported CSV bundle')
    figures.add_argument('--layout', choices=('archive','cmpb','cmpb-supplement'), default='archive',
                         help='Archive numbering (default), the six CMPB main figures, or twenty supplementary figures')
    figures.add_argument('--source', type=Path, required=True)
    figures.add_argument('--output', type=Path, required=True)
    figures.add_argument('--python')
    figures.add_argument('--figures', nargs='+')
    figures.add_argument('--tiff', action='store_true')
    figures.add_argument('--editable', action='store_true', help='Also export SVG and PNG copies')
    figures.add_argument('--check-env', action='store_true')
    commands.add_parser('verify', help='Verify supplied publication data and figure sources')
    limma = commands.add_parser('check-limma', help='Independently verify the unmoderated paired coefficient difference and SE (S11)')
    limma.add_argument('--rscript', help='Existing Rscript executable (default: on PATH)')
    limma.add_argument('--r-library', action='append', default=[], help='Existing R library; may be repeated')
    limma.add_argument('--output', type=Path, help='Optional new JSON receipt; defaults to stdout only')
    limma.add_argument('--smoke', action='store_true', help='Use local versions; cannot report a locked pass')
    commands.add_parser('test', help='Run numerical and workflow regression tests; no research downloads')
    design = commands.add_parser('design', help='Compute design diagnostics from sample metadata')
    design.add_argument('--metadata', type=Path, required=True)
    design.add_argument('--exposure', required=True)
    design.add_argument('--group', required=True)
    design.add_argument('--covariates', nargs='*', default=[])
    design.add_argument('--output', type=Path, required=True)
    compare = commands.add_parser('compare', help='Compare nested models on normalized expression')
    compare.add_argument('--response', type=Path, required=True)
    compare.add_argument('--baseline', type=Path, required=True)
    compare.add_argument('--adjusted', type=Path, required=True)
    compare.add_argument('--weights', type=Path)
    compare.add_argument('--target', required=True, help='The same named column in both design CSVs')
    compare.add_argument('--variance', choices=('model', 'hc3'), default='model')
    compare.add_argument('--alpha', type=float, default=.05)
    compare.add_argument('--output', type=Path, required=True)
    return p


def configure(args):
    from .workflow import WorkflowConfig
    names = ('stages', 'profile', 'data_work', 'raw_cache', 'python', 'rscript', 'r_library', 'python_package_path')
    defaults = dict(stages=('study', 'design', 'counts', 'tails'), profile='full', data_work=None,
                    raw_cache=(), python=sys.executable, rscript='Rscript', r_library=(), python_package_path=())
    if args.resume:
        marker = args.output.expanduser().resolve() / 'workflow.json'
        if not marker.is_file():
            raise ValueError('No workflow.json. Use the actual framework output directory; older experiments retain their original runner.')
        defaults = read_json(marker)['specification']
    values = {name: getattr(args, name) if getattr(args, name) is not None else defaults[name] for name in names}
    if values['data_work']:
        values['data_work'] = Path(values['data_work'])
    return WorkflowConfig(output=args.output, workers=args.workers, **values).validate()


def execute_run(args):
    from .workflow import plan, run_workflow
    config = configure(args)
    from pipeline.configuration import load_config
    load_config(ROOT / 'config.json', config.workers)
    if 'study' in config.stages:
        from pipeline.coverage import require_complete
        require_complete()
    if args.plan:
        for stage in plan(config):
            print(stage['stage'] + ': ' + shlex.join(stage['command']))
        print('publication: computed CSV bundle -> manuscript figures -> completion checks')
        return 0
    if not args.check_env and sys.platform != 'linux':
        raise ValueError('Research reproduction requires Linux. Use design/compare, verify, figures and test on Windows.')
    from . import environment
    # A fresh run searches existing environments; resume retains its recorded interpreter.
    requested_python = config.python if args.resume else args.python
    python, py_record = environment.select_python(requested_python, supplementary='study' in config.stages,
                                                 package_paths=config.python_package_path)
    rscript, libraries, r_record = environment.select_r(config.rscript, config.r_library)
    config.python = str(python)
    config.rscript = rscript
    config.r_library = tuple(map(str, libraries))
    if args.check_env:
        print(json.dumps(dict(python=py_record, R=r_record), indent=2))
        return 0
    print('PYTHON', config.python, flush=True)
    print('OUTPUT', config.output, '\nNO PACKAGE INSTALLS; VERIFIED RESUME', flush=True)
    print('RESUME', shlex.join(['python', 'run.py', 'run', '--resume', '--output',
                               str(config.output), '--workers', str(config.workers)]), flush=True)
    run_workflow(config, resume=args.resume)
    print('COMPLETE', config.output / 'results' / 'manifest.csv')
    print('FIGURES', config.output / 'figures')
    return 0


def run_diagnostic(args):
    from .diagnostics import diagnose_design, compare_models, read_numeric_csv
    import numpy as np
    files = [args.metadata] if args.command == 'design' else [args.response, args.baseline, args.adjusted]
    if args.command == 'compare' and args.weights:
        files.append(args.weights)
    output = separate_output(args.output, *files)
    if output.exists():
        raise ValueError('Diagnostic output must be new')
    inputs = {str(p.resolve()): sha256(p) for p in files}
    if args.command == 'design':
        with args.metadata.open(encoding='utf-8-sig', newline='') as stream:
            reader = csv.DictReader(stream)
            required = ['sample_id', args.exposure, args.group, *args.covariates]
            if len(reader.fieldnames or []) != len(set(reader.fieldnames or [])) or not set(required).issubset(reader.fieldnames or []):
                raise ValueError('Metadata must contain unique column names and ' + ', '.join(required))
            rows = list(reader)
        ids = [r['sample_id'] for r in rows]
        if not ids or len(ids) != len(set(ids)) or any(not i.strip() for i in ids):
            raise ValueError('Sample IDs must be nonempty and unique')
        covariates = np.asarray([[float(r[n]) for n in args.covariates] for r in rows])
        result = diagnose_design([float(r[args.exposure]) for r in rows], [r[args.group] for r in rows], covariates)
    else:
        ids, genes, y = read_numeric_csv(args.response)
        id0, names0, x0 = read_numeric_csv(args.baseline)
        id1, names1, x1 = read_numeric_csv(args.adjusted)
        if ids != id0 or ids != id1:
            raise ValueError('Sample IDs and order must match across all input CSVs')
        if args.target not in names0 or args.target not in names1 or names0.index(args.target) != names1.index(args.target):
            raise ValueError('Target column must have the same name and position in both designs')
        weights = None
        if args.weights:
            wi, wn, w = read_numeric_csv(args.weights)
            if wi != ids or len(wn) != 1:
                raise ValueError('Weights require matching sample IDs and exactly one numeric column')
            weights = w[:, 0]
        result = compare_models(y, x0, x1, weights=weights, target=names0.index(args.target),
                                variance=args.variance, alpha=args.alpha, gene_ids=genes)
    if any(sha256(p) != digest for p, digest in inputs.items()):
        raise ValueError('Input changed during analysis')
    output.mkdir(parents=True)
    if args.command == 'compare':
        with (output / 'genes.csv').open('w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(result['genes'][0]))
            writer.writeheader()
            writer.writerows(result['genes'])
        result = result['summary']
    write_json(output / 'summary.json', result)
    write_json(output / 'inputs.json', dict(command=args.command, sha256=inputs))
    print('RESULTS', output)
    return 0


def main(argv=None):
    args = parser().parse_args(argv)
    if args.command == 'run':
        return execute_run(args)
    if args.command == 'setup-python':
        from .environment import setup_python
        setup_python(args.output, check_only=args.check_only)
        return 0
    if args.command == 'status':
        from .workflow import status
        status(args.output, details=not args.brief)
    elif args.command == 'finalize':
        from .reports import finish_existing_workflow
        finish_existing_workflow(args.output, python=args.python,
                                 analysis_source_manifest=args.analysis_source_manifest)
    elif args.command in ('design', 'compare'):
        return run_diagnostic(args)
    elif args.command == 'verify':
        from .verification import main as verify
        verify()
    elif args.command == 'check-limma':
        from validation.paired_limma import run as check_limma
        return check_limma(args)
    elif args.command == 'figures':
        if args.layout in ('cmpb', 'cmpb-supplement'):
            if args.figures or args.editable or args.tiff:
                raise ValueError('The CMPB layouts export complete checked sets; --figures, --editable and --tiff are archive-only.')
            module = 'supplement' if args.layout == 'cmpb-supplement' else 'redraw_figures'
            cmd = [args.python or sys.executable, '-B', '-m', 'artwork.cmpb.' + module,
                   '--source', str(args.source.resolve()), '--out', str(args.output.resolve())]
            if args.check_env:
                cmd.append('--check-env')
            return subprocess.run(cmd, cwd=ROOT).returncode
        from .plotting import main as figures
        options = ['--output', str(args.output), '--source', str(args.source)]
        if args.python:
            options += ['--python', args.python]
        if args.figures:
            options += ['--figures', *args.figures]
        if args.tiff:
            options += ['--tiff']
        if args.editable:
            options += ['--editable']
        if args.check_env:
            options += ['--check-env']
        return figures(options)
    elif args.command == 'report':
        from .reports import export_publication, export_workflow, export_computed
        sources = {s:getattr(args,s) for s in ('study','design','counts','tails') if getattr(args,s) is not None}
        if args.kind == 'publication':
            if args.source or sources:
                raise ValueError('Publication replay cannot be mixed with computed results')
            export_publication(args.output)
        elif args.source:
            if sources:
                raise ValueError('Use --source or explicit stage directories, not both')
            export_workflow(args.source, args.output)
        else:
            if not sources:
                raise ValueError('Supply --source RUN or completed stage directories')
            export_computed(sources, args.output, args.rscript)
        print('RESULTS', args.output)
    elif args.command == 'test':
        success = True
        env = os.environ.copy()
        env['PYTHONPATH'] = str(ROOT) + os.pathsep + env.get('PYTHONPATH', '')
        for name in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
            env[name] = '1'
        for folder in ('tests', 'design_benchmark/tests', 'paired_count_calibration/tests', 'paired_tail_diagnostics/tests'):
            result = subprocess.run([sys.executable, '-B', '-m', 'unittest', 'discover',
                                     '-s', str(ROOT / folder), '-v'], cwd=ROOT, env=env)
            success = result.returncode == 0 and success
        return 0 if success else 1
    return 0


def entrypoint():
    try:
        return main()
    except KeyboardInterrupt:
        print('Interrupted; completed receipts retained. Resume the same output.', file=sys.stderr)
        return 130
    except (ValueError, RuntimeError, OSError, KeyError, subprocess.CalledProcessError) as exc:
        print('STOP:', exc, file=sys.stderr)
        return 2
