from __future__ import annotations

import shutil
import unittest
from pathlib import Path

from simulator.literature_validation import run_literature_validation

WORKSPACE_TMP = Path("simulator") / "tests" / "tmp_literature_validation"
WORKSPACE_TMP.mkdir(parents=True, exist_ok=True)


class LiteratureValidationTest(unittest.TestCase):
    def test_literature_validation_matches_bsm2_for_pyadm1(self) -> None:
        tmpdir = WORKSPACE_TMP / "case_pyadm1"
        shutil.rmtree(tmpdir, ignore_errors=True)
        tmpdir.mkdir(parents=True, exist_ok=False)
        try:
            report, output_dir = run_literature_validation(output_root=tmpdir)
            self.assertTrue((output_dir / "literature_validation.json").exists())
            self.assertTrue((output_dir / "literature_validation.md").exists())
            self.assertTrue(report["pyadm1"]["validated"])
            self.assertFalse(report["reduced"]["validated"])
            self.assertLess(report["conclusion"]["pyadm1_max_rel_delta_pct"], 0.1)
            self.assertGreater(report["conclusion"]["reduced_max_rel_delta_pct"], 10.0)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_literature_validation_uses_public_relative_sources(self) -> None:
        tmpdir = WORKSPACE_TMP / "case_sources"
        shutil.rmtree(tmpdir, ignore_errors=True)
        tmpdir.mkdir(parents=True, exist_ok=False)
        try:
            report, _ = run_literature_validation(output_root=tmpdir)
            initial_source = report["pyadm1"]["execution"]["initial_state_source"]
            self.assertEqual(initial_source, "vendor/PyADM1/src/digester_initial.csv")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
