from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from simulator.full_model.asm_adm1_interface import ASM1State, asm1_to_adm1_influent
from simulator.full_model.extension_registry import resolve_full_model_assembly
from simulator.full_model.iron_extension import IRON_EXTENSION
from simulator.full_model.model import build_numeric_biochemical_matrix
from simulator.full_model.trace_elements_extension import TRACE_ELEMENTS_EXTENSION
from simulator.tests.test_extensions import _make_params
from simulator.full_model.parameters import FULL_PARAMETER_CATALOG
from simulator.full_model.state_catalog import FULL_STATE_CATALOG
from simulator.full_model.units import KG_COD_M3, KMOL_M3, MOLAR


def test_asm_ammonium_is_not_counted_as_strong_cation() -> None:
    state = ASM1State(
        S_S=0, S_I=0, X_S=0, X_I=0, X_BH=0, X_BA=0, X_P=0,
        S_ND=0, X_ND=0, S_NH=14000, S_NO=0, S_ALK=0,
    )
    influent = asm1_to_adm1_influent(state)
    assert influent['S_IN'] == pytest.approx(1.0)
    assert influent['S_cation'] == pytest.approx(0.0)


@pytest.mark.parametrize("name", ["S_va_ion", "S_bu_ion", "S_pro_ion", "S_ac_ion"])
def test_ionized_vfa_unit_is_cod_concentration(name: str) -> None:
    states = {state.name: state for state in FULL_STATE_CATALOG}
    assert states[name].unit == KG_COD_M3


def test_gaseous_co2_unit_is_molar_concentration() -> None:
    states = {state.name: state for state in FULL_STATE_CATALOG}
    assert states["S_gas_co2"].unit == KMOL_M3


@pytest.mark.parametrize("name", ["K_H_co2", "K_H_ch4", "K_H_h2"])
def test_henry_constants_include_pressure_unit(name: str) -> None:
    parameters = {parameter.name: parameter for parameter in FULL_PARAMETER_CATALOG}
    assert parameters[name].unit == "M/bar"


def test_water_ionization_product_unit_is_molar_squared() -> None:
    parameters = {parameter.name: parameter for parameter in FULL_PARAMETER_CATALOG}
    assert parameters["K_w"].unit == "M^2"


@pytest.mark.parametrize("name", ["K_pH_aa", "K_pH_ac", "K_pH_h2"])
def test_ph_inhibition_constants_are_concentrations(name: str) -> None:
    parameters = {parameter.name: parameter for parameter in FULL_PARAMETER_CATALOG}
    assert parameters[name].unit == MOLAR


def test_vivianite_conserves_iron_and_phosphorus():
    c = IRON_EXTENSION.contribute()
    row = c.biochemical_stoichiometry_rows['rho_E8_VIV_precip']
    coefs = {key: float(eval(value, {'__builtins__': {}}, {})) for key, value in row.items()}
    assert coefs['S_Fe2'] + 3 * coefs['X_VIV'] == pytest.approx(0, abs=1e-12)
    assert coefs['S_IP'] + 2 * coefs['X_VIV'] == pytest.approx(0, abs=1e-12)
    viv = next(s for s in c.states if s.name == 'X_VIV')
    assert viv.unit == 'kmolVIV/m3'


def test_iron_sulfide_reduction_conserves_sulfur():
    c = IRON_EXTENSION.contribute()
    row = c.biochemical_stoichiometry_rows['rho_E8_Fe3_red_h2s']
    assert any(s.name == 'X_S0' and s.unit == 'kmolS/m3' for s in c.states)
    assert float(row['S_H2S']) + float(row['X_S0']) == pytest.approx(0)
    assert 'X_S0' in next(p for p in c.processes if p.name == 'rho_E8_Fe3_red_h2s').affected_states


def test_vivianite_saturation_uses_actual_ksp():
    c = IRON_EXTENSION.contribute()
    params = {p.name: p.value for p in c.parameters}
    state = {'S_Fe2': 0.001, 'S_IP': 0.001, 'S_H_ion': 1e-7}
    ka2, ka3 = 6.31e-8, 4.57e-13
    po4 = state['S_IP'] * ka2 * ka3 / (1e-14 + ka2 * 1e-7 + ka2 * ka3)
    ip = state['S_Fe2']**3 * po4**2 / params['Ksp_VIV']
    expected = params['k_precip_VIV'] * max(ip - 1, 0) * state['S_Fe2']
    assert c.rate_function(state, params)['rho_E8_VIV_precip'] == pytest.approx(expected)
    names = ['S_Fe2', 'X_FeS', 'X_VIV', 'S_H2S', 'S_IP', 'S_H_ion']
    assembly = SimpleNamespace(full_state_index={name: i for i, name in enumerate(names)})
    matrix = np.array([[state.get(name, 0) for name in names]])
    assert c.diagnostics_hook(matrix, assembly, params)['IP_VIV'][0] == pytest.approx(ip)


