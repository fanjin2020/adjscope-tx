"""Regression and failure-mode checks for the S11 independent comparison."""
from contextlib import redirect_stdout
from io import StringIO
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from adjscope_tx import cli
from adjscope_tx.storage import ROOT, sha256
from validation import paired_limma as check


class PairedLimmaCheckTests(unittest.TestCase):
    def test_reproducible_fixture_matches_the_published_design(self):
        x0, x1, w, y, genes, wire = check.fixture()
        self.assertEqual((x0.shape, x1.shape, y.shape), ((48, 3), (48, 5), (48, 12)))
        self.assertEqual(len(genes), 12)
        self.assertTrue((w > 0).all())
        self.assertEqual(wire, check.fixture()[-1])
        from_csv = np.loadtxt(StringIO(wire), delimiter=",", skiprows=1)
        np.testing.assert_array_equal(from_csv, np.column_stack((x1, w, y)))

    def test_server_receipt_describes_this_kernel_and_not_a_smoke_run(self):
        record = json.loads((ROOT/"validation/paired_limma_reference.json").read_text(encoding="utf-8"))
        self.assertEqual((record["samples"],record["genes"],record["seed"]),(check.N,check.G,check.SEED))
        self.assertEqual(record["status"],"PASS_LOCKED")
        self.assertTrue(record["locked_environment_checked"])
        self.assertEqual(record["absolute_tolerance_strictly_below"],check.TOL)
        for key in ("max_abs_difference_coefficient","max_abs_difference_standard_error"):
            self.assertLess(record[key],check.TOL)
        # Git checkout on Windows may translate source line endings.
        import hashlib
        for name in check.KERNEL_FILES:
            original = record["repository_file_sha256"][name]
            normalized = hashlib.sha256((ROOT/name).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
            self.assertIn(original, {sha256(ROOT/name), normalized})

    def test_misaligned_genes_and_r_version_mismatch_are_not_passes(self):
        result = subprocess.CompletedProcess([], 0, stdout="VERSIONS\t4.5.3\t3.66.0\ngene,delta,se\nwrong,0,1\n", stderr="")
        with patch.object(check.subprocess,"run",return_value=result):
            with self.assertRaisesRegex(ValueError,"misaligned"):
                check.reference("Rscript",[], "",["expected"],None)
            with self.assertRaisesRegex(ValueError,"preflight"):
                check.reference("Rscript",[], "",["wrong"],{"R":"4.5.3","packages":{"limma":"wrong"}})

    def test_numerical_disagreement_is_a_failure_even_in_smoke_mode(self):
        with patch.object(check, "reference", return_value=(np.ones((check.G,2)), "local", "local")):
            result=check.check("Rscript",[],None)
        self.assertEqual(result["status"],"FAIL")
        self.assertFalse(result["locked_environment_checked"])

    def test_no_implicit_downgrade_and_no_overwrite(self):
        args=cli.parser().parse_args(["check-limma","--rscript","unused"])
        self.assertFalse(args.smoke)
        with patch("pipeline.environment.python_snapshot", side_effect=ValueError("pin mismatch")), patch.object(check,"check") as calc:
            with self.assertRaisesRegex(ValueError,"pin mismatch"):
                check.run(args)
            calc.assert_not_called()
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"receipt.json";p.write_text("keep")
            with self.assertRaises(FileExistsError):
                cli.main(["check-limma","--output",str(p)])
            self.assertEqual(p.read_text(),"keep")

    @unittest.skipUnless(os.environ.get("ADJSCOPE_TEST_R"),"set ADJSCOPE_TEST_R for independent R/limma fit")
    def test_local_limma_invocation_is_explicitly_nonlocked(self):
        args=["check-limma", "--smoke", "--rscript", os.environ["ADJSCOPE_TEST_R"]]
        for lib in os.environ.get("ADJSCOPE_TEST_R_LIBRARY","").split(os.pathsep):
            if lib:args.extend(["--r-library",lib])
        buf=StringIO()
        with redirect_stdout(buf):
            self.assertEqual(cli.main(args),0)
        record=json.loads(buf.getvalue())
        self.assertEqual(record["status"],"SMOKE_PASS_NOT_LOCKED")
        self.assertLess(max(record["max_abs_difference_coefficient"],record["max_abs_difference_standard_error"]),check.TOL)
