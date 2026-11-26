"""Render the same section frames used for the CSVs as the submission workbook."""
import json
import math

import numpy as np
import pandas as pd


FILENAME = 'Supplementary_Tables.xlsx'
TITLES = (
    'Resources and eligibility', 'Human discovery-associated coefficients', 'Human threshold transitions',
    'Paired coefficient changes', 'Age and quality diagnostics', 'Quality-model variants',
    'Human design diagnostics', 'Astrocyte candidate estimates', 'Supplementary resource focal estimates',
    'Cognition associations', 'Cell-class and mixture checks', 'Mouse model summaries',
    'Mouse consistency and examples', 'Mouse precision decomposition', 'Cage variance and precision',
    'Design approximation checks', 'Five-model grouped-data simulation', 'Supplementary simulations',
    'Cage allocation geometry', 'Paired-test and count-pipeline calibration', 'Design-geometry benchmark',
    'Complete count calibration of paired differences', 'Extreme-tail controls and variance geometry',
)
NOTES = {
    'S11.1': ('Ast\u2013Oli and Ast\u2013Opc each used 19 matched donors (9 AD, 10 controls).',
              'Ast\u2013Oli and Ast\u2013Opc each include 9 AD and 10 control donors (19 matched donors per comparison).'),
    'S13.1': ('Counts use a single joint BH family: six specifications \u00d7 two models (baseline and cage fixed '
              'effects) \u00d7 237 planned genes = 2,844.',
              'joint BH family = six specifications \u00d7 two models \u00d7 237 planned genes (2,844 tests).'),
    'S14.4': ('significant_method_family: 1,422 tests per model across six specifications; significant_spec_family: '
              '237 tests per model and specification.',
              'BH correction covers 1,422 planned tests per model or 237 per model and specification.'),
}

CATALOGUE_GUIDE = ('Primary human panel results: S2-S4. Post hoc gene examples: S8, S9.4 and S13.4. '
                   'See Scope for each testing family.')
EXAMPLE_SCOPES = {
    'S8.1': 'Post hoc examples: GFAP, GSDMD and IGFBP5 across the designated supplementary astrocyte and comparator fits. BH columns retain their stated families.',
    'S8.2': 'SEA-AD: three post hoc example genes by three contrasts and two fits (18 rows). Joint q values use 17,064 planned positions, not these 18 rows. Fig. S2.',
    'S8.3': 'Three selected genes in the supplementary all-donor astrocyte comparison. The three-gene and panel-wide adjustments have different denominators.',
    'S9.3': 'Definitions of the raw p values and BH families used for the supplementary gene examples in S9.4.',
    'S9.4': 'Post hoc examples: three genes across twelve designated comparisons (36 planned positions, four unavailable). Read each q value with the family defined in S9.3.',
    'S13.2': 'Additional EMP3 example across human and mouse fits. Read each row with its species, contrast and correction family.',
    'S13.3': 'All 138 ortholog-mapped panel genes testable across the 18 mouse specifications; the gene-wise counts are not restricted to the illustrative genes. Fig. S3a.',
    'S13.4': 'Mouse estimates for post hoc examples selected after the model-consistency analysis. Selection did not define the panel-wide testing family.',
    'S20.5': 'General fixed-design grid, including six degenerate designs. Fig. S9 uses all 30 estimable matched-Gaussian designs for the paired and covariance-omitted comparison.',
    'S21.7': 'All 32 held-out design-scenario pairs. The empirical FDR, two-sided Monte Carlo interval and one-sided screening upper bound are distinct quantities. Fig. S20.',
}

# These sections display the original source's logical labels as Excel text.
_TEXT_FLAGS = frozenset(('S2.1','S3.2','S8.1','S8.3','S9.4','S11.1','S11.6',
                         'S13.2','S18.2','S19.1','S19.2','S19.4','S19.5'))
_UPPER_FLAGS = frozenset(('S6.5','S12.3','S12.9'))
_MIXED_NUMBERS = {'S17.7':'value','S20.2':'value','S20.3':'value','S20.7':'value','S19.6':'sample'}


