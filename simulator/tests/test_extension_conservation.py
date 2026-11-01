from __future__ import annotations

import numpy as np
import pytest
from scipy.integrate import solve_ivp

from simulator.core.models import OperatingConditions, ReactorConfig
from simulator.core.defaults import make_default_kinetics
from simulator.full_model.adapter import build_backend_inputs_from_state_maps
from simulator.full_model.extension_registry import resolve_full_model_assembly
from simulator.full_model.model import build_numeric_biochemical_matrix
from simulator.full_model.reactor_modes import build_reactor_mode
from simulator.full_model.trace_elements_extension import TRACE_ELEMENTS_EXTENSION
from simulator.tests.test_extensions import _base_state, _make_params


@pytest.mark.parametrize("extensions", [["srb"], ["srb", "phosphorus", "iron"]])
def test_cod_columns_include_sulfur_and_ferrous_reducing_equivalents(extensions):
    assembly = resolve_full_model_assembly(extensions)
    params = _make_params(extensions)
    matrix = build_numeric_biochemical_matrix(params, assembly)
    weights = np.array([float(s.cod_role == "cod") for s in assembly.state_catalog if s.role == "dynamic"])
    # Fedorovich et al. (2003); Lizarralde et al. (2015): sulfate is the S
    # reference, Fe(III) the Fe reference. One electron/mol Fe(II) = 8 kgO2/kmol.
    for name, equivalent in {"S_H2S": 64, "S_gas_H2S": 64, "X_FeS": 72,
                             "S_Fe2": 8, "X_VIV": 24, "X_S0": 48}.items():
        if name in assembly.dynamic_state_index:
            weights[assembly.dynamic_state_index[name]] = equivalent
    weights *= np.array([params["V_gas"] / params["V_liq"] if name in assembly.dynamic_gas_state_names else 1.0
                         for name in assembly.dynamic_state_names])
    for j, name in enumerate(assembly.biochemical_process_names):
        scale = np.abs(weights) @ np.abs(matrix[:, j])
        assert abs(weights @ matrix[:, j]) < 2e-15 * max(scale, 1.0), name


@pytest.mark.parametrize("extensions", [["lactate"], ["lactate", "ethanol"], ["phenolics"], ["syngas"],
                                        ["microalgae"], ["phosphorus"], ["trace_elements"],
                                        ["srb", "phosphorus", "iron"], ["lcfa_adsorption"],
                                        ["pilot_tracer"], ["multi_population"]])
def test_catalog_carbon_matches_reaction_columns(extensions):
    assembly = resolve_full_model_assembly(extensions)
    params = _make_params(extensions)
    params.update(C_sI=0.04, C_xI=0.03)
    matrix = build_numeric_biochemical_matrix(params, assembly)
    carbon = np.array([params.get(s.elemental_proxy, 1.0 if s.elemental_proxy == "1 mol C/mol" else 0.0)
                       for s in assembly.state_catalog if s.role == "dynamic"])
    carbon *= np.array([params["V_gas"] / params["V_liq"] if name in assembly.dynamic_gas_state_names else 1.0
                        for name in assembly.dynamic_state_names])
    for j, name in enumerate(assembly.biochemical_process_names):
        if "multi_population" in extensions and name in {
            "rho_11_uptake_acetate", "rho_12_uptake_hydrogen",
            "rho_18_decay_acetate_biomass", "rho_19_decay_hydrogen_biomass",
        }:
            continue
        assert abs(carbon @ matrix[:, j]) < 1e-14, name


@pytest.mark.parametrize("extensions", [["lactate"], ["ethanol"], ["srb"], ["syngas"],
                                        ["lcfa_adsorption"], ["multi_population"], ["phenolics"]])
@pytest.mark.parametrize("nitrogen", [0.0, -1e-10])
def test_no_extension_biomass_synthesis_without_inorganic_nitrogen(extensions, nitrogen):
    assembly = resolve_full_model_assembly(extensions)
    params = _make_params(extensions)
    state = {name: 0.1 for name in assembly.full_state_names}
    state.update(S_IN=nitrogen, S_H_ion=1e-7, S_h2=1e-7, S_nh3=0.0, S_H2S=1e-5)
    matrix = build_numeric_biochemical_matrix(params, assembly)
    biomass = [assembly.dynamic_state_index[s.name] for s in assembly.state_catalog
               if s.elemental_proxy == "C_bac" and s.role == "dynamic"]
    checked = []
    for rate_function in assembly.extension_rate_functions:
        state["S_IN"] = nitrogen
        rates = rate_function(state, params)
        synthesis = [name for name in rates if np.any(matrix[biomass, assembly.biochemical_process_names.index(name)] > 0)]
        checked.extend(synthesis)
        for name in synthesis:
            assert rates[name] == 0.0, name
        state["S_IN"] = 0.01
        fed_rates = rate_function(state, params)
        assert all(fed_rates[name] > 0 for name in synthesis)
    assert checked


