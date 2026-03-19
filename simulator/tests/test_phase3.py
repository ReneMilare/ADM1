from __future__ import annotations

import shutil
import unittest
from pathlib import Path

from simulator.design_pipeline import ADM1DesignPipeline
from simulator.validation import run_phase3_validation

WORKSPACE_TMP = Path("simulator") / "tests" / ".tmp"
WORKSPACE_TMP.mkdir(parents=True, exist_ok=True)
PHASE3_ARTIFACTS = [
    "backend_benchmark.json",
    "backend_benchmark.md",
    "openmodelica_scenarios.json",
    "phase3_validation.json",
    "phase3_validation.md",
]


class Phase3ValidationTest(unittest.TestCase):
    def tearDown(self) -> None:
        for name in PHASE3_ARTIFACTS:
            (WORKSPACE_TMP / name).unlink(missing_ok=True)
        for note_path in WORKSPACE_TMP.glob("estudo_de_teste*.md"):
            note_path.unlink(missing_ok=True)

    def test_validation_report_runs_without_openmodelica(self) -> None:
        report, output_dir = run_phase3_validation(output_root=WORKSPACE_TMP)
        self.assertEqual(output_dir.resolve(), WORKSPACE_TMP.resolve())
        self.assertTrue((output_dir / "phase3_validation.json").exists())
        self.assertTrue((output_dir / "phase3_validation.md").exists())
        self.assertIn(report["openmodelica"]["status"], {"toolchain_not_available", "partial_toolchain", "model_not_configured", "ready"})
        self.assertTrue(report["conclusion"]["phase3_local_validation_complete"])
        self.assertIn("prefer_pyadm1_for_cstr_fidelity", report["conclusion"])

    def test_design_pipeline_returns_ranked_candidates(self) -> None:
        pipeline = ADM1DesignPipeline(note_root=WORKSPACE_TMP)
        report = pipeline.run(substrate="Lodo de Esgoto", design_goal="balanced", backend="auto", persist_note=False)
        self.assertIn(report["recommended_reactor"], {"cstr", "uasb", "plug_flow"})
        self.assertEqual(len(report["candidates"]), 3)
        self.assertEqual(report["candidates"][0]["reactor_type"], report["recommended_reactor"])
        self.assertIsNone(report["note_path"])

    def test_design_pipeline_can_persist_note(self) -> None:
        pipeline = ADM1DesignPipeline(note_root=WORKSPACE_TMP)
        report = pipeline.run(
            substrate="Residuos Alimentares",
            design_goal="maximize_methane",
            backend="auto",
            persist_note=True,
            note_title="Estudo de Teste",
        )
        note_path = Path(report["note_path"])
        self.assertTrue(note_path.exists())
        self.assertIn("Estudo de Teste", note_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
