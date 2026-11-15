"""Render publication figures using an existing Python environment."""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).absolute().parents[1]
from .publication import SCHEMA
FIGURES = SCHEMA['figures']
CHECK = r'''
import importlib
import json
import os
import re
import sys

sys.path.extend(json.loads(os.environ.get('PAPER1_OPTIONAL_PACKAGE_PATHS', '[]')))
if sys.version_info < (3, 10):
    raise RuntimeError('Python 3.10 or later is required')
versions = {}
for name in ['numpy', 'pandas', 'matplotlib']:
    module = importlib.import_module(name)
    versions[name] = module.__version__
for name, lower in [('numpy', (1, 26)), ('pandas', (2, 2))]:
    version = tuple(map(int, re.match(r'^(\d+)\.(\d+)', versions[name]).groups()))
    if not lower <= version < (3, 0):
        raise RuntimeError(name + ': incompatible version ' + versions[name])
if versions['matplotlib'] != '3.10.1':
    raise RuntimeError('matplotlib: expected 3.10.1, found ' + versions['matplotlib'])
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot
from matplotlib import font_manager
try:
    font = font_manager.findfont('Arial', fallback_to_default=False)
    font_name = 'Arial'
except ValueError:
    font = font_manager.findfont('DejaVu Sans', fallback_to_default=False)
    font_name = 'DejaVu Sans'
print(json.dumps(dict(python=sys.version.split()[0], packages=versions,
                     font=font_name, font_file=font)))
'''


def candidates(root, explicit=None):
    if explicit:
        values = [explicit]
    else:
        values = [sys.executable, shutil.which('python3'), shutil.which('python')]
        if os.environ.get('CONDA_PREFIX'):
            values.append(Path(os.environ['CONDA_PREFIX']) / ('python.exe' if os.name == 'nt' else 'bin/python'))
    seen = set()
    for value in values:
        if not value:
            continue
        path = Path(shutil.which(str(value)) or str(value)).absolute()
        # Keep the virtual-environment invocation path, including symlinks.
        if path.is_file() and str(path) not in seen:
            seen.add(str(path))
            yield path


def select_python(root, explicit, env):
    for exe in candidates(root, explicit):
        try:
            result = subprocess.run([str(exe), '-c', CHECK], env=env,
                                    capture_output=True, text=True, timeout=90)
            if result.returncode == 0:
                return exe, json.loads(result.stdout)
            lines = (result.stderr or result.stdout).strip().splitlines()
            reason = lines[-1] if lines else 'environment check failed'
        except (OSError, subprocess.TimeoutExpired, ValueError) as error:
            reason = str(error)
        print('NOT SELECTED', exe, reason, flush=True)
    raise RuntimeError('No compatible existing plotting environment found. '
                       'No packages were downloaded. Use --python /path/to/existing/python.')


