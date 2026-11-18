"""Small orchestration fixtures projected from the canonical evidence store."""
from adjscope_tx.publication import Bundle
from adjscope_tx.storage import ROOT


def stage_frame(name):
    key = dict(count_summary='S22.1', tail_summary='S23.1', tail_rates='S23.2',
               paired_comparisons='S23.3', expression_strata='S23.4', gaussian_geometry='S23.5')[name]
    frame = Bundle(ROOT/'inputs/evidence').read('table',key)
    if name == 'expression_strata':
        frame=frame.rename(columns={'available_tests':'available','false_discovery_events':'discoveries_planned'})
        frame['arm']='estimated_design'; frame['test']='HC3'
    return frame
