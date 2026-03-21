from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
from pathlib import Path

from simulator.core.defaults import (
    make_default_feed,
    make_default_initial_state,
    make_default_kinetics,
    make_default_operating_conditions,
    make_default_simulation_config,
)
from simulator.design_pipeline import ADM1DesignPipeline
from simulator.mcp_server import compare_backends as mcp_compare_backends
from simulator.scenario_store import ScenarioStore
from simulator.service import ADM1SimulationService
from webapp.services.simulation_service import get_backend_options, resolve_requested_backend

WORKSPACE_TMP = Path("simulator") / "tests" / ".tmp"
WORKSPACE_TMP.mkdir(parents=True, exist_ok=True)


def _make_service() -> tuple[ADM1SimulationService, Path]:
    tmpdir = Path(tempfile.mkdtemp(dir=WORKSPACE_TMP))
    return ADM1SimulationService(store=ScenarioStore(tmpdir)), tmpdir


def test_phase5_backend_options_include_full_and_resolve_fallbacks() -> None:
    options = get_backend_options()

    assert "full" in options
    assert resolve_requested_backend("cstr", "full")[0] == "full"
    assert resolve_requested_backend("uasb", "full")[0] == "reduced"
    assert resolve_requested_backend("cstr", "auto")[0] == "pyadm1"


def test_phase5_service_compare_backends_for_cstr_full_vs_pyadm1() -> None:
    service, tmpdir = _make_service()
    try:
        simulation = make_default_simulation_config().model_copy(
            update={"duration_days": 4.0, "evaluation_points": 31, "persist": False}
        )
        report = service.compare_backends(
            ["pyadm1", "full"],
            reactor="cstr",
            operating_conditions=make_default_operating_conditions(),
            feed=make_default_feed(),
            initial_state=make_default_initial_state(make_default_feed()),
            parameters=make_default_kinetics(),
            simulation=simulation,
        )

        used = {entry["backend_used"] for entry in report["entries"]}
        assert report["baseline_backend"] == "pyadm1"
        assert len(report["entries"]) == 2
        assert used == {"pyadm1", "full"}
        assert report["reduced_is_exploratory"] is False
        assert report["note"] is None
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_phase5_design_pipeline_accepts_full_and_reports_fallbacks() -> None:
    service, tmpdir = _make_service()
    note_root = Path(tempfile.mkdtemp(dir=WORKSPACE_TMP))
    try:
        pipeline = ADM1DesignPipeline(service=service, note_root=note_root)
        report = pipeline.run(
            substrate="lodo_de_esgoto",
            design_goal="balanced",
            backend="full",
            reactor_candidates=["cstr", "plug_flow"],
            duration_days=5.0,
            evaluation_points=31,
            persist_note=False,
        )

        candidates = {candidate["reactor_type"]: candidate for candidate in report["candidates"]}
        assert candidates["cstr"]["backend_requested"] == "full"
        assert candidates["cstr"]["backend_used"] == "full"
        assert candidates["plug_flow"]["backend_requested"] == "full"
        assert candidates["plug_flow"]["backend_used"] == "reduced"
        assert candidates["plug_flow"]["fallback_reason"]
        assert report["reduced_is_exploratory"] is True
        assert report["backend_policy_note"]
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
        shutil.rmtree(note_root, ignore_errors=True)


def test_phase5_mcp_compare_backends_returns_full_and_pyadm1_entries() -> None:
    payload = json.loads(
        asyncio.run(
            mcp_compare_backends(
                reactor_type="cstr",
                backends=["pyadm1", "full"],
                duration_days=4.0,
            )
        )
    )

    used = {entry["backend_used"] for entry in payload["entries"]}
    assert payload["baseline_backend"] == "pyadm1"
    assert len(payload["entries"]) == 2
    assert used == {"pyadm1", "full"}
