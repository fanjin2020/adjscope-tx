"""Render the manuscript overview tables from result summaries and protocol text."""
import pandas as pd


def main_tables(sections, figures, specification):
    def unique(frame, column):
        values = frame[column].dropna().unique()
        if len(values) != 1:
            raise ValueError('Main-table description requires a common '+column)
        return int(values[0])

    group = sections['S17.1']
    general = sections['S20.5']
    donor = sections['S20.1']
    full = sections['S20.10']
    gaussian, count = sections['S21.3'], sections['S21.4']
    paired, tail = sections['S22.1'], sections['S23.1']
    human = donor[donor.contrast.eq('clinical_status')]
    mouse = sections['S12.7']
    family = figures['family_sizes'].set_index('scope').planned
    clinical = sections['S3.1']
    clinical = clinical[clinical.subset.eq('all_testable')]
    v = dict(
        donors=len(sections['S5.5']), contexts=human.context.nunique(),
        donor_min=int(human.n.min()), donor_max=int(human.n.max()),
        animals=unique(sections['S21.2'],'n'),
        general_designs=general.design.nunique(), error_laws=general.error_law.nunique(),
        mean_cases=general.mean_case.nunique(), general_draws=unique(general,'planned'),
        layouts=group.layout.nunique(), group_scenarios=group.scenario.nunique(),
        group_models=group.model.nunique(), group_draws=unique(group,'planned'),
        group_fits=int(group.planned.sum()), group_available=int(group.available.sum()),
        group_structural=int(group.not_estimable.sum()), group_failures=int(group.numerical_failed.sum()),
        donor_designs=len(donor[['context','contrast']].drop_duplicates()),
        donor_weights=donor.weight.nunique(), donor_draws=unique(donor,'planned'),
        full_scenarios=full.scenario.nunique(), full_reps=unique(full,'repetitions'),
        full_models=full.model.nunique(), genes=unique(full,'genes'),
        full_datasets=int(full[['scenario','repetitions']].drop_duplicates().repetitions.sum()),
        gaussian_allocations=gaussian.design.nunique(), gaussian_conditions=gaussian.scenario.nunique(),
        gaussian_reps=unique(gaussian,'planned_datasets'),
        count_allocations=count.design.nunique(), count_conditions=count.scenario.nunique(),
        count_reps=unique(count,'planned_datasets'), count_models=count.model.nunique(),
        count_datasets=int(count[['design','scenario','planned_datasets']].drop_duplicates().planned_datasets.sum()),
        paired_scenarios=paired.scenario.nunique(), paired_reps=unique(paired,'datasets'),
        paired_genes=unique(paired,'genes'),
        paired_configs=len(paired[['weight_mode','test']].drop_duplicates()),
        paired_datasets=int(paired[['scenario','datasets']].drop_duplicates().datasets.sum()),
        tail_scenarios=tail.scenario.nunique(), tail_reps=unique(tail,'datasets'), tail_arms=tail.arm.nunique(),
        tail_configs=len(tail[['arm','test']].drop_duplicates()),
        tail_datasets=int(tail[['scenario','datasets']].drop_duplicates().datasets.sum()),
        human_planned=int(family['original']), human_available=int(clinical.n.sum()),
        contrast_family=int(family['by_contrast']), context_family=int(family['by_context']),
        panel=int(family['by_context_contrast']), specs=mouse.spec.nunique(),
        precision_pairs=int(mouse[mouse.model.eq('baseline')].planned.sum()),
        cage_fits=int(sections['S15.3'].planned.sum()),
    )
    v['panel_per_arm'] = v['panel']*v['specs']
    v['panel_two'] = v['panel_per_arm']*2
    v['panel_three'] = v['panel_per_arm']*3
    return {entry['id']:pd.DataFrame(
        [[cell.format(**v) for cell in row] for row in entry['rows']], columns=entry['columns'])
        for entry in specification}
