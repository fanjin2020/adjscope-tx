"""Atomic records, content identities and single-writer outputs."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
            json.dump(value, stream, indent=2, allow_nan=False)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024**2), b''):
            digest.update(block)
    return digest.hexdigest()


def source_files(root=ROOT):
    root = Path(root)
    folders = ('adjscope_tx', 'pipeline', 'analysis', 'design_benchmark',
               'paired_count_calibration', 'paired_tail_diagnostics', 'publication_figures', 'inputs')
    files = [root / n for n in ('run.py', 'config.json', 'requirements.txt',
                                'requirements-supplementary.txt')]
    for name in folders:
        files.extend(p for p in (root / name).rglob('*')
                     if p.suffix in ('.py', '.R', '.json', '.csv')
                     and '__pycache__' not in p.parts)
    return {p.relative_to(root).as_posix(): sha256(p) for p in sorted(files)}


def source_digest(record):
    return hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()


def source_identity(root=ROOT):
    return source_digest(source_files(root))


def separate_output(output, *sources):
    output = Path(output).expanduser().resolve()
    for source in (ROOT, *sources):
        if source is None:
            continue
        source = Path(source).expanduser().resolve()
        if output.is_relative_to(source) or source.is_relative_to(output):
            raise ValueError('Output overlaps source: ' + str(source))
    return output


@contextmanager
def output_lock(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    with (output / '.framework.lock').open('a+b') as stream:
        if os.name == 'nt':
            import msvcrt
            stream.seek(0, 2)
            if stream.tell() == 0:
                stream.write(b'0')
                stream.flush()
            stream.seek(0)
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise RuntimeError('Another writer owns this output') from exc
        else:
            import fcntl
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise RuntimeError('Another writer owns this output') from exc
        try:
            yield
        finally:
            if os.name == 'nt':
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)
