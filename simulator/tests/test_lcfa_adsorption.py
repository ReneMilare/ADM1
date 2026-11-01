from __future__ import annotations

import numpy as np
import pytest
from scipy.integrate import solve_ivp

from simulator.core.defaults import make_default_kinetics
from simulator.core.models import OperatingConditions
from simulator.full_model.adapter import build_backend_inputs_from_state_maps
from simulator.full_model.lcfa_extension import LCFA_EXTENSION
from simulator.full_model.model import dynamic_state_dict
from simulator.full_model.rhs import FullCSTRRhs
from simulator.tests.test_extensions import _base_state, _make_params, _run_extensions


def test_adsorption_capacity_and_rates():
    params = _make_params('lcfa_adsorption')
    assert params['k_ads_LCFA'] == pytest.approx(0.350)
    assert params['k_des_LCFA'] == pytest.approx(0.2)
    assert params['q_sat_LCFA'] == pytest.approx(0.82 / (0.85 * 1.42))
    state = _base_state()
    state.update(S_fa=0.5, X_LCFA_ads=0.0)
    capacity = params['q_sat_LCFA'] * sum(state[n] for n in ('X_su', 'X_aa', 'X_fa', 'X_c4', 'X_pro', 'X_ac', 'X_h2'))
    rates = LCFA_EXTENSION._rates(state, params)
    assert rates['rho_E5_LCFA_adsorption'] == pytest.approx(0.350 * 0.5 * capacity)
    state['X_LCFA_ads'] = capacity
    rates = LCFA_EXTENSION._rates(state, params)
    assert rates['rho_E5_LCFA_adsorption'] == pytest.approx(0.0, abs=1e-14)
    assert rates['rho_E5_LCFA_desorption'] == pytest.approx(0.2 * capacity)
    state['X_LCFA_ads'] = 1.1 * capacity
    assert LCFA_EXTENSION._rates(state, params)['rho_E5_LCFA_adsorption'] == 0.0
    state.update(S_fa=0.0, X_LCFA_ads=0.0)
    assert LCFA_EXTENSION._rates(state, params)['rho_E5_LCFA_adsorption'] == 0.0


def test_lcfa_batch_cod_balance():
    state = _base_state()
    state.update(S_fa=1.0, X_LCFA_ads=0.3)
    inputs = build_backend_inputs_from_state_maps(
        operating_conditions=OperatingConditions(volume_m3=3400, temperature_c=35, hrt_days=20),
        parameters=make_default_kinetics(), influent_values=state, initial_values=state,
        flow_rate_m3_day=0, active_extensions=['lcfa_adsorption'],
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


def test_lcfa_reference_simulation():
    result = _run_extensions('lcfa_adsorption', extra_initial={'S_fa': 1.0},
                             extra_influent={'S_fa': 1.0}, duration_days=10)
    assert result['profiles']['methane_m3_day'][-1] == pytest.approx(141.93038, rel=1e-3)
    assert result['profiles']['S_fa'][-1] == pytest.approx(0.00909345, rel=1e-3)
