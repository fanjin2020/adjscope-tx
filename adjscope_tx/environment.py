#!/usr/bin/env python3
"""Select existing compatible environments and start a new public-input reproduction."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import site
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def distinct_existing(paths, *, resolve_symlinks=True):
    result = []
    for path in paths:
        p = Path(path).expanduser()
        p = p.resolve() if resolve_symlinks else p.absolute()
        if p.exists() and p not in result:
            result.append(p)
    return result


def python_candidates(explicit=None):
    # A venv's Python symlink must be invoked in place to retain its environment.
    if explicit:
        return distinct_existing([explicit], resolve_symlinks=False)
    values = [sys.executable]
    for base in (ROOT, ROOT.parent / 'paper1-from-publicV1', ROOT.parent / 'paper1_public_evidence'):
        for layout in (base, base / 'paper1-from-public'):
            for name in ('.raw-reproduction-venv', '.venv', '.benchmark-python'):
                values.extend([layout / name / 'bin/python', layout / name / 'Scripts/python.exe'])
    base = ROOT.parent / 'paper1_public_evidence'
    if base.is_dir():
        for pattern in ('paper1*source*/.venv/bin/python', 'paper3*source*/.venv/bin/python'):
            values.extend(sorted(base.glob(pattern)))
    return distinct_existing(values, resolve_symlinks=False)


def optional_package_paths(explicit=()):
    if explicit:
        return distinct_existing(explicit)
    values = list(site.getsitepackages())
    related = ROOT.parent / 'paper1_public_evidence'
    if related.is_dir():
        for pattern in ('paper1*source*/.venv/lib/python3.12/site-packages',
                        'paper3*source*/.venv/lib/python3.12/site-packages'):
            values.extend(sorted(related.glob(pattern)))
    return distinct_existing(values)


def clean_python_environment():
    env = {k: v for k, v in os.environ.items()
           if not k.upper().startswith(('PYTHON', 'PIP_'))}
    env.update(PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1',
               PYTHONIOENCODING='utf-8', PIP_CONFIG_FILE=os.devnull)
    return env


def select_python(explicit=None, supplementary=False, package_paths=(), isolated=False):
    code = ('import sys,json; sys.path.insert(0,sys.argv[1]); '
            'sys.path.extend(json.loads(sys.argv[2])); '
            'from pipeline.environment import python_snapshot; '
            'record=python_snapshot(); ')
    if supplementary:
        code += ('from pipeline.supplementary.driver import check_python,GROUPS; '
                 'record["supplementary_packages"]=check_python(GROUPS); ')
    code += 'print("PAPER1_PYTHON\\t"+json.dumps(record))'
    for exe in python_candidates(explicit):
        try:
            command = [str(exe), *(['-I'] if isolated else []), '-B', '-c', code,
                       str(ROOT), json.dumps(list(map(str, package_paths)))]
            result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8',
                                    errors='replace', timeout=180,
                                    env=clean_python_environment() if isolated else None)
        except (OSError, subprocess.TimeoutExpired) as exc:
            print('PYTHON NOT SELECTED', exe, str(exc), flush=True)
            continue
        lines = [line for line in result.stdout.splitlines() if line.startswith('PAPER1_PYTHON\t')]
        if result.returncode == 0 and len(lines) == 1:
            try:
                return exe, json.loads(lines[0].split('\t', 1)[1])
            except ValueError:
                print('PYTHON NOT SELECTED', exe, 'Invalid probe record', flush=True)
                continue
        print('PYTHON NOT SELECTED', exe, result.stderr[-2000:], flush=True)
    raise RuntimeError('No compatible existing Python found. No packages were downloaded. '
                       'Use --python /path/to/an/existing/python matching requirements.txt.')


def setup_python(output, check_only=False):
    """Explicitly provision one isolated runtime; a validated runtime is never repaired in place."""
    from .storage import output_lock, read_json, separate_output, sha256, write_json
    from .workflow import run_stage

    if sys.version_info[:2] != (3, 12):
        raise ValueError('Run setup-python with an existing Python 3.12 interpreter.')
    if Path(output).expanduser().is_symlink():
        raise ValueError('The isolated runtime output cannot be a symbolic link.')
    output = separate_output(output, ROOT)
    requirements = ('requirements.txt', 'requirements-supplementary.txt')
    signature = dict(format=1, purpose='adjscope_tx_isolated_python',
                     requirements={name: sha256(ROOT / name) for name in requirements})
    owner, ready = output / 'setup.json', output / 'ready.json'
    if check_only and not ready.is_file():
        raise ValueError('No validated isolated runtime. Run setup-python without --check-only first.')
    if output.exists() and not owner.is_file() and any(output.iterdir()):
        raise ValueError('Setup output is not an owned runtime; choose a new empty directory: ' + str(output))
    venv = output / 'environment'
    exe = venv / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    env = clean_python_environment()

    def validate_prefix():
        probe = 'import json,sys; print(json.dumps([sys.prefix,sys.base_prefix]))'
        result = subprocess.run([str(exe), '-I', '-c', probe], check=True,
                                capture_output=True, text=True, env=env, timeout=60)
        prefix, base = map(Path, json.loads(result.stdout))
        if prefix.resolve() != venv.resolve() or prefix.resolve() == base.resolve():
            raise ValueError('Python is not isolated in the requested runtime; no packages were installed.')

    with output_lock(output):
        if owner.exists():
            if read_json(owner) != signature:
                raise ValueError('Runtime requirements changed. Choose a new setup output; the existing runtime is unchanged.')
        else:
            if any(p.name != '.framework.lock' for p in output.iterdir()):
                raise ValueError('Setup output is no longer empty.')
            write_json(owner, signature)
        if venv.is_symlink():
            raise ValueError('The runtime environment cannot be a symbolic link.')
        if ready.exists():
            validate_prefix()
            _, current = select_python(str(exe), supplementary=True, isolated=True)
            saved = read_json(ready)
            if saved.get('requirements') != signature['requirements'] or any(
                saved['python'].get(k) != current.get(k)
                for k in ('python', 'packages', 'supplementary_packages')
            ):
                raise ValueError('Validated runtime changed. Choose a new setup output; no packages were modified.')
            print('REUSE ISOLATED PYTHON', exe, flush=True)
            return exe

        if check_only:
            raise ValueError('Runtime is not ready; --check-only never installs packages.')

        for name in requirements:
            target = output / name
            if target.exists():
                if sha256(target) != signature['requirements'][name]:
                    raise ValueError('Saved setup requirements changed: ' + str(target))
            else:
                target.write_bytes((ROOT / name).read_bytes())
        log = output / 'install.log'
        print('ISOLATED PYTHON SETUP', output, '\nINSTALL LOG', log, flush=True)
        print('Only this new runtime is installed. Existing Python and R environments are unchanged.', flush=True)
        run_stage([sys.executable, '-I', '-m', 'venv', str(venv)], env, log)
        validate_prefix()
        run_stage([str(exe), '-I', '-m', 'pip', '--disable-pip-version-check', 'install',
                   '--no-input', '--prefer-binary', '-r', str(output / requirements[1])], env, log)
        run_stage([str(exe), '-I', '-m', 'pip', 'check'], env, log)
        _, record = select_python(str(exe), supplementary=True, isolated=True)
        if any(sha256(ROOT / name) != signature['requirements'][name] for name in requirements):
            raise ValueError('Source requirements changed during setup; runtime was not marked ready.')
        write_json(ready, dict(executable=str(exe), requirements=signature['requirements'], python=record))
        print('READY ISOLATED PYTHON', exe, flush=True)
        return exe


def library_candidates(explicit=()):
    if explicit:
        return distinct_existing(explicit)
    values = list(explicit)
    # This is a library search only. No results or prepared data enter the analysis.
    related = ROOT.parent / 'paper1_public_evidence'
    values += [related / 'paper1_two_analyses/R_library', ROOT / 'R_library']
    for base in (ROOT.parent, related):
        if base.is_dir():
            for child in sorted(base.iterdir()):
                if child.is_dir() and child.name.startswith('paper1'):
                    values += [child / 'R_library', child / 'runtime/R_library']
    for name in ('R_LIBS', 'R_LIBS_USER', 'PAPER1_R_LIBRARIES'):
        values += [x for x in os.environ.get(name, '').split(os.pathsep) if x]
    return distinct_existing(values)


def select_r(executable=None, explicit=()):
    from pipeline.environment import r_snapshot
    exe = executable or shutil.which('Rscript')
    if not exe:
        raise RuntimeError('Rscript not found. Activate your existing paper1 environment or use --rscript.')
    libraries = library_candidates(explicit)
    record = r_snapshot(exe, libraries)
    return str(exe), libraries, record






