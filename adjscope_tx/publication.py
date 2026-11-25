"""One manuscript schema for computed results and the recorded evidence snapshot."""
import csv
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

import numpy as np
import pandas as pd
from pipeline.publication_text import publication_notes

from .storage import ROOT, read_json, separate_output, sha256
from . import cmpb_sections as cmpb
from . import supplement_workbook as supplement

ARCHIVE_SCHEMA = read_json(ROOT / 'inputs/publication.json')
ALL_STAGES = {'study', 'design', 'counts', 'tails'}
SCHEMA = {**ARCHIVE_SCHEMA, 'supplementary_workbook': supplement.FILENAME,
          'cmpb_evidence_digest': cmpb.EVIDENCE_DIGEST,
          'tables': ARCHIVE_SCHEMA['tables'] + [dict(id=k, stage='study', **v) for k, v in cmpb.EXTRA.items()]}
DESIGN = ('design_diagnostics', 'empirical_design_diagnostics', 'gaussian_summary',
          'counts_summary', 'gaussian_paired_mean_shift', 'counts_paired_mean_shift',
          'heldout_rule_evaluation', 'analytic_sensitivity')
CALIBRATION = {'S22.1': ('counts', 'summary.csv'), 'S23.1': ('tails', 'summary.csv'),
               'S23.2': ('tails', 'tail_summary.csv'), 'S23.3': ('tails', 'paired_comparisons.csv'),
               'S23.4': ('tails', 'expression_strata.csv'), 'S23.5': ('tails', 'gaussian_geometry.csv')}
MANIFEST_FIELDS = ('kind', 'id', 'file', 'section', 'columns', 'types', 'rows', 'sha256',
                   'figures', 'source', 'input_sha256', 'scope')


def schema_digest(schema=None):
    import hashlib
    return hashlib.sha256(json.dumps(SCHEMA if schema is None else schema, sort_keys=True).encode()).hexdigest()


def available_figures(stages):
    return [figure for figure in SCHEMA['figures'] if all(
        e['stage'] in stages for e in SCHEMA['figure_data'] if figure in e['figures'])]


def safe_path(root, name):
    path = (Path(root) / name).resolve()
    if not path.is_relative_to(Path(root).resolve()) or not path.is_file():
        raise ValueError('Missing or unsafe source: ' + name)
    return path


def select(frame, columns, label):
    missing = set(columns) - set(frame.columns)
    if missing:
        raise ValueError(label + ': missing columns ' + ', '.join(sorted(missing)))
    return frame.loc[:, columns].reset_index(drop=True)


