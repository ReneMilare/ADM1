from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest

from simulator.core.defaults import make_default_kinetics
from simulator.core.models import OperatingConditions, ReactorConfig, SimulationConfig, TPADConfig
from simulator.full_model.acid_base import solve_acid_base
from simulator.full_model.diagnostics import translate_full_profiles
from simulator.full_model.inhibition import build_inhibition_factors
from simulator.full_model.model import build_full_inputs_from_state_maps, dynamic_state_dict
from simulator.full_model.reactor_modes import (
    FullPlugFlowRhs, FullTPADRhs, FullTwoPhaseRhs, FullUASBRhs, build_reactor_mode,
)
from simulator.full_model.rhs import FullCSTRRhs
from simulator.full_model.solver import simulate_with_full_inputs


def _inputs(*, extensions=(), overrides=None, initial=None, influent=None, temperature=35.0, volume=3400.0):
    state = {"S_IC": 0.1, "S_IN": 0.01, "S_cation": 0.1, "S_anion": 0.01}
    state.update(initial or {})
    return build_full_inputs_from_state_maps(
        operating_conditions=OperatingConditions(volume_m3=volume, temperature_c=temperature, hrt_days=20),
        parameters=make_default_kinetics(),
        influent_values=state if influent is None else influent,
        initial_values=state,
        flow_rate_m3_day=170.0,
        active_extensions=extensions,
        extension_parameter_overrides=overrides,
    )


def test_ph_limits_override_recomputes_midpoint_and_exponent():
    inputs = _inputs(overrides={"pH_LL_ac": 7.0, "pH_UL_ac": 8.0})
    factors = build_inhibition_factors(
        {"S_H_ion": 10**-7.5, "S_IN": 0.01, "S_h2": 0.0, "S_nh3": 0.0}, inputs.parameter_values,
    )
    assert factors["I_pH_ac"] == pytest.approx(0.5)
    assert inputs.parameter_values["n_ac"] == pytest.approx(3.0)


@pytest.mark.parametrize("derived", ["K_pH_ac", "n_ac", "K_w", "K_H_co2", "p_gas_h2o"])
def test_explicit_derived_override_wins(derived):
    inputs = _inputs(overrides={"pH_LL_ac": 7.0, "pH_UL_ac": 9.0, derived: 0.123})
    assert inputs.parameter_values[derived] == 0.123


def test_tpad_preserves_explicit_temperature_independent_ph_midpoint():
    inputs = _inputs(overrides={"K_pH_ac": 1e-8})
    system = FullTPADRhs(inputs=inputs)
    assert system._rhs1.params["K_pH_ac"] == pytest.approx(1e-8, abs=0.0)
    assert system._rhs2.params["K_pH_ac"] == pytest.approx(1e-8, abs=0.0)


def test_temperature_derivatives_use_final_reference_parameters():
    p = _inputs(overrides={"R": 0.09, "T_base": 300.0, "T_op": 315.0}).parameter_values
    dt = 1 / 300.0 - 1 / 315.0
    assert p["K_w"] == pytest.approx(1e-14 * np.exp(55900 / 9.0 * dt), abs=0.0)
    assert p["K_H_co2"] == pytest.approx(0.035 * np.exp(-19410 / 9.0 * dt))
    assert p["p_gas_h2o"] == pytest.approx(0.0313 * np.exp(5290 * dt))


@pytest.mark.parametrize("fraction,extension", [("f_lac_su", "lactate"), ("f_et_su", "ethanol")])
def test_product_fraction_requires_its_extension(fraction, extension):
    with pytest.raises(ValueError, match=f"{fraction}.*{extension}"):
        _inputs(overrides={fraction: 0.1})
    assert _inputs(extensions=[extension], overrides={fraction: 0.1}).parameter_values[fraction] == 0.1


def _charge_residual(state, p, acid):
    return (state["S_cation"] + acid.s_nh4_ion + acid.s_h_ion - acid.s_hco3_ion
            - acid.s_ac_ion / 64 - acid.s_pro_ion / 112 - acid.s_bu_ion / 160
            - acid.s_va_ion / 208 - p["K_w"] / acid.s_h_ion - state["S_anion"])