def create_output(root, requested):
    if requested:
        from .storage import separate_output
        output = separate_output(requested)
        if output.exists():
            raise RuntimeError('Output already exists; choose a new directory: ' + str(output))
        output.mkdir(parents=True)
        return output
    prefix = 'p1_fig_' + datetime.now().strftime('%Y%m%d_%H%M%S') + '_'
    return Path(tempfile.mkdtemp(prefix=prefix, dir=root.parent))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-root', type=Path, default=ROOT)
    parser.add_argument('--python', default=os.environ.get('PAPER1_PYTHON'))
    parser.add_argument('--output', type=Path)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--figures', nargs='+', choices=FIGURES)
    parser.add_argument('--tiff', action='store_true')
    parser.add_argument('--editable', action='store_true')
    parser.add_argument('--check-env', action='store_true')
    args = parser.parse_args(argv)
    root = args.project_root.expanduser().absolute()
    from .publication import Bundle
    bundle = Bundle(args.source).verify()
    selected = args.figures or bundle.figures()
    if not selected or set(selected) - set(bundle.figures()):
        raise ValueError('Requested figures lack computed inputs in the CSV bundle')
    package = root / 'publication_figures'
    required = [package / 'make_figures.py']
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise RuntimeError('Upload the complete publication_figures directory. Missing: '
                           + ', '.join(missing))
    env = os.environ.copy()
    env['PYTHONPATH'] = str(root) + os.pathsep + env.get('PYTHONPATH','')
    env.update(OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1',
               NUMEXPR_NUM_THREADS='1', MPLBACKEND='Agg', PYTHONIOENCODING='utf-8')
    print('PACKAGE INSTALLS DISABLED; NO STUDY DOWNLOADS; NO MODEL FITTING', flush=True)
    exe, snapshot = select_python(root, args.python, env)
    print('PYTHON', exe, flush=True)
    print('PACKAGES', json.dumps(snapshot['packages']), flush=True)
    print('FONT', snapshot['font'], flush=True)
    if snapshot['font'] != 'Arial':
        print('NOTE: Arial is unavailable. DejaVu Sans changes text appearance and layout; '
              'inspect the exported figures.', flush=True)
    if args.check_env:
        return 0
    from .storage import separate_output
    if args.output:
        separate_output(args.output, args.source)
    output = create_output(root, args.output)
    print('OUTPUT', output, flush=True)
    (output / 'plot_environment.json').write_text(json.dumps(snapshot, indent=2), encoding='utf-8')
    bootstrap = ('import json,os,sys,runpy; '
                 'sys.path.extend(json.loads(os.environ.get("PAPER1_OPTIONAL_PACKAGE_PATHS", "[]"))); '
                 'sys.argv.pop(0); sys.path.insert(0,os.path.dirname(sys.argv[0])); '
                 'runpy.run_path(sys.argv[0],run_name="__main__")')
    command = [str(exe), '-B', '-c', bootstrap, str(package / 'make_figures.py'), '--output', str(output),
               '--source', str(bundle.root), '--figures', *selected]
    if args.tiff:
        command.append('--tiff')
    if not args.editable:
        command.append('--pdf-only')
    result = subprocess.run(command, cwd=root, env=env)
    if result.returncode:
        raise RuntimeError('Plotting stopped; partial output retained at ' + str(output))
    bundle.verify()
    print('COMPLETE', output, flush=True)
    print('Submission files: Fig*.pdf; optional copies only when requested.', flush=True)
    return 0


def render_workflow(output, *, python=None):
    """Publish a complete figure directory; reuse only verified final files."""
    from .publication import Bundle
    from .storage import read_json, write_json, sha256
    output = Path(output).resolve()
    source = output / 'results'
    bundle = Bundle(source).verify()
    names = {'Fig' + number for number in bundle.figures()}
    expected = {name + '.pdf' for name in names} | {'layout_checks.json', 'plot_environment.json'}
    manifest = sha256(source / 'manifest.csv')
    destination = output / 'figures'
    receipt = output / 'figures.json'

    def check_files(folder):
        if {p.name for p in folder.iterdir()} != expected:
            raise ValueError('Figure files do not match the manuscript mapping')
        layout = read_json(folder / 'layout_checks.json')
        if (len(layout) != len(names) or {r['figure'] for r in layout} != names
                or any(r['out_of_canvas_text'] for r in layout)):
            raise ValueError('Figure layout verification failed')
        return {name: sha256(folder / name) for name in sorted(expected)}

    if destination.exists():
        if not receipt.is_file():
            raise ValueError('Existing figure directory has no framework receipt')
        record = read_json(receipt)
        if record.get('input_manifest_sha256') != manifest or record.get('files') != check_files(destination):
            raise ValueError('Existing figures changed; export figures to a new directory')
        print('VERIFIED FIGURES', len(names), flush=True)
        return destination

    with tempfile.TemporaryDirectory(prefix='.figure-render-', dir=output) as temporary:
        rendered = Path(temporary) / 'figures'
        options = ['--source', str(source), '--output', str(rendered)]
        if python:
            options += ['--python', str(python)]
        main(options)
        files = check_files(rendered)
        bundle.verify()
        # The receipt precedes the atomic publish, so interruption cannot expose
        # a final directory without its integrity record.
        write_json(receipt, dict(input_manifest_sha256=manifest, files=files))
        os.replace(rendered, destination)
    return destination


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError) as error:
        print('STOP:', error, file=sys.stderr)
        raise SystemExit(1)
