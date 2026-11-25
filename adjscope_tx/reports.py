"""Compact CSV exports from a workflow or explicitly supplied completed stages."""
from pathlib import Path
import time

from .storage import read_json, sha256, write_json, separate_output, output_lock, source_files, source_digest
from .publication import Bundle, Computed, Snapshot, write_bundle, safe_path, schema_digest


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
        if bundle.entry('contract', 'publication')['input_sha256'] != schema_digest():
            raise ValueError('Existing results use the archived table schema. Use report with a new output directory.')
        for entry in bundle.entries:
            if entry['kind'] == 'input':
                stage, relative = entry['id'].split('/',1)
                if sha256(sources[stage]/relative) != entry['input_sha256']:
                    raise ValueError('Existing export is stale; export to a new directory')
    else:
        write_bundle(provider, result)
    files = [dict(file=p.relative_to(output).as_posix(),sha256=sha256(p),bytes=p.stat().st_size)
             for p in sorted(result.rglob('*')) if p.is_file()]
    write_json(output/'results.json', dict(kind='computed_results',source_sha256=record['source_sha256'],files=files))
    return files


def finalize_workflow(output, python=None):
    from .plotting import render_workflow
    index_workflow(output)
    render_workflow(output, python=python)


def publication_source_changes(original, current, expected):
    """Check a legacy source record without replacing its analysis identity."""
    if source_digest(original) != expected:
        raise ValueError('Original source manifest does not match the analysis run')
    if set(original) != set(current):
        raise ValueError('Source file set changed; use a separate publication export')
    changed = {name:dict(before=original[name],after=current[name])
               for name in current if original[name] != current[name]}
    entry_points = {'adjscope_tx/cli.py','adjscope_tx/reports.py','adjscope_tx/storage.py',
                    'adjscope_tx/workflow.py','adjscope_tx/plotting.py'}
    unsafe = [name for name in changed if name not in entry_points and
              not (name.startswith('publication_figures/') and name.endswith('.py'))]
    if unsafe:
        raise ValueError('Analysis/input code changed: '+', '.join(sorted(unsafe)))
    return changed


def finish_existing_workflow(output, *, python=None, analysis_source_manifest=None):
    """Validate existing CSVs and finish publication only, preserving analysis provenance."""
    from .plotting import render_workflow
    output = separate_output(output)
    marker = output/'workflow.json'
    if not marker.is_file():
        raise ValueError('No workflow.json for publication-only finalization')
    with output_lock(output):
        record = read_json(marker)
        original_record = sha256(marker)
        stages = record['specification']['stages']
        if record['output'] != str(output):
            raise ValueError('Workflow output path changed')
        if not stages or any(record.get('stages',{}).get(s,{}).get('status') != 'COMPLETE' for s in stages):
            raise ValueError('Workflow has incomplete analysis stages; publication-only finalization refused')
        current = source_files()
        original = read_json(analysis_source_manifest) if analysis_source_manifest else record.get('source_files')
        if original is None:
            if source_digest(current) != record['source_sha256']:
                raise ValueError('Legacy source changed; provide --analysis-source-manifest from the original code')
            original = current
        changed = publication_source_changes(original,current,record['source_sha256'])
        source = output/'results'
        export_record = read_json(output/'results.json')
        if export_record.get('source_sha256') != record['source_sha256']:
            raise ValueError('CSV export belongs to a different analysis source')
        expected = export_record['files']
        names = [item['file'] for item in expected]
        actual = {p.relative_to(output).as_posix() for p in source.rglob('*') if p.is_file()}
        if not names or len(names) != len(set(names)) or set(names) != actual:
            raise ValueError('CSV export receipt is incomplete')

        def verify_results():
            bundle = Bundle(source).verify(expected_stages=stages)
            for item in expected:
                path = safe_path(output,item['file'])
                if sha256(path) != item['sha256'] or path.stat().st_size != item['bytes']:
                    raise ValueError('Exported CSV changed: '+item['file'])
            for item in bundle.entries:
                if item['kind'] == 'input':
                    stage,relative = item['id'].split('/',1)
                    if stage not in stages or sha256(safe_path(output/stage,relative)) != item['input_sha256']:
                        raise ValueError('Analysis input to CSV export changed: '+item['id'])

        verify_results()
        manifest = sha256(source/'manifest.csv')
        print('FINALIZE ONLY: verified completed stages and computed CSVs; no downloads or model fitting',flush=True)
        render_workflow(output,python=python or record['specification']['python'])
        verify_results()
        if source_files() != current or sha256(marker) != original_record:
            raise ValueError('Source or workflow record changed during finalization')
        record['publication'] = dict(finalizer_source_sha256=source_digest(current),source_changes=changed,
            input_manifest_sha256=manifest,figure_receipt_sha256=sha256(output/'figures.json'),
            completed=time.time(),analysis_refitted=False)
        if record.get('error'):
            record['publication']['previous_export_error'] = record['error']
        record.update(status='COMPLETE',finished=time.time(),source_files=original)
        record.pop('error',None)
        write_json(marker,record)
    print('COMPLETE',output/'results',output/'figures',flush=True)
    return output


def export_workflow(source, output):
    record, sources = workflow_sources(source)
    output = separate_output(output, source)
    return write_bundle(Computed(sources, record['specification']['rscript']), output)


def export_computed(sources, output, rscript='Rscript'):
    return write_bundle(Computed(sources, rscript), output)


def export_publication(output):
    return write_bundle(Snapshot(), output)
