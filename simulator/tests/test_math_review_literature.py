from __future__ import annotations

import pytest

from simulator.full_model.extension_registry import resolve_full_model_assembly
from simulator.full_model.kinetics import biochemical_rates
from simulator.full_model.lactate_extension import LACTATE_EXTENSION
from simulator.full_model.multi_population_extension import MULTI_POPULATION_EXTENSION
from simulator.full_model.phenolics_extension import PHENOLICS_EXTENSION
from simulator.full_model.srb_extension import SRB_EXTENSION
from simulator.tests.test_extensions import _base_state, _make_params


def test_fedorovich_srb_parameters():
    params = {p.name: p for p in SRB_EXTENSION.contribute().parameters}
    expected = {
        'k_m_SRB_pro': 12.6, 'K_S_SRB_pro': 0.11, 'K_S_SO4_pro': 2e-4,
        'Y_SRB_pro': 0.0329, 'k_dec_X_SRB_pro': 0.01,
        'k_m_SRB_bu': 13.7, 'K_S_SRB_bu': 0.10, 'K_S_SO4_bu': 2.1e-4,
        'Y_SRB_bu': 0.0329, 'k_dec_X_SRB_bu': 0.01,
    }
    for name, value in expected.items():
        assert params[name].value == pytest.approx(value), name
        assert 'Fedorovich' in params[name].notes


def test_fezzani_benzoate_parameters():
    params = {p.name: p for p in PHENOLICS_EXTENSION.contribute().parameters}
    for name, value in {'k_m_ben': 8, 'K_S_ben': 15.5, 'Y_ben': 0.0135, 'k_dec_X_ben': 0.02}.items():
        assert params[name].value == pytest.approx(value)
    assert 'Monod' in params['K_S_ben'].notes


def test_phenol_and_tvfa_inhibit_only_acetate():
    state = {'S_phen': 25, 'S_va': 5, 'S_bu': 10, 'S_pro': 15, 'S_ac': 17.5}
    factors = PHENOLICS_EXTENSION._inhibition(state, {'K_I_phen': 50})
    assert factors == {'rho_11_uptake_acetate': pytest.approx((1 / 1.5) * (1 / 2))}


def test_phenol_uptake_is_haldane_from_fezzani_table2():
    # rho_7a = k_m * S / (K_S + S + S^2/K_I) * X, with no ADM1 inhibition factor.
    params = _make_params('phenolics')
    state = {'S_phen': 25, 'X_phen': 1, 'S_IN': 0.01, 'S_H_ion': 1e-7, 'S_h2': 1e-4}
    rate = PHENOLICS_EXTENSION._rates(state, params)['rho_E11_uptake_phenolics']
    expected = params['k_m_phen'] * 25 / (params['K_S_phen'] + 25 + 25**2 / params['K_I_phen'])
    assert rate == pytest.approx(expected)
    acid = PHENOLICS_EXTENSION._rates(dict(state, S_H_ion=1e-5, S_h2=1e-2), params)['rho_E11_uptake_phenolics']
    assert acid == pytest.approx(rate)


def test_lactate_uses_c4_hydrogen_inhibition():
    params = _make_params('lactate')
    state = {'S_lac': 1, 'X_lac': 1, 'S_IN': 0.01, 'S_h2': 1e-5}
    baseline = LACTATE_EXTENSION._rates(dict(state, S_h2=0), params)['rho_E6_uptake_lactate']
    rate = LACTATE_EXTENSION._rates(state, params)['rho_E6_uptake_lactate']
    assert rate / baseline == pytest.approx(1 / (1 + 1e-5 / params['K_I_h2_c4']), rel=1e-6)


def test_multi_population_disables_all_replaced_core_rates():
    assembly = resolve_full_model_assembly(['multi_population'])
    state = _base_state()
    state.update({'S_H_ion': 1e-7, 'S_nh3': 0})
    rates, _ = biochemical_rates(state, _make_params('multi_population'), assembly=assembly)
    for name in ('rho_11_uptake_acetate', 'rho_12_uptake_hydrogen', 'rho_18_decay_acetate_biomass', 'rho_19_decay_hydrogen_biomass'):
        assert rates[name] == 0


@pytest.mark.parametrize('extension,state,ac,h2', [
    ('phenolics', {'S_phen': 50, 'S_va': 0, 'S_bu': 0, 'S_pro': 0, 'S_ac': 0}, 0.5, 1.0),
    ('syngas', {'S_CO': 0.00103}, 0.5, 0.005 / 0.00603),
    # pH 7 = pKa1: only half of the total sulfide is free H2S.
    ('srb', {'S_H2S': 0.00672}, 0.5, 0.5),
])
def test_multi_population_receives_other_inhibitions(extension, state, ac, h2):
    params = _make_params(['multi_population', extension])
    factors = MULTI_POPULATION_EXTENSION.contribute().inhibition_hook(state, params)
    assert factors['rho_E12_uptake_ac_1'] == pytest.approx(ac)
    assert factors['rho_E12_uptake_ac_2'] == pytest.approx(ac)
    assert factors['rho_E12_uptake_h2_1'] == pytest.approx(h2)
    assert factors['rho_E12_uptake_h2_2'] == pytest.approx(h2)


