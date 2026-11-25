"""Study summaries added to the CMPB supplementary tables."""
from pathlib import PurePosixPath
import re

import numpy as np
import pandas as pd


BULK = ('188_design_status.csv', '190_endpoint_summary.csv')
LIBRARIES = ('GSM6911563', 'GSM6911564', 'GSM6911565')
REGIONS = ('entorhinal_cortex', 'frontal_cortex')
EVIDENCE = 'inputs/cmpb_study_evidence.json'
EVIDENCE_DIGEST = '7a8506cbab33e4c0cac2592f97cbdd14222640dc8e759569c68ed536d87bff7c'
EXTRA = {
    'S9.5': dict(columns=['region', 'AD', 'controls', 'total samples', 'measured panel genes',
                          'same direction as panel', 'joint BH discoveries'],
                 scope='GSE48350: both regions in the primary age-overlap log2 model, adjusted for age and sex. '
                       'The joint BH family contains 3,880 planned positions; direction is relative to the panel source.'),
    'S11.7': dict(columns=['GEO library', 'seed', 'QC-passing cells', 'predicted doublets', 'predicted fraction'],
                  scope='GSE222007: the three libraries with high primary-seed fractions discussed in S7, not all 39 '
                        'eligible libraries. Predicted fraction is the proportion of QC-passing cells flagged by '
                        'Scrublet, not a measured doublet rate.'),
}


def receipt_members(receipt):
    # Use fingerprinted members under the selected attempt, not the machine-specific absolute path.
    tail = PurePosixPath(receipt['directory'].replace(chr(92), '/')).parts[-2:]
    if len(tail) != 2 or tail[0] != 'bulk' or not re.fullmatch(r'attempt_[0-9]+', tail[1]):
        raise ValueError('S9.5: invalid bulk attempt in completion receipt')
    result = []
    for name in BULK:
        member = '/'.join((*tail, name))
        digest = receipt['files'].get(member)
        if not isinstance(digest, str) or not re.fullmatch('[a-f0-9]{64}', digest):
            raise ValueError('S9.5: missing bulk receipt fingerprint for ' + member)
        result.append(('supplementary/' + member, digest))
    return result


def counts(frame, columns, label):
    for col in columns:
        values = pd.to_numeric(frame[col], errors='raise')
        if not (np.isfinite(values) & values.ge(0) & values.eq(np.floor(values))).all():
            raise ValueError(label + ': invalid count in ' + col)
        frame[col] = values.astype('int64')


def ordered(frame, key, expected, label):
    if frame[key].duplicated().any() or set(frame[key]) != set(expected):
        raise ValueError(label + ': missing, duplicate or unexpected ' + key)
    return frame.set_index(key).loc[list(expected)].reset_index()


def bulk_summary(design, endpoints):
    def primary(frame):
        return ordered(frame.loc[frame.model.eq('overlap_log2_linear')], 'region', REGIONS, 'S9.5')
    d, e = primary(design), primary(endpoints)
    if not d.status.eq('tested').all():
        raise ValueError('S9.5: primary model was not tested')
    counts(d, ['AD', 'control'], 'S9.5')
    counts(e, ['tested', 'same', 'significant_same', 'significant_opposite'], 'S9.5')
    if ((e.same > e.tested) | (e.significant_same > e.same) |
            (e.significant_opposite > e.tested - e.same)).any():
        raise ValueError('S9.5: inconsistent directional counts')
    out = d[['region', 'AD', 'control']].copy()
    out['total'] = d.AD + d.control
    out['tested'], out['same'] = e.tested, e.same
    out['significant'] = e.significant_same + e.significant_opposite
    out.columns = EXTRA['S9.5']['columns']
    return out


def doublet_summary(frame):
    f = frame.loc[frame.gsm.isin(LIBRARIES)]
    f = ordered(f.loc[pd.to_numeric(f.seed, errors='raise').eq(290)], 'gsm', LIBRARIES, 'S11.7')
    counts(f, ['qc_cells', 'predicted_doublets'], 'S11.7')
    if (not f.status.eq('completed_risk_screen_not_doublet_truth').all() or
            (f.qc_cells.eq(0) | f.predicted_doublets.gt(f.qc_cells)).any()):
        raise ValueError('S11.7: invalid primary library screen')
    f['predicted_fraction'] = pd.to_numeric(f.predicted_fraction, errors='raise')
    if not np.allclose(f.predicted_fraction, f.predicted_doublets / f.qc_cells, rtol=0, atol=1e-12):
        raise ValueError('S11.7: fraction disagrees with doublet and QC counts')
    out = f[['gsm', 'seed', 'qc_cells', 'predicted_doublets', 'predicted_fraction']].copy()
    out['seed'] = pd.to_numeric(out.seed).astype('int64')
    out.columns = EXTRA['S11.7']['columns']
    return out
