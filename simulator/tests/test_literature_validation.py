from __future__ import annotations

import shutil
import unittest
from pathlib import Path

from simulator.literature_validation import run_literature_validation, write_vault_report

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
            self.assertLess(report["conclusion"]["pyadm1_max_rel_delta_pct"], 0.2)
            self.assertGreater(report["conclusion"]["reduced_max_rel_delta_pct"], 10.0)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_literature_validation_can_write_vault_note(self) -> None:
        tmpdir = WORKSPACE_TMP / "case_note"
        shutil.rmtree(tmpdir, ignore_errors=True)
        tmpdir.mkdir(parents=True, exist_ok=False)
        try:
            report, output_dir = run_literature_validation(output_root=tmpdir / "artifacts")
            note_path = write_vault_report(report, artifact_dir=output_dir, note_root=tmpdir / "notes")
            self.assertTrue(note_path.exists())
            note_text = note_path.read_text(encoding="utf-8-sig")
            self.assertIn("Validação contra Literatura BSM2", note_text)
            self.assertIn("Qgas", note_text)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