def test_trace_sulfides_inactive_without_dissolved_sulfide_state():
    params = _make_params("trace_elements")
    state = {"S_Ni": 1e-6, "S_Co": 1e-6, "S_Fe2_te": 1e-6,
             "X_NiS": 1e-6, "X_CoS": 1e-6, "X_FeS_te": 1e-6,
             "X_FeCO3": 1e-6, "S_IC": 0.0, "S_H_ion": 1e-7}
    rates = TRACE_ELEMENTS_EXTENSION._rates(state, params)
    assert all(value == 0 for name, value in rates.items() if "FeCO3" not in name)
    assert rates["rho_E9_FeCO3_dissolv"] > 0
    rates_with_srb = TRACE_ELEMENTS_EXTENSION._rates({**state, "S_H2S": 0.0}, params)
    assert rates_with_srb["rho_E9_NiS_dissolv"] > 0


def test_trace_elements_alone_batch_conserves_sulfur_and_cod():
    assembly = resolve_full_model_assembly(["trace_elements"])
    initial = {**_base_state(), "S_Ni": 1e-8, "S_Co": 1e-8, "S_Fe2_te": 1e-6,
               "X_NiS": 1e-8, "X_CoS": 1e-8, "X_FeS_te": 1e-6, "X_FeCO3": 1e-6}
    inputs = build_backend_inputs_from_state_maps(
        operating_conditions=OperatingConditions(), parameters=make_default_kinetics(),
        initial_values=initial, influent_values=initial, active_extensions=["trace_elements"],
        extension_parameter_overrides={"q_ad": 0.0},
    )
    rhs = build_reactor_mode("batch", inputs, reactor_config=ReactorConfig(reactor_type="batch"))
    n = len(assembly.dynamic_state_names)
    sulfur = np.array([float(name in {"X_NiS", "X_CoS", "X_FeS_te"}) for name in assembly.dynamic_state_names])
    cod = np.array([float(s.cod_role == "cod") for s in assembly.state_catalog if s.role == "dynamic"]) + 64 * sulfur
    gas = np.array([name in assembly.dynamic_gas_state_names for name in assembly.dynamic_state_names])
    volume = np.where(gas, inputs.parameter_values["V_gas"], inputs.parameter_values["V_liq"])

    def augmented_rhs(t, z):
        state = dict(zip(assembly.dynamic_state_names, z[:n]))
        q_gas = rhs.evaluate(dynamic_values=state, use_cache=False).gas_transfer.q_gas
        return np.r_[rhs(t, z[:n]), q_gas * (cod[gas] @ z[:n][gas])]

    sol = solve_ivp(augmented_rhs, (0.0, 0.25), np.r_[inputs.dynamic_initial, 0.0],
                    method="BDF", rtol=2e-9, atol=1e-12)
    assert sol.success
    assert sulfur @ (volume * sol.y[:n, -1]) == pytest.approx(sulfur @ (volume * sol.y[:n, 0]), rel=1e-12)
    assert cod @ (volume * sol.y[:n, -1]) + sol.y[-1, -1] == pytest.approx(cod @ (volume * sol.y[:n, 0]), rel=1e-12)


def test_iron_trace_conflict_explains_duplicate_fes():
    with pytest.raises(ValueError, match="FeS"):
        resolve_full_model_assembly(["srb", "phosphorus", "iron", "trace_elements"])


def test_exact_formula_based_extension_parameters():
    ethanol = _make_params("ethanol")
    phenolics = _make_params("phenolics")
    assert ethanol["f_ac_et"] == 2 / 3
    assert ethanol["f_h2_et"] == 1 / 3
    assert phenolics["C_phen"] == 6 / 224
    assert phenolics["C_ben"] == 7 / 240
