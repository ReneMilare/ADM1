from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from simulator.core.defaults import make_default_simulation_config
from simulator.scenario_store import ScenarioStore
from simulator.service import ADM1SimulationService

WORKSPACE_TMP = Path("simulator") / "tests" / ".tmp"
WORKSPACE_TMP.mkdir(parents=True, exist_ok=True)


class ADM1SimulationServiceTest(unittest.TestCase):
    def test_simulation_returns_profiles(self) -> None:
        tmpdir = Path(tempfile.mkdtemp(dir=WORKSPACE_TMP))
        try:
            service = ADM1SimulationService(store=ScenarioStore(tmpdir))
            simulation = make_default_simulation_config().model_copy(update={"duration_days": 20.0, "evaluation_points": 81, "persist": False})
            result = service.simulate("cstr", simulation=simulation)
            self.assertEqual(len(result.time_days), 81)
            self.assertGreater(result.summary.methane_final_m3_day, 0.0)
            self.assertIn("ph", result.series)
            self.assertIn("vfa_total", result.series)
            self.assertEqual(result.metadata["backend_requested"], "pyadm1")
            self.assertEqual(result.metadata["backend_used"], "pyadm1")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_reactor_types_diverge(self) -> None:
        tmpdir = Path(tempfile.mkdtemp(dir=WORKSPACE_TMP))
        try:
            service = ADM1SimulationService(store=ScenarioStore(tmpdir))
            simulation = make_default_simulation_config().model_copy(update={"duration_days": 20.0, "evaluation_points": 61, "persist": False})
            cstr = service.simulate("cstr", simulation=simulation)
            uasb = service.simulate("uasb", simulation=simulation)
            pfr = service.simulate("plug_flow", simulation=simulation)
            methane_values = {
                round(cstr.summary.methane_final_m3_day, 6),
                round(uasb.summary.methane_final_m3_day, 6),
                round(pfr.summary.methane_final_m3_day, 6),
            }
            self.assertGreater(len(methane_values), 1)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_persisted_roundtrip(self) -> None:
        store = ScenarioStore(WORKSPACE_TMP)
        service = ADM1SimulationService(store=store)
        simulation = make_default_simulation_config().model_copy(update={"duration_days": 10.0, "evaluation_points": 41, "persist": True})
        result = service.simulate("cstr", simulation=simulation)
        try:
            loaded = service.get_result(result.simulation_id)
            self.assertEqual(loaded.simulation_id, result.simulation_id)
            self.assertEqual(len(loaded.time_days), 41)
            self.assertTrue(store.path_for(result.simulation_id).exists())
        finally:
            store.path_for(result.simulation_id).unlink(missing_ok=True)

    def test_pyadm1_backend_smoke_for_cstr(self) -> None:
        tmpdir = Path(tempfile.mkdtemp(dir=WORKSPACE_TMP))
        try:
            service = ADM1SimulationService(store=ScenarioStore(tmpdir))
            simulation = make_default_simulation_config().model_copy(
                update={"duration_days": 5.0, "evaluation_points": 21, "persist": False, "backend": "pyadm1"}
            )
            result = service.simulate("cstr", simulation=simulation)
            self.assertEqual(result.metadata["backend_requested"], "pyadm1")
            self.assertEqual(result.metadata["backend_used"], "pyadm1")
            self.assertEqual(len(result.time_days), 21)
            self.assertEqual(len(result.series["methane_m3_day"]), 21)
            self.assertIn("pyadm1_runtime", result.metadata)
            self.assertGreaterEqual(result.summary.biogas_final_m3_day, 0.0)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_pyadm1_request_falls_back_for_non_cstr(self) -> None:
        tmpdir = Path(tempfile.mkdtemp(dir=WORKSPACE_TMP))
        try:
            service = ADM1SimulationService(store=ScenarioStore(tmpdir))
            simulation = make_default_simulation_config().model_copy(
                update={"duration_days": 10.0, "evaluation_points": 41, "persist": False, "backend": "pyadm1"}
            )
            result = service.simulate("uasb", simulation=simulation)
            self.assertEqual(result.metadata["backend_requested"], "pyadm1")
            self.assertEqual(result.metadata["backend_used"], "reduced")
            self.assertIn("backend_fallback_reason", result.metadata)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