def workbook_value(key, column, value):
    value = value.item() if isinstance(value, np.generic) else value
    if isinstance(value, bool):
        if key in _UPPER_FLAGS:
            return str(value).upper()
        if key in _TEXT_FLAGS:
            return str(value)
    if isinstance(value, str) and column == _MIXED_NUMBERS.get(key) and value and value[0] in '-0123456789':
        try:
            number = json.loads(value)
        except ValueError:
            return value
        # Preserve compound labels, padded identifiers and integers Excel cannot store exactly.
        if type(number) is int and abs(number) < 10**15:
            return number
        if type(number) is float and math.isfinite(number):
            return number
    return value


def section_scope(entry, frame):
    key, scope = entry['id'], entry['scope']
    if key in NOTES:
        return scope + ' ' + NOTES[key][0]
    if key == 'S22.1' and len(frame) == 96 and frame.scenario.nunique() == 24 and frame.datasets.eq(1000).all():
        return 'All 24 count-grid scenarios, two weight policies and two tests; 1,000 datasets per scenario.'
    if key == 'S23.1' and len(frame) == 72 and frame.scenario.nunique() == 6 and frame.datasets.eq(500).all():
        return 'All six targeted scenarios, six arms and two tests; 500 datasets per scenario.'
    if key == 'S23.2' and len(frame) and np.allclose(frame.cutoff, .05/3000, rtol=1e-12, atol=0):
        return 'All arm-test marginal tail summaries at 0.05/3000; rates use available tests.'
    return scope


def write_workbook(path, sections, entries):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    cat = wb.active
    cat.title = 'Catalogue'
    bold = Font(name='Calibri', bold=True)
    wrap = Alignment(vertical='center', wrap_text=True)
    cat['A1'] = 'Supplementary Tables S1-S23'
    cat['A1'].font = bold
    cat.append([])
    cat['A2'] = CATALOGUE_GUIDE
    cat.append(('Section', 'Worksheet', 'Header row', 'Records', 'Columns', 'Scope'))
    for c in cat[3]:
        c.font = bold
    for j, width in enumerate((13, 15, 14, 12, 12, 95), 1):
        cat.column_dimensions[get_column_letter(j)].width = width
    cat.freeze_panes = 'A4'
    next_row = {}
    for n, title in enumerate(TITLES, 1):
        sheet = wb.create_sheet(f'S{n:02d}')
        sheet['A1'] = f'Table S{n} {title}'
        sheet['A1'].font = bold
        sheet['A2'] = ('Blank numeric cells represent unavailable values.' if n < 22 else
                       'Rates are proportions; all paired differences are null. Planned and retained families are separate.')
        sheet.freeze_panes = 'A4'
        next_row[sheet.title] = 4
    for entry in sorted(entries, key=lambda e: tuple(map(int, e['id'][1:].split('.')))):
        key = entry['id']
        f = sections[key]
        # The planned gene count is needed by the plots, but is not a column of manuscript Table S22.1.
        if key == 'S22.1':
            f = f.drop(columns='genes')
        sh = wb[f"S{int(key[1:].split('.')[0]):02d}"]
        start = next_row[sh.title]
        sh.cell(start, 1, key).font = bold
        if key in NOTES:
            sh['A3'] = key + ': ' + NOTES[key][1]
        for j, col in enumerate(f.columns, 1):
            c = sh.cell(start+1, j, col)
            c.font, c.alignment = bold, wrap
            dim = sh.column_dimensions[get_column_letter(j)]
            dim.width = max(dim.width, min(55, len(col)+3), 20 if j == 1 else 13)
        sh.row_dimensions[start+1].height = 31
        for i, row in enumerate(f.itertuples(index=False, name=None), start+2):
            for j, v in enumerate(row, 1):
                if pd.isna(v):
                    continue
                displayed = workbook_value(key, f.columns[j-1], v)
                c = sh.cell(i, j, displayed)
                if isinstance(displayed, str):
                    c.data_type = 's'
                if key == 'S11.7' and j == 5:
                    c.number_format = '0.00%'
        scope = EXAMPLE_SCOPES.get(key, section_scope(entry, f))
        cat.append((key, sh.title, start+1, len(f), len(f.columns), scope))
        cat.cell(cat.max_row, 6).alignment = wrap
        cat.row_dimensions[cat.max_row].height = 42
        next_row[sh.title] = start + len(f) + 4
    cat.auto_filter.ref = f'A3:F{cat.max_row}'
    wb.save(path)
    wb.close()