def test_newton_requires_charge_residual_at_high_ph():
    inputs = _inputs(initial={"S_cation": 0.118306972319976, "S_ac": 0.1,
                              "S_pro": 0.01, "S_bu": 0.01, "S_va": 0.01})
    acid = solve_acid_base(inputs.initial_values, inputs.parameter_values)
    assert acid.converged
    assert abs(_charge_residual(inputs.initial_values, inputs.parameter_values, acid)) < inputs.parameter_values["ph_solver_tol"]
    assert acid.p_h == pytest.approx(11.5, abs=1e-8)


def test_newton_does_not_report_convergence_on_small_step_only():
    inputs = _inputs(initial={"S_cation": 0.118306972319976, "S_ac": 0.1,
                              "S_pro": 0.01, "S_bu": 0.01, "S_va": 0.01},
                     overrides={"max_newton_iterations": 1})
    acid = solve_acid_base(inputs.initial_values, inputs.parameter_values, initial_guess=1.7e-12)
    assert not acid.converged


@pytest.mark.parametrize("x,expected", [(0.0, 0.5), (4.0, 0.43)])
def test_uasb_retains_only_outgoing_solids(x, expected):
    inputs = _inputs(initial={"X_I": x}, influent={"X_I": 10.0})
    derivative = FullUASBRhs(inputs=inputs, biomass_washout_factor=0.35)(0, inputs.dynamic_initial)
    assert derivative[inputs.assembly.dynamic_state_index["X_I"]] == pytest.approx(expected)


@pytest.mark.parametrize("extensions,gas,divisor", [(["syngas"], "S_gas_CO", 16.0), (["srb"], "S_gas_H2S", 1.0),
                                                    (["syngas", "srb"], "S_gas_CO", 16.0)])
def test_extra_gases_contribute_pressure_and_diagnostics(extensions, gas, divisor):
    inputs = _inputs(extensions=extensions, initial={gas: 1.0})
    p = inputs.parameter_values
    ev = FullCSTRRhs(inputs=inputs).evaluate(dynamic_values=dynamic_state_dict(inputs.dynamic_initial, inputs.assembly), use_cache=False)
    expected_p = p["p_gas_h2o"] + p["R"] * p["T_op"] / divisor
    assert ev.gas_transfer.p_total == pytest.approx(expected_p)
    assert ev.gas_transfer.q_gas == pytest.approx(p["k_p"] * (expected_p - p["p_atm"]))
    profiles = translate_full_profiles(full_state_matrix=np.asarray([ev.full_state.vector]), parameter_values=p, assembly=inputs.assembly)
    assert profiles["Pgas_bar"][0] == pytest.approx(expected_p)
    flow_name = "co_m3_day" if gas == "S_gas_CO" else "h2s_m3_day"
    expected_partial_flow = ev.gas_transfer.q_gas * (expected_p - p["p_gas_h2o"]) / p["p_atm"]
    assert profiles[flow_name][0] == pytest.approx(expected_partial_flow)


@pytest.mark.parametrize("unit,new_name", [("kgCOD/m3", "S_gas_unknown"), ("unsupported/m3", "S_gas_CO")])
def test_unknown_gas_conversion_fails_clearly(unit, new_name):
    inputs = _inputs(extensions=["syngas"])
    a = inputs.assembly
    catalog = tuple(replace(s, name=new_name, unit=unit) if s.name == "S_gas_CO" else s for s in a.state_catalog)
    assembly = replace(a, state_catalog=catalog, dynamic_gas_state_names=tuple(new_name if n == "S_gas_CO" else n for n in a.dynamic_gas_state_names))
    inputs = replace(inputs, assembly=assembly)
    with pytest.raises(ValueError, match=new_name):
        FullCSTRRhs(inputs=inputs).evaluate(dynamic_values=dynamic_state_dict(inputs.dynamic_initial, a), use_cache=False)