class Computed:
    kind = 'computed_results'

    def __init__(self, sources, rscript='Rscript'):
        self.sources = {k: Path(v).expanduser().resolve() for k, v in sources.items() if v is not None}
        if not self.sources or set(self.sources) - {'study', 'design', 'counts', 'tails'}:
            raise ValueError('Supply study, design, counts and/or tails results')
        self.tracked = {}
        self.rscript = rscript
        self.blocks = {}
        self.expected = {}
        if 'study' in self.sources:
            mapping = self.read('study', 'reporting/block_sources.csv')
            if mapping.block.duplicated().any():
                raise ValueError('Duplicate study block mapping')
            self.blocks = dict(zip(mapping.block, mapping.file))
            index = self.read('study', 'reporting/source_index.csv')
            self.expected.update({('study', 'reporting/' + r.file): r.sha256 for r in index.itertuples()})
        for stage in ('counts', 'tails'):
            if stage not in self.sources:
                continue
            path = safe_path(self.sources[stage], 'review_manifest.json')
            self.track(stage, 'review_manifest.json', path)
            self.expected.update({(stage, name): digest for name, digest in read_json(path).items()})

    def track(self, stage, name, path):
        digest = sha256(path)
        key = stage + '/' + name
        if key in self.tracked and digest != self.tracked[key][1]:
            raise ValueError('Source changed: ' + key)
        if (stage, name) in self.expected and digest != self.expected[stage, name]:
            raise ValueError('Source checksum mismatch: ' + key)
        self.tracked[key] = (path, digest)

    def read(self, stage, name):
        path = safe_path(self.sources[stage], name)
        self.track(stage, name, path)
        return pd.read_csv(path, low_memory=False, float_precision='round_trip')

    def block(self, section):
        if section not in self.blocks:
            raise ValueError('Missing study section: ' + section)
        return self.read('study', 'reporting/' + self.blocks[section])

    def table(self, entry):
        section = entry['id']
        if section == 'S9.5':
            name = 'supplementary/bulk.complete.json'
            receipt = safe_path(self.sources['study'], name)
            self.track('study', name, receipt)
            frames = []
            for member, digest in cmpb.receipt_members(read_json(receipt)):
                self.expected['study', member] = digest
                frames.append(self.read('study', member))
            frame = cmpb.bulk_summary(*frames)
        elif section == 'S11.7':
            name = 'reporting/S11/doublet_libraries.csv'
            if ('study', name) not in self.expected:
                raise ValueError('S11.7: library screen is missing from the study source index')
            frame = cmpb.doublet_summary(self.read('study', name))
        elif entry['stage'] == 'study':
            frame = self.block(section)
            if section == 'S2.1':
                frame = frame[frame.q_joint_base.lt(.05) | frame.q_joint_quality.lt(.05)]
            elif section == 'S4.1':
                selected = self.block('S3.2')
                keys = pd.MultiIndex.from_frame(selected[['gene_symbol', 'spec']])
                keep = pd.MultiIndex.from_frame(frame[['gene_symbol', 'spec']]).isin(keys)
                frame = frame[frame.q_joint.lt(.05) | frame.q_HC3_joint.lt(.05) | keep]
        elif entry['stage'] == 'design':
            frame = self.read('design', 'review/' + DESIGN[int(section.split('.')[1])-1] + '.csv')
        elif section == 'S23.5':
            if (self.sources['tails'] / 'gaussian_geometry.csv').is_file():
                frame = self.read('tails', 'gaussian_geometry.csv')
            else:
                protocol = safe_path(self.sources['tails'], 'protocol.json')
                self.track('tails', 'protocol.json', protocol)
                with tempfile.TemporaryDirectory() as folder:
                    temporary = Path(folder)
                    output = temporary / 'geometry.csv'
                    # ASCII temporary paths also support Windows R installations with a non-UTF8 locale.
                    for relative in ('analysis/common.R','paired_count_calibration/engine.R','paired_tail_diagnostics/geometry.R'):
                        destination = temporary/relative
                        destination.parent.mkdir(parents=True,exist_ok=True)
                        shutil.copy2(ROOT/relative, destination)
                    shutil.copy2(protocol, temporary/'protocol.json')
                    env = os.environ.copy()
                    if os.name == 'nt':
                        env.update(LC_ALL='English_United States.utf8', LANG='English_United States.utf8')
                    subprocess.run([str(self.rscript), '--vanilla', str(temporary/'paired_tail_diagnostics/geometry.R'),
                                    str(temporary), str(temporary/'protocol.json'), str(output)], check=True, env=env)
                    frame = pd.read_csv(output)
        else:
            frame = self.read(*CALIBRATION[section])
            if section == 'S23.2':
                frame = frame[frame.label.eq('bh_first')]
            elif section == 'S23.3':
                frame = frame[frame.test.eq('HC3') & frame.arm.isin(['independent_shared', 'independent_design'])
                              & frame.reference_arm.eq('estimated_shared') & frame.reference_test.eq('HC3')
                              & frame.metric.eq('fdp_planned_050')]
            elif section == 'S23.4':
                frame = frame[frame.arm.eq('estimated_design') & frame.test.eq('HC3')]
                frame = frame.groupby('stratum', sort=False)[['available', 'discoveries_planned']].sum()
                frame = frame.reindex(['mean_lt10', 'mean10_lt50', 'mean_ge50']).reset_index()
                frame = frame.rename(columns={'available':'available_tests', 'discoveries_planned':'false_discovery_events'})
                frame['events_per_million_tests'] = frame.false_discovery_events / frame.available_tests * 1e6
        frame = select(frame, entry['columns'], section)
        if section in ('S17.7','S20.7','S20.2','S20.3'):
            from pipeline.publication_text import display_values
            frame = pd.DataFrame([display_values(section, list(frame.columns), list(row))
                                  for row in frame.itertuples(index=False, name=None)], columns=frame.columns)
        # Runtime settings can contain private paths; do not publish those strings.
        for column in frame.select_dtypes(include=['object']):
            private = frame[column].astype(str).str.contains(r'/home/|[A-Za-z]:[\\/]Users[\\/]', regex=True)
            frame.loc[private, column] = '[runtime path omitted]'
        return frame

    def figure_data(self, entry):
        name = entry['id']
        frame = self.read(entry['stage'], entry['source'])
        if name == 'mouse_se_ratios':
            base = frame[frame.model.eq('baseline') & frame.status.eq('available')][['gene_symbol', 'spec', 'SE']]
            frame = frame[frame.model.ne('baseline') & frame.status.eq('available')].merge(
                base, on=['gene_symbol','spec'], suffixes=('', '_base'), validate='many_to_one')
            frame['SE_ratio'] = frame.SE / frame.SE_base
            frame = frame.groupby(['spec','model'], sort=True).SE_ratio.median().reset_index()
        elif name == 'precision_components':
            rows = []
            for spec, group in frame.groupby('spec', sort=True):
                for metric in ('SE_ratio','unscaled_ratio','posterior_SD_ratio','reweight_factor'):
                    values = group[metric].dropna()
                    q1, med, q3 = values.quantile([.25,.5,.75])
                    rows.append(dict(spec=spec, metric=metric, n=len(values), q25=q1, median=med, q75=q3,
                        whisker_low=values[values.ge(q1-1.5*(q3-q1))].min(),
                        whisker_high=values[values.le(q3+1.5*(q3-q1))].max()))
            frame = pd.DataFrame(rows)
        elif name == 'mouse_focal':
            frame = frame[frame.gene_symbol.isin(['GFAP','GSDMD','IGFBP5','EMP3'])]
        elif name == 'family_sizes':
            frame = frame[frame.collection.eq('human_17064') & frame.denominator.eq('planned')]
            frame = select(frame, entry['columns'], name).drop_duplicates()
        elif name == 'icc_density':
            frame = select(frame, entry['columns'], name)
            frame = frame[frame.weight_policy.eq('shared')].dropna()
        elif name == 'human_contexts':
            frame = frame[frame.collection.eq('human_17064') & frame.model.eq('clinical_status')]
            rows = []
            for context, group in frame.groupby('context', sort=True):
                row = dict(context=context, available=group.beta_base.count(), selected=group.original_q_base.lt(.05).sum())
                for field in ('log_abs_beta_ratio','minus_log_SE_ratio'):
                    row.update({field+'_'+q: value for q, value in zip(('q25','median','q75'),group[field].quantile([.25,.5,.75]))})
                rows.append(row)
            frame = pd.DataFrame(rows)
        elif name == 'design_errors':
            frame = pd.DataFrame([dict(spec=spec, n=g.design_only_log_error.count(),
                **dict(zip(('p05','q25','median','q75','p95'),g.design_only_log_error.quantile([.05,.25,.5,.75,.95]))))
                for spec, g in frame.groupby('spec', sort=True)])
        return select(frame, entry['columns'], name)

    def verify_unchanged(self):
        for key, (path, digest) in self.tracked.items():
            if sha256(path) != digest:
                raise ValueError('Source changed during export: ' + key)


