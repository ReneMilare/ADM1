from __future__ import annotations

import numpy as np
import pytest
from pydantic import ValidationError
from scipy.integrate import solve_ivp

from simulator.core.defaults import make_default_kinetics
from simulator.core.models import FeedDefinition, OperatingConditions, ReactorConfig, SimulationConfig, TPADConfig
from simulator.full_model.model import build_full_inputs_from_state_maps, dynamic_state_dict
from simulator.full_model.reactor_modes import build_reactor_mode
from simulator.full_model.solver import simulate_with_full_inputs
from simulator.reactor_models import build_reactor


def _inputs():
    state = {"S_IC": 0.1, "S_IN": 0.01, "S_cation": 0.1, "S_anion": 0.01}
    return build_full_inputs_from_state_maps(
        operating_conditions=OperatingConditions(volume_m3=3400, hrt_days=20),
        parameters=make_default_kinetics(), influent_values=state, initial_values=state,
        flow_rate_m3_day=170,
    )


def test_tpad_absolute_hrt_and_volumes():
    cfg = ReactorConfig(reactor_type="tpad", tpad=TPADConfig(thermo_hrt_days=3, meso_hrt_days=15))
    op = OperatingConditions(volume_m3=3400, hrt_days=20)
    reduced = build_reactor(cfg)
    assert [1 / reduced.segment_dilution_rate(i, op) for i in range(2)] == pytest.approx([3, 15])
    assert [reduced.segment_volume(i, op) for i in range(2)] == pytest.approx([510, 2550])
    assert reduced.segment_volumes(FeedDefinition(flow_rate_m3_day=100), op) == pytest.approx([300, 1500])
    full = build_reactor_mode("tpad", _inputs(), reactor_config=cfg)
    assert [full._params1["V_liq"], full._params2["V_liq"]] == pytest.approx([510, 2550])
    assert [1 / full._q_over_v1, 1 / full._q_over_v2] == pytest.approx([3, 15])


def test_tpad_full_metadata_reports_mismatch():
    cfg = ReactorConfig(reactor_type="tpad")
    result = simulate_with_full_inputs(inputs=_inputs(), simulation=SimulationConfig(duration_days=0.2, evaluation_points=21), reactor_config=cfg)
    assert result["metadata"]["effective_hrt_days"] == pytest.approx(18)
    assert result["metadata"]["hrt_warning"]


@pytest.mark.parametrize("kind", ["uasb", "plug_flow", "two_phase", "tpad"])
@pytest.mark.parametrize("capture", [None, 0.0, 1.0])
def test_capture_is_bounded(kind, capture):
    reactor = build_reactor(ReactorConfig(reactor_type=kind, gas_capture_efficiency=capture))
    assert all(0 <= reactor.gas_capture_efficiency(i) <= 1 for i in range(reactor.segment_count))


@pytest.mark.parametrize("capture", [-0.01, 1.01])
def test_capture_config_rejects_out_of_range(capture):
    with pytest.raises(ValidationError):
        ReactorConfig(gas_capture_efficiency=capture)


def test_plug_flow_parallel_valve_conductance_and_headspace():
    inputs = _inputs()
    count = 4
    system = build_reactor_mode("plug_flow", inputs, reactor_config=ReactorConfig(reactor_type="plug_flow", segments=count))
    assert system._seg_params["V_gas"] * count == pytest.approx(inputs.parameter_values["V_gas"])
    assert system._seg_params["k_p"] * count == pytest.approx(inputs.parameter_values["k_p"])
    cstr = build_reactor_mode("cstr", inputs)
    initial = inputs.dynamic_initial.copy()
    initial[inputs.assembly.dynamic_state_index["S_ch4"]] = 0.07
    gas_indices = [inputs.assembly.dynamic_state_index[name] for name in ("S_gas_h2", "S_gas_ch4", "S_gas_co2")]
    def gas_rhs(t, gas):
        state = initial.copy()
        state[gas_indices] = gas
        return cstr(t, state)[gas_indices]
    equilibrium = solve_ivp(gas_rhs, (0, 20), initial[gas_indices], method="BDF", rtol=1e-8, atol=1e-10)
    assert equilibrium.success
    initial[gas_indices] = equilibrium.y[:, -1]
    state = dynamic_state_dict(initial, assembly=inputs.assembly)
    q_cstr = cstr.evaluate(dynamic_values=state, use_cache=False).gas_transfer.q_gas
    q_segments = count * system._rhs.evaluate(dynamic_values=state, use_cache=False).gas_transfer.q_gas
    assert q_cstr > 0
    assert q_segments == pytest.approx(q_cstr)
    derivatives = system(0, np.tile(initial, count)).reshape(count, -1)
    np.testing.assert_allclose(derivatives[:, gas_indices], np.tile(gas_rhs(0, initial[gas_indices]), (count, 1)), atol=1e-9)
    assert np.max(np.abs(derivatives[:, gas_indices])) < 1e-5
    gas = cstr.evaluate(dynamic_values=state, use_cache=False).gas_transfer
    assert gas.p_total == pytest.approx(inputs.parameter_values["p_atm"], abs=0.03)


def test_reduced_tpad_reports_effective_hrt():
    from simulator.core.defaults import make_default_feed, make_default_initial_state, make_default_kinetics
    from simulator.core.models import OperatingConditions, ReactorConfig, SimulationConfig, TPADConfig
    from simulator.service import ADM1SimulationService

    result = ADM1SimulationService().simulate(
        reactor=ReactorConfig(reactor_type="tpad", tpad=TPADConfig(thermo_hrt_days=3.0, meso_hrt_days=15.0)),
        operating_conditions=OperatingConditions(volume_m3=3400, temperature_c=35, hrt_days=20),
        feed=make_default_feed(), initial_state=make_default_initial_state(), parameters=make_default_kinetics(),
        simulation=SimulationConfig(duration_days=5.0, evaluation_points=21, backend="reduced", persist=False),
    )
    assert result.metadata["effective_hrt_days"] == 18.0
    assert "hrt_warning" in result.metadata
