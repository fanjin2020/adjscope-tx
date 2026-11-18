import csv
import gzip
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from adjscope_tx.publication import Bundle
from adjscope_tx.storage import ROOT


def read(name):
    key={'tail_summary':'S23.1','count_summary':'S22.1'}[name]
    return Bundle(ROOT/'inputs/evidence').read('table',key).to_dict('records')


class CalibrationPublicationTests(unittest.TestCase):
    def test_complete_inputs(self):
        Bundle(ROOT/'inputs/evidence').verify()
        self.assertEqual(len(read('count_summary')),96)
        self.assertEqual(len(read('tail_summary')),72)

    def test_gaussian_headline(self):
        rows = read('tail_summary')
        r = next(r for r in rows if (r['scenario'], r['arm'], r['test']) == ('s09', 'gaussian_unit', 'HC3'))
        self.assertAlmostEqual(float(r['fdp_planned_050']), .108)
        self.assertAlmostEqual(float(r['bonferroni_fwer']), .106)
        self.assertGreater(float(r['coverage95']), .95)
        self.assertGreater(float(r['fdp_planned_050_ci_low']), .05)

    def test_checksums_reject_changed_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'source'
            shutil.copytree(ROOT/'inputs/evidence', root)
            path = root / 'tables/TableS22.csv.gz'
            path.write_bytes(path.read_bytes() + b'x')
            with self.assertRaisesRegex(ValueError, 'changed'):
                Bundle(root).verify()

    def test_output_safety_and_separate_families(self):
        from adjscope_tx.reports import export_publication
        from adjscope_tx.publication import Bundle
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'report'
            export_publication(out)
            frame = Bundle(out).read('table','S23.1')
            rows = frame[frame.arm.eq('gaussian_unit') & frame.test.eq('HC3')]
            self.assertGreater(rows.fdp_retained_050.max(), rows.fdp_planned_050.max())
            with self.assertRaises(ValueError):
                export_publication(out)


if __name__ == '__main__':
    unittest.main()