class Snapshot:
    kind = 'recorded_publication_evidence'
    sources = dict.fromkeys(('study','design','counts','tails'))

    def __init__(self):
        self.bundle = Bundle(ROOT/'inputs/evidence').verify()
        path = safe_path(ROOT, cmpb.EVIDENCE)
        self.tracked = {cmpb.EVIDENCE: (path, sha256(path))}
        evidence = read_json(path)
        if schema_digest(evidence) != cmpb.EVIDENCE_DIGEST:
            raise ValueError('CMPB recorded study evidence changed')
        self.study_rows = {name: pd.DataFrame(v['rows'], columns=v['columns']) for name, v in evidence.items()}

    def table(self, entry):
        if entry['id'] == 'S9.5':
            return cmpb.bulk_summary(*(self.study_rows[k] for k in cmpb.BULK))
        if entry['id'] == 'S11.7':
            return cmpb.doublet_summary(self.study_rows['doublet_libraries.csv'])
        return self.get('table', entry['id'])

    def figure_data(self, entry):
        return self.get('figure_data', entry['id'])

    def get(self, kind, key):
        entry = self.bundle.entry(kind, key)
        path = safe_path(self.bundle.root, entry['file'])
        self.tracked[entry['file']] = (path, sha256(path))
        return self.bundle.read(kind, key)

    verify_unchanged = Computed.verify_unchanged