@pytest.mark.parametrize("mode", ["cstr", "batch", "uasb", "plug_flow", "two_phase", "tpad"])
@pytest.mark.parametrize("volume", [3400.0, 10.0])
@pytest.mark.parametrize("gas_initial", [0.0, 1.0])
@pytest.mark.parametrize("extension,liquid_name,gas_name", [("syngas", "S_CO", "S_gas_CO"), ("srb", "S_H2S", "S_gas_H2S")])
def test_extra_gas_transfer_is_present_and_conservative_in_every_mode(mode, volume, extension, liquid_name, gas_name, gas_initial):
    inputs = _inputs(extensions=[extension], initial={liquid_name: 1.0, gas_name: gas_initial}, overrides={"q_ad": 0.0}, volume=volume)
    system = build_reactor_mode(mode, inputs, reactor_config=ReactorConfig(reactor_type=mode, segments=2))
    if isinstance(system, FullPlugFlowRhs):
        rhs_list = [system._rhs] * system.n_segments
    elif isinstance(system, FullTwoPhaseRhs):
        rhs_list = [system._rhs1, system._rhs2]
    else:
        rhs_list = [system]
    m = len(inputs.assembly.dynamic_state_names)
    dy = system(0.0, np.tile(inputs.dynamic_initial, len(rhs_list)))
    idx = inputs.assembly.dynamic_state_index
    for i, rhs in enumerate(rhs_list):
        liquid = dy[i * m + idx[liquid_name]]
        gas = dy[i * m + idx[gas_name]]
        if gas_initial == 0.0:
            assert gas > 0
        reference = FullCSTRRhs(inputs=rhs.inputs)(0, inputs.dynamic_initial)
        assert gas == pytest.approx(reference[idx[gas_name]])
        p = rhs.params
        divisor = 16.0 if extension == "syngas" else 1.0
        pressure = p["p_gas_h2o"] + gas_initial * p["R"] * p["T_op"] / divisor
        q_gas = max(p["k_p"] * (pressure - p["p_atm"]), 0.0)
        residual = liquid * p["V_liq"] + gas * p["V_gas"] + q_gas * gas_initial
        assert residual == pytest.approx(0.0, abs=1e-8)
        if extension == "syngas":
            # CO carries 1 kmol C per 16 kg COD (syngas extension stoichiometry).
            assert residual / 16.0 == pytest.approx(0.0, abs=1e-10)
        assert dy[i * m + idx["S_IN"]] == pytest.approx(0.0, abs=1e-14)


def test_all_extra_gases_add_to_pressure_and_partial_flows():
    inputs = _inputs(extensions=["syngas", "srb"], initial={"S_gas_CO": 0.5, "S_gas_H2S": 0.1})
    p = inputs.parameter_values
    ev = FullCSTRRhs(inputs=inputs).evaluate(dynamic_values=inputs.initial_values, use_cache=False)
    p_co = 0.5 * p["R"] * p["T_op"] / 16
    p_h2s = 0.1 * p["R"] * p["T_op"]
    assert ev.gas_transfer.p_total == pytest.approx(p["p_gas_h2o"] + p_co + p_h2s)
    assert ev.gas_transfer.q_co == pytest.approx(ev.gas_transfer.q_gas * p_co / ev.gas_transfer.p_total)
    assert ev.gas_transfer.q_h2s == pytest.approx(ev.gas_transfer.q_gas * p_h2s / ev.gas_transfer.p_total)


