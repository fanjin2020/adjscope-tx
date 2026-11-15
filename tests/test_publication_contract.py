"""Missing products, extra files and stale display tables must fail validation."""
import csv
from pathlib import Path
import shutil
import tempfile
import unittest

from adjscope_tx.publication import Bundle
from adjscope_tx.storage import ROOT


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'evidence'
        shutil.copytree(ROOT/'inputs/evidence',self.root)

    def rewrite(self,entries):
        with (self.root/'manifest.csv').open('w',newline='',encoding='utf-8') as f:
            writer=csv.DictWriter(f,fieldnames=list(entries[0]));writer.writeheader();writer.writerows(entries)

    def test_removed_table_and_manifest_records_are_rejected(self):
        bundle=Bundle(self.root)
        self.rewrite([e for e in bundle.entries if not (e['kind']=='table' and e['id'].startswith('S23.'))])
        (self.root/'tables/TableS23.csv.gz').unlink()
        with self.assertRaisesRegex(ValueError,'Incomplete publication'):Bundle(self.root).verify()

    def test_undeclared_result_is_rejected(self):
        (self.root/'old_duplicate.csv').write_text('value\n1\n')
        with self.assertRaisesRegex(ValueError,'Unexpected'):Bundle(self.root).verify()

    def test_subset_manifest_cannot_claim_full_workflow(self):
        entries=Bundle(self.root).entries
        next(e for e in entries if e['kind']=='contract')['scope']='counts'
        self.rewrite(entries)
        with self.assertRaisesRegex(ValueError,'stages differ'):
            Bundle(self.root).verify(expected_stages=('study','design','counts','tails'))

    def test_aliases_are_explicit_and_stable(self):
        b=Bundle(self.root).verify()
        self.assertEqual(b.entry('figure_data','icc_strata')['file'],b.entry('table','S15.4')['file'])
        self.assertEqual(b.entry('table','S20.7')['section'],'S17.7')
        self.assertEqual(len(list((self.root/'figure_data').glob('*'))),8)
        self.assertEqual(len([e for e in b.entries if e['kind']=='main_table']),3)

    def test_main_tables_use_analysis_cohorts_not_subsampling_designs(self):
        b=Bundle(self.root).verify()
        main=b.read('main_table','1')
        human=main[main.Component.eq('SEA-AD')].iloc[0]
        self.assertEqual(human['Units and conditions'],'80 donors; 24 contexts; 21-80 donors/context')
        family=b.read('main_table','3').iloc[0]
        self.assertEqual(family['Planned positions or fits'],'24 contexts x 3 contrasts x 237 genes = 17,064 per arm')

    def test_plot_projection_cannot_silently_drop_columns(self):
        entries=Bundle(self.root).entries
        next(e for e in entries if e['kind']=='figure_data' and e['id']=='count_summary')['columns']='[]'
        self.rewrite(entries)
        with self.assertRaisesRegex(ValueError,'columns differ'):Bundle(self.root).verify()


if __name__=='__main__':unittest.main()