def write_bundle(provider, output):
    output = Path(output).expanduser().resolve()
    separate_output(output)
    for root in provider.sources.values():
        if root is not None and (output.is_relative_to(root) or root.is_relative_to(output)):
            raise ValueError('Export overlaps calculation inputs')
    if output.exists():
        raise ValueError('Output must be new: ' + str(output))
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.'+output.name+'-', dir=output.parent))
    try:
        sections, plot_data, manifest = {}, {}, []
        for entry in SCHEMA['tables']:
            if entry['stage'] in provider.sources:
                sections[entry['id']] = (sections[entry['alias']] if entry.get('alias') else
                    publication_notes(entry['id'], select(provider.table(entry), entry['columns'], entry['id'])))
        for entry in SCHEMA['figure_data']:
            if entry['stage'] in provider.sources:
                frame = sections[entry['table']] if entry.get('table') else provider.figure_data(entry)
                plot_data[entry['id']] = select(frame, entry['columns'], entry['id'])
        (staging / 'tables').mkdir()
        aliases = {e['id']:e['alias'] for e in SCHEMA['tables'] if e.get('alias')}
        for table in dict.fromkeys(k.split('.')[0] for k in sections):
            members = [(key, frame) for key, frame in sections.items() if key.split('.')[0] == table and key not in aliases]
            pd.concat([frame.assign(section=key, record=np.arange(1,len(frame)+1))
                       for key, frame in members], ignore_index=True).to_csv(staging/'tables'/('Table'+table+'.csv'), index=False)
        def record(kind, key, frame, filename, section='', figures='', scope=''):
            types = {col:('boolean' if pd.api.types.infer_dtype(frame[col].dropna()) == 'boolean' else
                          'number' if pd.api.types.is_numeric_dtype(frame[col]) else 'string') for col in frame}
            manifest.append(dict(kind=kind, id=key, file=filename, section=section,
                columns=json.dumps(list(frame.columns)), types=json.dumps(types), rows=len(frame), sha256=sha256(staging/filename),
                figures=figures, source=provider.kind, input_sha256='', scope=scope))
        for entry in SCHEMA['tables']:
            key = entry['id']
            if key in sections:
                source = aliases.get(key, key)
                record('table', key, sections[key], 'tables/Table'+source.split('.')[0]+'.csv', source,
                       scope=supplement.section_scope(entry, sections[key]))
        for entry in SCHEMA['figure_data']:
            key = entry['id']
            if key not in plot_data:
                continue
            frame = plot_data[key]
            same = entry.get('table')
            if same:
                filename, section = 'tables/Table'+same.split('.')[0]+'.csv', same
            else:
                (staging/'figure_data').mkdir(exist_ok=True)
                filename, section = 'figure_data/'+key+'.csv', ''
                frame.to_csv(staging/filename, index=False)
            record('figure_data', key, frame, filename, section, ';'.join(entry['figures']))
        if set(provider.sources) == ALL_STAGES:
            from .paper_tables import main_tables
            for key, frame in main_tables(sections, plot_data, SCHEMA['main_tables']).items():
                filename = 'tables/Table'+key+'.csv'
                frame.to_csv(staging/filename, index=False)
                record('main_table', key, frame, filename, scope='Main manuscript; derived from the same exported sections')
            supplement.write_workbook(staging/supplement.FILENAME, sections, SCHEMA['tables'])
            manifest.append(dict(kind='workbook', id='supplement', file=supplement.FILENAME,
                rows=sum(map(len, sections.values())), sha256=sha256(staging/supplement.FILENAME),
                source=provider.kind, scope='CMPB supplementary Tables S1-S23, including declared section aliases'))
        for figure in available_figures(provider.sources):
            needs = [e['id'] for e in SCHEMA['figure_data'] if figure in e['figures']]
            if all(key in plot_data for key in needs):
                manifest.append(dict(kind='figure', id=figure, file='', section='', columns='[]', rows=0,
                    sha256='', figures='', source=provider.kind, input_sha256='',
                    scope=';'.join(needs) if needs else 'Schematic; no numerical inputs'))
        for key, (_, digest) in provider.tracked.items():
            manifest.append(dict(kind='input', id=key, file='', section='', columns='[]', rows=0,
                sha256='', figures='', source=provider.kind, input_sha256=digest, scope='Read-only source fingerprint'))
        provider.verify_unchanged()
        manifest.append(dict(kind='contract', id='publication', file='', section='', columns='[]', rows=0,
            sha256='', figures='', source=provider.kind, input_sha256=schema_digest(),
            scope=';'.join(sorted(provider.sources))))
        with (staging/'manifest.csv').open('w',encoding='utf-8',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=MANIFEST_FIELDS);writer.writeheader();writer.writerows(manifest)
        Bundle(staging).verify(expected_stages=provider.sources)
        os.replace(staging, output)
    finally:
        if staging.exists():
            if staging.resolve().parent != output.parent or not staging.name.startswith('.'+output.name+'-'):
                raise ValueError('Refusing cleanup outside the export staging directory')
            shutil.rmtree(staging)
    return output