def test_multi_population_batch_cod_balance_five_days():
    import numpy as np
    from scipy.integrate import solve_ivp
    from simulator.core.defaults import make_default_kinetics
    from simulator.core.models import OperatingConditions
    from simulator.full_model.adapter import build_backend_inputs_from_state_maps
    from simulator.full_model.model import dynamic_state_dict
    from simulator.full_model.rhs import FullCSTRRhs

    state = _base_state()
    state.update({'X_ac_1': 0.75, 'X_ac_2': 0.75, 'X_h2_1': 0.25, 'X_h2_2': 0.25})
    inputs = build_backend_inputs_from_state_maps(
        operating_conditions=OperatingConditions(volume_m3=3400, temperature_c=35, hrt_days=20),
        parameters=make_default_kinetics(), influent_values=state, initial_values=state,
        flow_rate_m3_day=0, active_extensions=['multi_population'],
    )
    inputs.parameter_values['q_ad'] = 0.0
    rhs = FullCSTRRhs(inputs=inputs)
    assembly = inputs.assembly
    liquid = [assembly.dynamic_state_index[s.name] for s in assembly.state_catalog
              if s.role == 'dynamic' and s.cod_role == 'cod' and s.phase != 'gas']
    gas = [assembly.dynamic_state_index[name] for name in ('S_gas_h2', 'S_gas_ch4')]
    v_liq, v_gas = rhs.params['V_liq'], rhs.params['V_gas']

    def augmented(t, y):
        dy = rhs(t, y[:-1])
        dynamic = dynamic_state_dict(y[:-1], assembly=assembly)
        q_gas = rhs.evaluate(dynamic_values=dynamic, use_cache=False).gas_transfer.q_gas
        return np.append(dy, q_gas * sum(y[i] for i in gas))

    y0 = np.append(inputs.dynamic_initial, 0.0)
    sol = solve_ivp(augmented, (0, 5), y0, method='BDF', rtol=1e-8, atol=1e-10)
    assert sol.success
    def inventory(y):
        return v_liq * sum(y[i] for i in liquid) + v_gas * sum(y[i] for i in gas) + y[-1]
    assert inventory(sol.y[:, -1]) == pytest.approx(inventory(y0), rel=2e-7)


def test_combined_extension_hooks_multiply_on_e12_rates():
    extensions = ['multi_population', 'phenolics', 'syngas', 'srb']
    assembly = resolve_full_model_assembly(extensions)
    params = _make_params(extensions)
    state = _base_state()
    state.update({'S_H_ion': 1e-7, 'S_nh3': 0, 'X_ac_1': 1, 'X_h2_1': 1,
                  'S_phen': 50, 'S_CO': 0.00103, 'S_H2S': 0.00672})
    rates, _ = biochemical_rates(state, params, assembly=assembly)
    uninhibited = MULTI_POPULATION_EXTENSION._rates(state, params)
    tvfa = sum(state[name] for name in ('S_va', 'S_bu', 'S_pro', 'S_ac'))
    assert rates['rho_E12_uptake_ac_1'] == pytest.approx(
        uninhibited['rho_E12_uptake_ac_1'] * 0.5 / (1 + tvfa / 47.5) * 0.5 * 0.5)
    assert rates['rho_E12_uptake_h2_1'] == pytest.approx(
        uninhibited['rho_E12_uptake_h2_1'] * (0.005 / 0.00603) * 0.5)


def test_multi_population_seeds_sub_populations_from_core_biomass():
    from simulator.core.defaults import make_default_kinetics
    from simulator.core.models import OperatingConditions
    from simulator.full_model.adapter import build_backend_inputs_from_state_maps

    state = _base_state()
    state.update({'X_ac': 0.8, 'X_h2': 0.4})
    inputs = build_backend_inputs_from_state_maps(
        operating_conditions=OperatingConditions(volume_m3=3400, temperature_c=35, hrt_days=20),
        parameters=make_default_kinetics(), influent_values=state, initial_values=state,
        flow_rate_m3_day=170, active_extensions=['multi_population'],
    )
    for values in (inputs.initial_values, inputs.influent_values):
        assert values['X_ac'] == 0.0 and values['X_h2'] == 0.0
        assert values['X_ac_1'] == pytest.approx(0.4) and values['X_ac_2'] == pytest.approx(0.4)
        assert values['X_h2_1'] == pytest.approx(0.2) and values['X_h2_2'] == pytest.approx(0.2)

    # Explicit sub-populations are kept as given.
    state.update({'X_ac_1': 0.1})
    inputs = build_backend_inputs_from_state_maps(
        operating_conditions=OperatingConditions(volume_m3=3400, temperature_c=35, hrt_days=20),
        parameters=make_default_kinetics(), influent_values=state, initial_values=state,
        flow_rate_m3_day=170, active_extensions=['multi_population'],
    )
    assert inputs.initial_values['X_ac_1'] == pytest.approx(0.1)
    assert inputs.initial_values['X_ac'] == pytest.approx(0.8)
