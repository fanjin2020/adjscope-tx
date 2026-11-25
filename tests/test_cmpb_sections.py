"""The two CMPB tables come from the selected study, not a frozen lookup."""
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from adjscope_tx import cmpb_sections as cmpb
from adjscope_tx.publication import Computed
from adjscope_tx.storage import sha256, write_json


class StudySupplementTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        attempt = self.root / 'supplementary/bulk/attempt_007'
        attempt.mkdir(parents=True)
        regions = list(reversed(cmpb.REGIONS))
        design = pd.DataFrame(dict(region=regions, model='overlap_log2_linear',
                                   status='tested', AD=[7, 12], control=[3, 8]))
        endpoints = pd.DataFrame(dict(region=regions, model='overlap_log2_linear', tested=[30, 100],
                                      same=[20, 85], significant_same=[1, 3], significant_opposite=[2, 1]))
        for name, frame in zip(cmpb.BULK, (design, endpoints.iloc[::-1])):
            pd.concat([frame, frame.assign(model='other')]).to_csv(attempt/name, index=False)
        self.receipt = self.root/'supplementary/bulk.complete.json'
        write_json(self.receipt, dict(directory='/old/server/study/supplementary/bulk/attempt_007',
                   files={'bulk/attempt_007/'+n:sha256(attempt/n) for n in cmpb.BULK}))
        report = self.root/'reporting'
        (report/'S11').mkdir(parents=True)
        self.libs = pd.DataFrame(dict(gsm=list(cmpb.LIBRARIES), seed=290, qc_cells=100,
            predicted_doublets=[12, 20, 37], predicted_fraction=[.12, .20, .37],
            status='completed_risk_screen_not_doublet_truth'))
        libfile = 'S11/doublet_libraries.csv'
        pd.concat([self.libs.iloc[::-1],self.libs.assign(seed=291),self.libs.iloc[:1].assign(gsm='other')]).to_csv(
            report/libfile, index=False)
        pd.DataFrame([dict(file=libfile, sha256=sha256(report/libfile))]).to_csv(report/'source_index.csv',index=False)
        pd.DataFrame(columns=['block','file']).to_csv(report/'block_sources.csv',index=False)
        self.provider = Computed({'study':self.root})

    def table(self, key):
        return self.provider.table(dict(id=key, stage='study', **cmpb.EXTRA[key]))

    def test_computed_rows_follow_the_supplied_study(self):
        self.assertEqual(list(self.table('S9.5').itertuples(index=False,name=None)), [
            (cmpb.REGIONS[0],12,8,20,100,85,4), (cmpb.REGIONS[1],7,3,10,30,20,3)])
        f = self.table('S11.7')
        self.assertEqual(list(f['GEO library']),list(cmpb.LIBRARIES))
        self.assertEqual(list(f['predicted fraction']),[.12,.20,.37])
        self.provider.verify_unchanged()

    def test_missing_receipt_has_no_replay_fallback(self):
        self.receipt.unlink()
        with self.assertRaisesRegex(ValueError,'bulk.complete'):
            self.table('S9.5')

    def test_changed_attempt_file_is_rejected(self):
        p=self.root/'supplementary/bulk/attempt_007'/cmpb.BULK[0]
        with p.open('ab') as f: f.write(b'\n')
        with self.assertRaisesRegex(ValueError,'checksum mismatch'):
            self.table('S9.5')

    def test_missing_and_duplicate_provenance_keys_are_rejected(self):
        for f in (self.libs.iloc[:2], pd.concat([self.libs,self.libs.iloc[:1]]), self.libs.assign(seed=291)):
            with self.assertRaisesRegex(ValueError,'missing, duplicate'):
                cmpb.doublet_summary(f)
        with self.assertRaisesRegex(ValueError,'fingerprint'):
            cmpb.receipt_members({'directory':'/elsewhere/bulk/attempt_001','files':{}})
        with self.assertRaisesRegex(ValueError,'invalid bulk attempt'):
            cmpb.receipt_members({'directory':'../../elsewhere','files':{}})

    def test_fractions_must_match_counts(self):
        with self.assertRaisesRegex(ValueError,'fraction disagrees'):
            cmpb.doublet_summary(self.libs.assign(predicted_fraction=.40))
