"""Verify compact publication evidence; no downloads or model fitting."""
from pathlib import Path
from .publication import Bundle, Snapshot, cmpb

ROOT=Path(__file__).resolve().parents[1]


def rows(name):
    return Bundle(ROOT/'inputs/evidence').read('figure_data',name.removesuffix('.csv.gz')).to_dict('records')


def main():
    snapshot=Snapshot()
    bundle=snapshot.bundle
    tables=[e for e in bundle.entries if e['kind']=='table']
    inputs=[e for e in bundle.entries if e['kind']=='figure_data']
    for key, dimension, expected, repetitions in [('S22.1','weight_mode',96,1000),('S23.1','arm',72,500)]:
        frame=bundle.read('table',key)
        if len(frame)!=expected or frame[['scenario',dimension,'test']].duplicated().any():
            raise ValueError('Incomplete calibration grid: '+key)
        if not frame.datasets.eq(repetitions).all():
            raise ValueError('Calibration repetitions differ: '+key)
        import numpy as np
        if not np.allclose(frame.coverage95+frame.fpr_050,1,atol=1e-10,rtol=0):
            raise ValueError('Coverage/rejection accounting differs: '+key)
        for metric in ('coverage95','fdp_planned_050','fdp_retained_050'):
            if not frame[metric].between(0,1).all():
                raise ValueError('Invalid calibration rate: '+metric)
    held=rows('design_heldout_rule_evaluation.csv.gz')
    statuses={s:sum(r['status']==s for r in held) for s in
              ('conditionally_eligible','no_supported_selection','within_effect_not_estimable')}
    expected={'conditionally_eligible':16,'no_supported_selection':8,'within_effect_not_estimable':8}
    if statuses!=expected or len({(r['design'],r['scenario']) for r in held})!=32:
        raise ValueError('Held-out combination counts differ')
    selected=[r for r in held if r['status']=='conditionally_eligible']
    if sum(float(r['heldout_fdr'])>.05 for r in selected)!=8:
        raise ValueError('Held-out nominal exceedance count differs')
    if sum(float(r['heldout_fdr_mc_upper'])>.075 for r in selected)!=2:
        raise ValueError('Held-out Monte Carlo screen exceedance count differs')
    for filename,n in [('design_counts_summary.csv.gz',480),('design_gaussian_summary.csv.gz',384)]:
        data=rows(filename)
        if len(data)!=n or len({(r['design'],r['scenario'],r['model']) for r in data})!=n:
            raise ValueError('Design benchmark grid is incomplete: '+filename)
    added=[snapshot.table({'id':key}) for key in cmpb.EXTRA]
    snapshot.verify_unchanged()
    print('Verified',len(tables),'archived sections +',len(added),'CMPB sections',
          f'({sum(map(len,added))} additional records);',len(inputs),'figure inputs')
    print('Held-out: 16 eligible, 8 unsupported, 8 structurally non-estimable')
    print('Figures: 10 main and 15 supplementary; no model fitting performed')


if __name__=='__main__':main()
