from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import numpy as np
import pytest

from simulator.core.defaults import (
    make_default_feed,
    make_default_initial_state,
    make_default_kinetics,
    make_default_operating_conditions,
    make_default_simulation_config,
)
from simulator.full_model.acid_base import solve_acid_base
from simulator.core.models import OperatingConditions, SimulationConfig
from simulator.full_model.adapter import build_backend_inputs, build_backend_inputs_from_state_maps
from simulator.full_model.kinetics import BIOCHEMICAL_RATE_ORDER
from simulator.full_model.rhs import FullCSTRRhs
from simulator.full_model.solver import simulate_with_full_inputs
from simulator.scenario_store import ScenarioStore
from simulator.service import ADM1SimulationService

WORKSPACE_TMP = Path("simulator") / "tests" / ".tmp"
WORKSPACE_TMP.mkdir(parents=True, exist_ok=True)


def _make_service():
    tmpdir = Path(tempfile.mkdtemp(dir=WORKSPACE_TMP))
    return ADM1SimulationService(store=ScenarioStore(tmpdir)), tmpdir


def test_full_backend_smoke_for_cstr() -> None:
    service, tmpdir = _make_service()
    try:
        simulation = make_default_simulation_config().model_copy(
            update={"duration_days": 5.0, "evaluation_points": 21, "persist": False, "backend": "full"}
        )
        result = service.simulate("cstr", simulation=simulation)
        assert result.metadata["backend_requested"] == "full"
        assert result.metadata["backend_used"] == "full"
        assert len(result.time_days) == 21
        assert len(result.series["methane_m3_day"]) == 21
        assert len(result.metadata["full_state_columns"]) == 38
        assert len(result.metadata["full_dynamic_state_columns"]) == 29
        assert len(result.metadata["final_internal_state"]) == 38
        assert result.metadata["full_model_runtime"] == "native"
        assert result.metadata["full_model_ph_converged"] is True
        assert result.summary.methane_final_m3_day > 0.0
        assert 5.0 <= result.summary.ph_final <= 8.5
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_full_backend_accepts_dop853_solver() -> None:
    operating_conditions = OperatingConditions(volume_m3=3400.0, temperature_c=35.0, hrt_days=20.0)
    state_names = [
        "S_su", "S_aa", "S_fa", "S_va", "S_bu", "S_pro", "S_ac", "S_h2", "S_ch4", "S_IC", "S_IN", "S_I",
        "X_xc", "X_ch", "X_pr", "X_li", "X_su", "X_aa", "X_fa", "X_c4", "X_pro", "X_ac", "X_h2", "X_I",
        "S_cation", "S_anion", "S_H_ion", "S_va_ion", "S_bu_ion", "S_pro_ion", "S_ac_ion", "S_hco3_ion",
        "S_co2", "S_nh3", "S_nh4_ion", "S_gas_h2", "S_gas_ch4", "S_gas_co2",
    ]
    influent = {name: 0.0 for name in state_names}
    influent.update({"S_IC": 0.04, "S_IN": 0.01, "S_cation": 0.04, "S_anion": 0.02, "Q": 170.0})
    inputs = build_backend_inputs_from_state_maps(
        operating_conditions=operating_conditions,
        parameters=make_default_kinetics(),
        influent_values=influent,
        initial_values=dict(influent),
        flow_rate_m3_day=170.0,
    )
    simulation = SimulationConfig(
        duration_days=0.25,
        evaluation_points=21,
        solver="DOP853",
        backend="full",
        rtol=1e-8,
        atol=1e-10,
        persist=False,
    )
    result = simulate_with_full_inputs(inputs=inputs, simulation=simulation)
    assert len(result["time_days"]) == 21
    assert len(result["profiles"]["ph"]) == 21
    assert result["metadata"]["solver_status"]


def test_full_backend_persistence_roundtrip() -> None:
    service = ADM1SimulationService(store=ScenarioStore(WORKSPACE_TMP))
    simulation = make_default_simulation_config().model_copy(
        update={"duration_days": 4.0, "evaluation_points": 21, "persist": True, "backend": "full"}
    )
    result = service.simulate("cstr", simulation=simulation)
    try:
        loaded = service.get_result(result.simulation_id)
        assert loaded.simulation_id == result.simulation_id
        assert loaded.metadata["backend_used"] == "full"
        assert len(loaded.metadata["full_state_columns"]) == 38
        assert len(loaded.metadata["final_internal_state"]) == 38
        assert service.store.path_for(result.simulation_id).exists()
    finally:
        service.store.path_for(result.simulation_id).unlink(missing_ok=True)


