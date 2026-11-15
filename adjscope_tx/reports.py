"""Compact CSV exports from a workflow or explicitly supplied completed stages."""
from pathlib import Path

from .storage import read_json, sha256, write_json, separate_output
from .publication import Bundle, Computed, Snapshot, write_bundle


def workflow_sources(source, *, finalizing=False):
    source = Path(source).expanduser().resolve()
    record = read_json(source/'workflow.json')
    if record['status'] != 'COMPLETE' and not (finalizing and record['status'] == 'FINALIZING'):
        raise ValueError('Workflow is not complete')
    if any(record.get('stages', {}).get(s, {}).get('status') != 'COMPLETE'
           for s in record['specification']['stages']):
        raise ValueError('Workflow has incomplete analysis stages')
    return record, {s:source/s for s in record['specification']['stages']}


def index_workflow(output):
    output = Path(output).resolve()
    record, sources = workflow_sources(output, finalizing=True)
    result = output/'results'
    provider = Computed(sources, record['specification']['rscript'])
    if result.exists():
        bundle = Bundle(result).verify(expected_stages=sources)
        for entry in bundle.entries:
            if entry['kind'] == 'input':
                stage, relative = entry['id'].split('/',1)
                if sha256(sources[stage]/relative) != entry['input_sha256']:
                    raise ValueError('Existing export is stale; export to a new directory')
    else:
        write_bundle(provider, result)
    files = [dict(file=p.relative_to(output).as_posix(),sha256=sha256(p),bytes=p.stat().st_size)
             for p in sorted(result.rglob('*.csv'))]
    write_json(output/'results.json', dict(kind='computed_results',source_sha256=record['source_sha256'],files=files))
    return files


def finalize_workflow(output, python=None):
    from .plotting import render_workflow
    index_workflow(output)
    render_workflow(output, python=python)


def export_workflow(source, output):
    record, sources = workflow_sources(source)
    output = separate_output(output, source)
    return write_bundle(Computed(sources, record['specification']['rscript']), output)


def export_computed(sources, output, rscript='Rscript'):
    return write_bundle(Computed(sources, rscript), output)


def export_publication(output):
    return write_bundle(Snapshot(), output)
