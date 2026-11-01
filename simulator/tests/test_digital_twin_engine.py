from __future__ import annotations

import numpy as np
import pytest

from simulator.core.defaults import (
    make_default_feed,
    make_default_initial_state,
    make_default_kinetics,
    make_default_operating_conditions,
)
from simulator.core.models import ReactorConfig, SimulationConfig
from simulator.digital_twin.contracts import InfluentWindow
from simulator.digital_twin.engine import TwinEngine, load_state, save_state
from simulator.full_model.model import build_full_inputs
from simulator.full_model.solver import simulate_with_full, simulate_with_full_inputs


@pytest.fixture(scope="module")
def case():
    feed = make_default_feed()
    initial = make_default_initial_state(feed)
    conditions = make_default_operating_conditions()
    inputs = build_full_inputs(
        operating_conditions=conditions,
        feed=feed,
        initial_state=initial,
        parameters=make_default_kinetics(),
    )
    window = InfluentWindow(
        t_start_days=0.0,
        t_end_days=20.0,
        flow_m3_day=conditions.volume_m3 / conditions.hrt_days,
        temperature_c=conditions.temperature_c,
        influent_values=inputs.influent_values,
    )
    engine = TwinEngine(volume_m3=conditions.volume_m3, points_per_day=2)
    state = engine.initial_state(window, warmup_days=30.0)
    return engine, state, window, inputs, feed, initial, conditions


def test_split_windows_preserve_complete_state(case):
    engine, state, window, *_ = case
    whole = engine.advance(state, window)
    first = window.model_copy(update={"t_end_days": 10.0})
    second = window.model_copy(update={"t_start_days": 10.0})
    parts = engine.run(state, [first, second])

    assert parts[0].time_days[-1] == pytest.approx(10.0)
    assert parts[1].time_days[0] == pytest.approx(10.0)
    assert parts[-1].state.time_days == pytest.approx(20.0)
    assert whole.state.dynamic_state.keys() == parts[-1].state.dynamic_state.keys()
    np.testing.assert_allclose(
        list(whole.state.dynamic_state.values()),
        list(parts[-1].state.dynamic_state.values()),
        rtol=1e-3,
        atol=1e-7,
    )


def test_constant_window_matches_full_backend(case):
    engine, state, window, _, feed, initial, conditions = case
    actual = engine.advance(state, window)
    full = simulate_with_full(
        operating_conditions=conditions,
        feed=feed,
        initial_state=initial,
        parameters=make_default_kinetics(),
        simulation=SimulationConfig(
            duration_days=20.0, evaluation_points=len(actual.time_days),
            backend="full", persist=False,
        ),
        initial_state_overrides=state.dynamic_state,
        influent_state_overrides=window.influent_values,
    )
    profiles = {name: np.asarray(values) for name, values in full["profiles"].items() if isinstance(values, list)}
    for output, profile in {"ph": "ph", "vfa_kg_cod_m3": "vfa_total"}.items():
        np.testing.assert_allclose(actual.outputs[output], profiles[profile], rtol=1e-3, atol=1e-7)
    # Physical outputs (lab basis) recomputed from the full-model state.
    p = engine_params(conditions)
    dry = profiles["Pgas_bar"] - p["p_gas_h2o"]
    expected = {
        "nh4_kg_n_m3": 14.0 * (profiles["S_IN"] - profiles["S_nh3"]),
        "ch4_fraction": profiles["S_gas_ch4"] * p["R"] * p["T_op"] / 64.0 / dry,
        "biogas_m3_d": profiles["q_gas_headspace_m3_day"] * dry / 1.01325 * 273.15 / p["T_op"],
        "alkalinity_kmol_m3": profiles["S_hco3_ion"] + profiles["S_nh3"] + profiles["S_ac_ion"] / 64.0
        + profiles["S_pro_ion"] / 112.0 + profiles["S_bu_ion"] / 160.0 + profiles["S_va_ion"] / 208.0,
    }
    for output, values in expected.items():
        np.testing.assert_allclose(actual.outputs[output], values, rtol=1e-3, atol=1e-7)


def engine_params(conditions):
    from simulator.full_model.model import resolve_full_parameter_values

    return resolve_full_parameter_values(operating_conditions=conditions, parameters=make_default_kinetics())


def test_flow_step_increases_biogas(case):
    engine, state, window, *_ = case
    baseline = engine.advance(state, window)
    stepped = engine.advance(state, window.model_copy(update={"flow_m3_day": window.flow_m3_day * 1.3}))
    assert stepped.outputs["biogas_m3_d"][-1] > baseline.outputs["biogas_m3_d"][-1]


def test_state_json_round_trip(case, tmp_path):
    engine, state, *_ = case
    path = tmp_path / "state.json"
    save_state(state, path)
    assert load_state(path) == state


def test_noncontiguous_window_is_rejected(case):
    engine, state, window, *_ = case
    first = window.model_copy(update={"t_end_days": 10.0})
    gap = window.model_copy(update={"t_start_days": 11.0})
    with pytest.raises(ValueError, match="(?i)(contig|time|start)"):
        engine.run(state, [first, gap])
    with pytest.raises(ValueError, match="(?i)(contig|time|start)"):
        engine.advance(state, gap)


def test_solver_restart_rejects_non_cstr(case):
    _, _, _, inputs, *_ = case
    with pytest.raises(ValueError, match="(?i)cstr"):
        simulate_with_full_inputs(
            inputs=inputs,
            simulation=SimulationConfig(duration_days=1, evaluation_points=21),
            reactor_config=ReactorConfig(reactor_type="batch"),
            initial_dynamic_state=inputs.dynamic_initial,
        )


def test_temperature_change_affects_parameters_and_outputs(case):
    engine, state, window, *_ = case
    first = window.model_copy(update={"t_end_days": 1.0})
    next_state = engine.advance(state, first).state
    normal = window.model_copy(update={"t_start_days": 1.0, "t_end_days": 2.0})
    warmer = normal.model_copy(update={"temperature_c": 45.0})
    normal_inputs = engine._inputs(normal, next_state.dynamic_state, next_state.parameter_overrides)
    warmer_inputs = engine._inputs(warmer, next_state.dynamic_state, next_state.parameter_overrides)
    assert normal_inputs.parameter_values["T_op"] == pytest.approx(308.15)
    assert warmer_inputs.parameter_values["T_op"] == pytest.approx(318.15)
    assert warmer_inputs.parameter_values["T_ad"] == pytest.approx(318.15)
    assert warmer_inputs.parameter_values["K_a_co2"] != pytest.approx(normal_inputs.parameter_values["K_a_co2"], rel=1e-4, abs=0)
    normal_result = engine.advance(next_state, normal)
    warmer_result = engine.advance(next_state, warmer)
    assert warmer_result.outputs["ph"][-1] != pytest.approx(normal_result.outputs["ph"][-1], rel=1e-5)


def test_short_window_and_incomplete_state(case):
    engine, state, window, *_ = case
    short = window.model_copy(update={"t_end_days": 0.05})
    result = engine.advance(state, short)
    assert result.time_days[0] == 0.0
    assert result.time_days[-1] == pytest.approx(0.05)
    assert result.state.time_days == pytest.approx(0.05)
    incomplete = dict(state.dynamic_state)
    incomplete.pop(next(iter(incomplete)))
    with pytest.raises(ValueError, match="(?i)dynamic state"):
        engine.advance(state.model_copy(update={"dynamic_state": incomplete}), short)