class Bundle:
    def __init__(self, root):
        self.root = Path(root).expanduser().resolve()
        self._frames = {}
        with safe_path(self.root, 'manifest.csv').open(encoding='utf-8',newline='') as f:
            self.entries = list(csv.DictReader(f))
        identities = [(e['kind'],e['id']) for e in self.entries]
        if len(set(identities)) != len(identities):
            raise ValueError('Duplicate publication manifest IDs')

    def entry(self, kind, key):
        matches = [e for e in self.entries if e['kind'] == kind and e['id'] == key]
        if len(matches) != 1:
            raise ValueError('Missing publication '+kind+': '+key)
        return matches[0]

    def read(self, kind, key):
        entry = self.entry(kind, key)
        path = safe_path(self.root, entry['file'])
        digest = sha256(path)
        if digest != entry['sha256']:
            raise ValueError('Publication CSV changed: ' + entry['file'])
        if path not in self._frames or self._frames[path][0] != digest:
            self._frames[path] = (digest, pd.read_csv(path, low_memory=False, float_precision='round_trip'))
        frame = self._frames[path][1]
        if entry['section']:
            frame = frame[frame.section.eq(entry['section'])]
        frame = select(frame, json.loads(entry['columns']), key)
        for column, kind in json.loads(entry.get('types') or '{}').items():
            if kind == 'number':
                frame[column] = pd.to_numeric(frame[column], errors='raise')
            elif kind == 'boolean':
                values = frame[column].dropna().astype(str)
                if not values.isin(['True','False','true','false']).all():
                    raise ValueError('Invalid Boolean values: ' + key + '/' + column)
                frame[column] = frame[column].map(lambda v: v if pd.isna(v) else str(v).lower() == 'true')
        if len(frame) != int(entry['rows']):
            raise ValueError('Publication row count changed: ' + key)
        return frame

    def figures(self):
        return [e['id'] for e in self.entries if e['kind'] == 'figure']

    def verify(self, expected_stages=None):
        contract = self.entry('contract', 'publication')
        stages = set(contract['scope'].split(';'))
        if not stages or not stages <= {'study','design','counts','tails'}:
            raise ValueError('Invalid publication stages')
        if expected_stages is not None and stages != set(expected_stages):
            raise ValueError('Publication stages differ from the completed workflow')
        if contract['input_sha256'] == schema_digest():
            schema = SCHEMA
        elif contract['input_sha256'] == schema_digest(ARCHIVE_SCHEMA):
            schema = ARCHIVE_SCHEMA
        else:
            raise ValueError('Publication schema changed; export again to a new directory')
        expected = {('contract','publication')}
        for kind, group in (('table','tables'),('figure_data','figure_data')):
            expected.update((kind,e['id']) for e in schema[group] if e['stage'] in stages)
        expected.update(('figure',key) for key in available_figures(stages))
        if stages == ALL_STAGES:
            expected.update(('main_table',e['id']) for e in schema['main_tables'])
            if 'supplementary_workbook' in schema:
                expected.add(('workbook','supplement'))
        actual = {(e['kind'],e['id']) for e in self.entries if e['kind'] != 'input'}
        if expected != actual:
            raise ValueError('Incomplete publication contract: missing '+str(sorted(expected-actual))+
                             '; extra '+str(sorted(actual-expected)))
        registered = {'manifest.csv'} | {e['file'] for e in self.entries if e['file']}
        present = {p.relative_to(self.root).as_posix() for p in self.root.rglob('*') if p.is_file()}
        if registered != present:
            raise ValueError('Unexpected or missing publication files: '+str(sorted(registered ^ present)))
        for kind, group in (('table','tables'),('figure_data','figure_data')):
            for specification in schema[group]:
                if specification['stage'] not in stages:
                    continue
                entry = self.entry(kind, specification['id'])
                if json.loads(entry['columns']) != specification['columns']:
                    raise ValueError('Publication columns differ: '+specification['id'])
                target = specification.get('alias') if kind == 'table' else specification.get('table')
                if target:
                    original = self.entry('table', target)
                    if (entry['file'],entry['section']) != (original['file'],original['section']):
                        raise ValueError('Publication alias differs: '+specification['id'])
        for entry in self.entries:
            if entry['kind'] in ('table', 'figure_data', 'main_table'):
                self.read(entry['kind'], entry['id'])
        for figure in self.figures():
            for item in schema['figure_data']:
                if figure in item['figures']:
                    self.entry('figure_data', item['id'])
        if stages == ALL_STAGES:
            from .paper_tables import main_tables
            sections = {e['id']:self.read('table', e['id']) for e in schema['tables']}
            figures = {e['id']:self.read('figure_data', e['id']) for e in schema['figure_data']}
            if 'supplementary_workbook' in schema:
                x = self.entry('workbook', 'supplement')
                if (x['file'] != schema['supplementary_workbook'] or sha256(safe_path(self.root, x['file'])) != x['sha256']
                        or int(x['rows']) != sum(map(len, sections.values()))):
                    raise ValueError('Supplementary workbook changed or has a stale row count')
            for key, frame in main_tables(sections, figures, schema['main_tables']).items():
                if not frame.equals(self.read('main_table', key)):
                    raise ValueError('Main table is stale: '+key)
        return self