def _mock_solution(monkeypatch, *, phase_gases=False):
    captured = {}

    def solve(system, **kwargs):
        captured.update(system=system, **kwargs)
        y = np.tile(kwargs["y0"][:, None], (1, len(kwargs["t_eval"])))
        if phase_gases:
            a = system.assembly
            m = len(a.dynamic_state_names)
            for segment in range(len(kwargs["y0"]) // m):
                y[segment * m + a.dynamic_state_index["S_gas_ch4"]] = 2.0 + segment
                y[segment * m + a.dynamic_state_index["S_gas_co2"]] = 0.01 * (segment + 1)
                y[segment * m + a.dynamic_state_index["S_gas_h2"]] = 0.002 * (segment + 1)
                y[segment * m + a.dynamic_state_index["S_ac"]] = 0.1 + segment
                for name in ("S_gas_CO", "S_gas_H2S"):
                    if name in a.dynamic_state_index:
                        y[segment * m + a.dynamic_state_index[name]] = 0.1 * (segment + 1)
        captured["y"] = y
        return SimpleNamespace(success=True, message="test solution", y=y)

    monkeypatch.setattr("simulator.full_model.solver.solve_ivp", solve)
    return captured


@pytest.mark.parametrize("mode", ["cstr", "plug_flow", "two_phase", "tpad"])
def test_solver_metadata_records_effective_and_requested_settings(monkeypatch, mode):
    captured = _mock_solution(monkeypatch)
    sim = SimulationConfig(duration_days=0.2, evaluation_points=21, solver="BDF", rtol=1e-8, atol=1e-10)
    result = simulate_with_full_inputs(inputs=_inputs(), simulation=sim, reactor_config=ReactorConfig(reactor_type=mode, segments=2))
    metadata = result["metadata"]
    for key, arg in [("method", "method"), ("rtol", "rtol"), ("atol", "atol")]:
        assert metadata[f"full_model_solver_{key}"] == captured[arg]
        assert metadata[f"full_model_solver_{key}_requested"] == getattr(sim, "solver" if key == "method" else key)


@pytest.mark.parametrize("mode", ["plug_flow", "two_phase", "tpad"])
@pytest.mark.parametrize("extensions", [(), ("syngas", "srb")])
def test_segment_gas_outputs_are_summed_with_each_segments_parameters(monkeypatch, mode, extensions):
    captured = _mock_solution(monkeypatch, phase_gases=True)
    config = ReactorConfig(reactor_type=mode, segments=2, tpad=TPADConfig(meso_temperature_c=42))
    result = simulate_with_full_inputs(inputs=_inputs(temperature=25, extensions=extensions),
                                      simulation=SimulationConfig(duration_days=0.2, evaluation_points=21), reactor_config=config)
    system = captured["system"]
    rhs_list = [system._rhs] * system.n_segments if isinstance(system, FullPlugFlowRhs) else [system._rhs1, system._rhs2]
    totals = dict.fromkeys(["biogas_m3_day", "methane_m3_day", "co2_m3_day", "h2_m3_day", "q_gas_headspace_m3_day"], 0.0)
    if extensions:
        totals.update(co_m3_day=0.0, h2s_m3_day=0.0)
    m = len(system.assembly.dynamic_state_names)
    last_p = None
    for i, rhs in enumerate(rhs_list):
        p = rhs.params
        row = captured["y"][i * m:(i + 1) * m, 0]
        state = dynamic_state_dict(row, system.assembly)
        partials = {"methane_m3_day": state["S_gas_ch4"] * p["R"] * p["T_op"] / 64,
                    "co2_m3_day": state["S_gas_co2"] * p["R"] * p["T_op"],
                    "h2_m3_day": state["S_gas_h2"] * p["R"] * p["T_op"] / 16}
        for name, flow, divisor in (("S_gas_CO", "co_m3_day", 16.0), ("S_gas_H2S", "h2s_m3_day", 1.0)):
            if name in state:
                partials[flow] = state[name] * p["R"] * p["T_op"] / divisor
        last_p = sum(partials.values()) + p["p_gas_h2o"]
        q = max(p["k_p"] * (last_p - p["p_atm"]), 0)
        totals["q_gas_headspace_m3_day"] += q
        totals["biogas_m3_day"] += q * last_p / p["p_atm"]
        for name, partial in partials.items():
            totals[name] += q * partial / p["p_atm"]
    for name, expected in totals.items():
        assert result["profiles"][name][0] == pytest.approx(expected)
    assert result["profiles"]["ch4_fraction"][0] == pytest.approx(totals["methane_m3_day"] / totals["biogas_m3_day"])
    assert result["profiles"]["Pgas_bar"][0] == pytest.approx(last_p)
    assert result["profiles"]["acetate"][0] == pytest.approx(1.1)
