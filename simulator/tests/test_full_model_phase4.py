from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from simulator.core.defaults import make_default_feed, make_default_initial_state, make_default_kinetics, make_default_operating_conditions, make_default_simulation_config
from simulator.core.models import OperatingConditions, SimulationConfig
from simulator.full_model.adapter import build_backend_inputs_from_state_maps
from simulator.full_model.extension_registry import list_registered_extensions, resolve_full_model_assembly
from simulator.full_model.model import FULL_STATE_NAMES
from simulator.full_model.process_catalog import FULL_PROCESS_NAMES
from simulator.full_model.solver import simulate_with_full_inputs
from simulator.scenario_store import ScenarioStore
from simulator.service import ADM1SimulationService

WORKSPACE_TMP = Path("simulator") / "tests" / ".tmp"
WORKSPACE_TMP.mkdir(parents=True, exist_ok=True)


def _make_service():
    tmpdir = Path(tempfile.mkdtemp(dir=WORKSPACE_TMP))
    return ADM1SimulationService(store=ScenarioStore(tmpdir)), tmpdir


def test_full_assembly_without_extensions_matches_base_catalog() -> None:
    assembly = resolve_full_model_assembly([])
    assert assembly.active_extensions == ()
    assert assembly.full_state_names == FULL_STATE_NAMES
    assert assembly.full_process_names == FULL_PROCESS_NAMES
    assert len(assembly.full_state_names) == 38
    assert len(assembly.dynamic_state_names) == 29
    assert set(list_registered_extensions()) == {"pilot_tracer", "lactate", "ethanol", "phenolics", "lcfa_adsorption", "srb"}



def test_pilot_extension_adds_state_process_parameter_and_diagnostics() -> None:
    operating_conditions = OperatingConditions(volume_m3=3400.0, temperature_c=35.0, hrt_days=20.0)
    influent = {name: 0.0 for name in FULL_STATE_NAMES}
    influent.update({"S_IC": 0.04, "S_IN": 0.01, "S_cation": 0.04, "S_anion": 0.02, "Q": 170.0, "X_tracer": 0.0})
    initial = dict(influent)
    initial["X_tracer"] = 1.0
    inputs = build_backend_inputs_from_state_maps(
        operating_conditions=operating_conditions,
        parameters=make_default_kinetics(),
        influent_values=influent,
        initial_values=initial,
        flow_rate_m3_day=170.0,
        active_extensions=["pilot_tracer"],
        extension_parameter_overrides={"k_decay_tracer": 0.6},
    )
    simulation = SimulationConfig(
        duration_days=4.0,
        evaluation_points=41,
        solver="BDF",
        backend="full",
        persist=False,
        full_extensions=["pilot_tracer"],
        full_extension_parameter_overrides={"k_decay_tracer": 0.6},
    )

    result = simulate_with_full_inputs(inputs=inputs, simulation=simulation)

    assert result["metadata"]["full_model_active_extensions"] == ["pilot_tracer"]
    assert "X_tracer" in result["metadata"]["full_state_columns"]
    assert "pilot_tracer_inventory" in result["profiles"]
    assert result["profiles"]["pilot_tracer_inventory"][0] > result["profiles"]["pilot_tracer_inventory"][-1]
    assert result["profiles"]["pilot_tracer_fraction_remaining"][-1] < 1.0
    assert result["profiles"]["X_I"][-1] > result["profiles"]["X_I"][0]



def test_service_exposes_full_extension_activation_metadata() -> None:
    service, tmpdir = _make_service()
    try:
        simulation = make_default_simulation_config().model_copy(
            update={
                "duration_days": 3.0,
                "evaluation_points": 21,
                "persist": False,
                "backend": "full",
                "full_extensions": ["pilot_tracer"],
            }
        )
        result = service.simulate(
            "cstr",
            operating_conditions=make_default_operating_conditions(),
            feed=make_default_feed(),
            initial_state=make_default_initial_state(make_default_feed()),
            parameters=make_default_kinetics(),
            simulation=simulation,
        )
        assert result.metadata["backend_used"] == "full"
        assert result.metadata["full_model_active_extensions"] == ["pilot_tracer"]
        assert "X_tracer" in result.metadata["full_state_columns"]
        assert len(result.metadata["full_state_columns"]) == 39
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
