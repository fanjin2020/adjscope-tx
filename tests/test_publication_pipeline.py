"""Publication data contracts: current results, not fallback snapshot values."""
import csv
import gzip
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd
from pandas.testing import assert_frame_equal

from adjscope_tx.publication import Bundle, Computed, SCHEMA, write_bundle
from adjscope_tx.storage import ROOT, write_json, sha256
from evidence_helpers import stage_frame


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.counts=self.root/'counts'
        self.counts.mkdir()
        stage_frame('count_summary').to_csv(self.counts/'summary.csv',index=False)
        self.receipt()

    def receipt(self):
        write_json(self.counts/'review_manifest.json',{'summary.csv':sha256(self.counts/'summary.csv')})

    def test_changed_current_value_reaches_table_and_plot_input(self):
        frame=pd.read_csv(self.counts/'summary.csv')
        frame.loc[0,'fdp_planned_050']=.321
        frame.to_csv(self.counts/'summary.csv',index=False)
        self.receipt()
        result=write_bundle(Computed({'counts':self.counts}),self.root/'result')
        bundle=Bundle(result).verify()
        self.assertAlmostEqual(bundle.read('table','S22.1').fdp_planned_050.iloc[0],.321)
        self.assertAlmostEqual(bundle.read('figure_data','paired_count_summary').fdp_planned_050.iloc[0],.321)
        self.assertFalse((result/'tables/TableS21.csv').exists())
        self.assertNotIn('9',bundle.figures())
        self.assertEqual(set(bundle.figures()), {'S9','S14'})

    def test_plot_column_subset_reuses_identical_table_rows(self):
        import copy
        from adjscope_tx import publication
        schema = copy.deepcopy(SCHEMA)
        table = next(e for e in schema['tables'] if e['id'] == 'S22.1')
        plot = next(e for e in schema['figure_data'] if e['id'] == 'paired_count_summary')
        plot['columns'] = [c for c in plot['columns'] if c in table['columns']][:3]
        self.assertTrue(plot['columns'])
        with patch.object(publication, 'SCHEMA', schema):
            result = write_bundle(Computed({'counts':self.counts}), self.root/'result')
            bundle = Bundle(result).verify()
            self.assertEqual(bundle.entry('figure_data','paired_count_summary')['file'], 'tables/TableS22.csv')
            self.assertFalse((result/'figure_data/paired_count_summary.csv').exists())

    def test_no_snapshot_fallback_when_computed_input_is_missing(self):
        (self.counts/'summary.csv').unlink()
        with self.assertRaisesRegex(ValueError,'Missing'):
            write_bundle(Computed({'counts':self.counts}),self.root/'result')
        self.assertFalse((self.root/'result').exists())

    def test_bad_source_checksum_rejected(self):
        with (self.counts/'summary.csv').open('a') as f:f.write('\n')
        with self.assertRaisesRegex(ValueError,'checksum'):
            write_bundle(Computed({'counts':self.counts}),self.root/'result')

    def test_changed_csv_detected_before_plotting(self):
        result=write_bundle(Computed({'counts':self.counts}),self.root/'result')
        with (result/'tables/TableS22.csv').open('a') as f:f.write('\n')
        with self.assertRaisesRegex(ValueError,'changed'):
            Bundle(result).verify()

    def test_schema_contains_all_required_figure9_and_paired_controls(self):
        self.assertIn('design_empirical_design_diagnostics',{e['id'] for e in SCHEMA['figure_data']})
        self.assertTrue({'S21.5','S21.6'}.issubset({e['id'] for e in SCHEMA['tables']}))

    def test_declared_dependencies_match_all_renderer_reads(self):
        import importlib.util
        import sys
        folder = ROOT/'publication_figures'
        spec = importlib.util.spec_from_file_location('publication_dependency_test', folder/'make_figures.py')
        module = importlib.util.module_from_spec(spec)
        seen = set()
        def read(name):
            seen.add(name)
            return Bundle(ROOT/'inputs/evidence').read('figure_data',name)
        with patch.object(sys, 'path', [str(folder), *sys.path]), patch.dict(sys.modules, {spec.name:module}):
            spec.loader.exec_module(module)
            module.style()
            with patch.object(module, 'read', side_effect=read), \
                 patch.object(module, 'export', side_effect=lambda fig, name:module.plt.close(fig)):
                for figure in SCHEMA['figures']:
                    seen.clear()
                    module.FUNCTIONS[figure]()
                    declared = {e['id'] for e in SCHEMA['figure_data'] if figure in e['figures']}
                    self.assertEqual(seen, declared, 'Figure '+figure)

    def test_calibration_renderer_reads_supplied_context(self):
        from publication_figures import calibration_figures
        class Context:
            def read(self,name):return name
        self.assertEqual(calibration_figures.read(Context(),'tail_summary'),'paired_tail_summary')

    def test_no_extra_products_or_private_paths_in_final_export(self):
        result=write_bundle(Computed({'counts':self.counts}),self.root/'result')
        self.assertTrue(all(p.suffix=='.csv' for p in result.rglob('*') if p.is_file()))
        text=(result/'manifest.csv').read_text(encoding='utf-8')
        self.assertNotIn(str(self.root),text)

    def test_rendered_clinical_counts_are_not_hardcoded(self):
        import importlib.util
        import sys
        import numpy as np
        folder=ROOT/'publication_figures'
        spec=importlib.util.spec_from_file_location('publication_renderer_test',folder/'make_figures.py')
        module=importlib.util.module_from_spec(spec)
        with patch.object(sys,'path',[str(folder),*sys.path]):
            spec.loader.exec_module(module)
        frame=pd.DataFrame(dict(q_joint_base=[.01,.02,.2],q_joint_quality=[.03,.8,.4],
                                beta_base=[-.2,.4,.5],beta_quality=[-.1,.3,.6]))
        with patch.object(module,'read',return_value=frame),patch.object(module,'export') as save:
            module.fig5()
        fig=save.call_args.args[0]
        self.assertIn('2 base-significant',fig.axes[0].get_ylabel())
        self.assertIn('3 clinical',fig.axes[1].get_title(loc='left'))
        self.assertEqual(sum(p.get_height() for p in fig.axes[2].patches),4)
        module.plt.close(fig)

    def test_expanded_numeric_axes_receive_new_ticks(self):
        import importlib.util
        import sys
        folder=ROOT/'publication_figures'
        spec=importlib.util.spec_from_file_location('publication_renderer_ticks',folder/'make_figures.py')
        module=importlib.util.module_from_spec(spec)
        with patch.object(sys,'path',[str(folder),*sys.path]):spec.loader.exec_module(module)
        module.OUT=self.root;module.PDF_ONLY=True
        fig,ax=module.plt.subplots()
        ax.scatter([0,100],[0,1]);ax.set_xlim(0,15);ax.set_xticks([0,5,10,15])
        with patch.object(fig,'savefig'):
            module.export(fig,'test')
        self.assertGreater(ax.get_xlim()[1],100)
        self.assertGreater(max(ax.get_xticks()),90)


if __name__=='__main__':unittest.main()