def test_full_request_falls_back_for_non_cstr() -> None:
    service, tmpdir = _make_service()
    try:
        simulation = make_default_simulation_config().model_copy(
            update={"duration_days": 4.0, "evaluation_points": 21, "persist": False, "backend": "full"}
        )
        result = service.simulate("uasb", simulation=simulation)
        assert result.metadata["backend_requested"] == "full"
        assert result.metadata["backend_used"] == "reduced"
        assert "backend_fallback_reason" in result.metadata
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_full_backend_is_deterministic_for_same_inputs() -> None:
    service, tmpdir = _make_service()
    try:
        simulation = make_default_simulation_config().model_copy(
            update={"duration_days": 5.0, "evaluation_points": 21, "persist": False, "backend": "full"}
        )
        first = service.simulate("cstr", simulation=simulation)
        second = service.simulate("cstr", simulation=simulation)
        assert second.summary.methane_final_m3_day == pytest.approx(first.summary.methane_final_m3_day, rel=1e-9, abs=1e-9)
        assert second.summary.ph_final == pytest.approx(first.summary.ph_final, rel=1e-9, abs=1e-9)
        assert second.series["biogas_m3_day"][-1] == pytest.approx(first.series["biogas_m3_day"][-1], rel=1e-9, abs=1e-9)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_full_rhs_dimensions_and_nominal_newton_convergence() -> None:
    feed = make_default_feed()
    inputs = build_backend_inputs(
        operating_conditions=make_default_operating_conditions(),
        feed=feed,
        initial_state=make_default_initial_state(feed),
        parameters=make_default_kinetics(),
    )
    system = FullCSTRRhs(inputs=inputs)
    evaluation = system.evaluate(dynamic_values=inputs.initial_values, use_cache=False)
    rate_vector = np.asarray([evaluation.rates[name] for name in BIOCHEMICAL_RATE_ORDER], dtype=float)
    derivative = system(np.float64(0.0), inputs.dynamic_initial)

    assert system.biochemical_matrix.shape == (29, len(BIOCHEMICAL_RATE_ORDER))
    assert rate_vector.shape == (len(BIOCHEMICAL_RATE_ORDER),)
    assert derivative.shape == (29,)
    assert np.isfinite(rate_vector).all()
    assert np.isfinite(derivative).all()
    assert evaluation.acid_base.converged is True


def test_acid_base_solver_reports_iteration_limit_case() -> None:
    feed = make_default_feed()
    inputs = build_backend_inputs(
        operating_conditions=make_default_operating_conditions(),
        feed=feed,
        initial_state=make_default_initial_state(feed),
        parameters=make_default_kinetics(),
    )
    limited_params = dict(inputs.parameter_values)
    limited_params["max_newton_iterations"] = 1.0
    result = solve_acid_base(inputs.initial_values, limited_params, initial_guess=1e-14)

    assert result.iterations == 1
    assert result.converged is False
    assert np.isfinite(result.p_h)
    assert result.s_h_ion > 0.0


def test_algebraic_states_consistent_with_dynamic() -> None:
    """pH deve ser -log10(S_H_ion) e S_nh3 + S_nh4_ion deve igualar S_IN."""
    import math

    feed = make_default_feed()
    inputs = build_backend_inputs(
        operating_conditions=make_default_operating_conditions(),
        feed=feed,
        initial_state=make_default_initial_state(feed),
        parameters=make_default_kinetics(),
    )
    simulation = make_default_simulation_config().model_copy(update={"backend": "full", "duration_days": 60.0})
    result = simulate_with_full_inputs(inputs=inputs, simulation=simulation)
    profiles = result["profiles"]

    ph_final = profiles["ph"][-1]
    s_h_ion_final = profiles["S_H_ion"][-1]
    assert abs(ph_final - (-math.log10(max(s_h_ion_final, 1e-14)))) < 1e-6, (
        f"pH ({ph_final:.4f}) != -log10(S_H_ion) ({-math.log10(max(s_h_ion_final, 1e-14)):.4f})"
    )

    s_in_final = profiles["S_IN"][-1]
    s_nh3_final = profiles["S_nh3"][-1]
    s_nh4_final = profiles["S_nh4_ion"][-1]
    nitrogen_balance_err = abs((s_nh3_final + s_nh4_final) - s_in_final) / max(s_in_final, 1e-9)
    assert nitrogen_balance_err < 0.01, (
        f"S_nh3 + S_nh4_ion ({s_nh3_final + s_nh4_final:.6f}) != S_IN ({s_in_final:.6f}), err={nitrogen_balance_err:.4f}"
    )