def test_hydrogen_reduction_rate_constant_unit():
    params = IRON_EXTENSION.contribute().parameters
    assert next(p.unit for p in params if p.name == 'k_Fe3_red_h2') == 'd^-1'


def test_trace_elements_small_ksp():
    c = TRACE_ELEMENTS_EXTENSION.contribute()
    params = {p.name: p.value for p in c.parameters}
    params.update({'Ksp_NiS': 1e-36})
    state = {'S_Ni': 1e-9, 'S_H2S': 1e-9}
    names = ['S_Ni', 'S_Co', 'S_Fe2_te', 'X_NiS', 'X_CoS', 'X_FeS_te', 'X_FeCO3', 'S_H2S', 'S_IC', 'S_H_ion']
    assembly = SimpleNamespace(full_state_index={name: i for i, name in enumerate(names)})
    matrix = np.array([[state.get(name, 0) for name in names]])
    diagnostics = c.diagnostics_hook(matrix, assembly, params)
    expected = 1e-18 / (1 + params['K_c_Ni'] * params['S_DOM_TE']) / 1e-36
    assert diagnostics['IP_NiS'][0] == pytest.approx(expected)
    rate = c.rate_function(state, params)['rho_E9_NiS_precip']
    free = 1e-9 / (1 + params['K_c_Ni'] * params['S_DOM_TE'])
    assert rate == pytest.approx(params['k_precip_NiS'] * (expected - 1) * free)


def _column(extension: str, process: str):
    assembly = resolve_full_model_assembly([extension])
    params = _make_params(extension)
    matrix = build_numeric_biochemical_matrix(params, assembly=assembly)
    col = matrix[:, assembly.biochemical_process_names.index(process)]
    return params, {name: col[i] for name, i in assembly.dynamic_state_index.items()}


def test_h2s_transfer_conserves_sulfur_between_volumes():
    p, col = _column('srb', 'rho_E4_H2S_transfer')
    for transfer in (0.1, -0.1):
        residual = transfer * (p['V_liq'] * (col['S_SO4'] + col['S_H2S']) + p['V_gas'] * col['S_gas_H2S'])
        assert residual == pytest.approx(0.0, abs=1e-12)


def test_algae_disintegration_conserves_nitrogen():
    p, col = _column('microalgae', 'rho_E20_dis_alg')
    residual = col['X_alg'] * p['i_N_alg'] / 14 + col['X_pr'] * p['N_aa'] + (col['X_I'] + col['S_I']) * p['N_I'] + col['S_IN']
    assert residual == pytest.approx(0.0, abs=1e-12)


def test_algae_disintegration_conserves_carbon():
    p, col = _column('microalgae', 'rho_E20_dis_alg')
    residual = col['X_alg'] * p['C_xc'] + col['X_ch'] * p['C_ch'] + col['X_pr'] * p['C_pr'] + col['X_li'] * p['C_li'] + (col['X_I'] + col['S_I']) * p['C_xI'] + col['S_IC']
    assert residual == pytest.approx(0.0, abs=1e-12)


def test_srb_inhibition_hook_targets_existing_c4_and_propionate_processes():
    from simulator.full_model.model import resolve_full_model_assembly
    from simulator.full_model.srb_extension import SRB_EXTENSION

    assembly = resolve_full_model_assembly(["srb"])
    factors = SRB_EXTENSION.contribute().inhibition_hook({"S_H2S": 0.00336}, {"K_I_H2S": 6.72e-3})
    assert set(factors) <= set(assembly.biochemical_process_names)
    for name in ("rho_8_uptake_valerate", "rho_9_uptake_butyrate", "rho_10_uptake_propionate"):
        assert factors[name] == pytest.approx(0.5)


def test_unknown_process_in_extension_hook_is_rejected():
    from simulator.full_model.kinetics import _require_known_process

    with pytest.raises(ValueError):
        _require_known_process("rho_99_typo", {"rho_11_uptake_acetate": 1.0})
