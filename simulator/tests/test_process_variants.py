from __future__ import annotations

import numpy as np

from simulator.core.defaults import make_default_feed, make_default_initial_state, make_default_kinetics, make_default_operating_conditions, make_default_simulation_config
from simulator.core.kinetics import reaction_vector
from simulator.core.models import ReactorConfig, TPADConfig
from simulator.reactor_models import BatchReactor, TPADReactor, TwoPhaseReactor, build_reactor
from simulator.scenario_store import ScenarioStore
from simulator.service import ADM1SimulationService


def test_build_reactor_registry() -> None:
    assert build_reactor(ReactorConfig(reactor_type="batch")).__class__.__name__ == "BatchReactor"
    assert build_reactor(ReactorConfig(reactor_type="two_phase")).__class__.__name__ == "TwoPhaseReactor"
    assert build_reactor(ReactorConfig(reactor_type="tpad")).__class__.__name__ == "TPADReactor"


def test_new_reactors_fallback_to_reduced() -> None:
    service = ADM1SimulationService(store=ScenarioStore())
    simulation = make_default_simulation_config().model_copy(update={"duration_days": 12.0, "evaluation_points": 61, "persist": False, "backend": "pyadm1"})
    result = service.simulate("two_phase", simulation=simulation)
    assert result.metadata["backend_requested"] == "pyadm1"
    assert result.metadata["backend_used"] == "reduced"


def test_two_phase_produces_more_methane_than_cstr() -> None:
    # At 25 d the CSTR is in a high-methane transient (initial biomass still active), so
    # comparison requires reaching near steady-state (≥ 60 d) where the two-phase
    # hydrolysis advantage (1.35× multiplier in phase 1) outweighs the startup lag.
    service = ADM1SimulationService(store=ScenarioStore())
    simulation = make_default_simulation_config().model_copy(update={"duration_days": 60.0, "evaluation_points": 121, "persist": False, "backend": "reduced"})
    cstr = service.simulate("cstr", simulation=simulation)
    two_phase = service.simulate("two_phase", simulation=simulation)
    assert two_phase.summary.methane_final_m3_day >= cstr.summary.methane_final_m3_day


def test_two_phase_phase1_low_methanogenesis() -> None:
    # Phase 1 operates at short HRT (20 % of total) so all methanogens wash out —
    # confirmed by the biomass viability condition Y×k_m < decay + 1/HRT for all
    # methanogenic groups at the phase-1 dilution rate (0.25 d⁻¹).
    # The thermodynamically correct pH (from Henderson-Hasselbalch charge balance)
    # reflects the actual alkalinity/VFA balance, not a heuristic setpoint anchor.
    # We therefore verify the acidogenic nature of phase 1 by its near-zero methane
    # output rather than by an artificially anchored pH value.
    service = ADM1SimulationService(store=ScenarioStore())
    simulation = make_default_simulation_config().model_copy(update={"duration_days": 60.0, "evaluation_points": 121, "persist": False, "backend": "reduced"})
    result = service.simulate("two_phase", simulation=simulation)
    total_methane = result.series["methane_m3_day"][-1]
    phase1_methane = result.series["phase1_methane_rate_m3_day"][-1]
    # Phase 1 should contribute < 5 % of total methane (methanogens wash out)
    assert phase1_methane / max(total_methane, 1e-9) < 0.05


def test_tpad_thermo_accelerates_hydrolysis() -> None:
    service = ADM1SimulationService(store=ScenarioStore())
    simulation = make_default_simulation_config().model_copy(update={"duration_days": 12.0, "evaluation_points": 61, "persist": False, "backend": "reduced"})
    result = service.simulate("tpad", simulation=simulation)
    assert result.series["thermo_hydrolysis_rate"][0] >= 2.0 * result.series["meso_hydrolysis_rate"][0]


def test_tpad_total_hrt_conservation() -> None:
    config = ReactorConfig(reactor_type="tpad", tpad=TPADConfig(thermo_hrt_days=3.0, meso_hrt_days=15.0))
    operating = make_default_operating_conditions().model_copy(update={"hrt_days": 18.0})
    reactor = TPADReactor(config)
    total_hrt = sum(1.0 / reactor.segment_dilution_rate(index, operating) for index in range(reactor.segment_count))
    assert abs(total_hrt - 18.0) < 1e-9


def test_batch_no_dilution() -> None:
    reactor = BatchReactor(ReactorConfig(reactor_type="batch"))
    feed = make_default_feed()
    initial = make_default_initial_state(feed)
    operating = make_default_operating_conditions()
    kinetics = make_default_kinetics()
    state = reactor.build_batch_initial_vector(feed, initial)
    rhs = reactor.rhs(0.0, state, feed=feed, operating_conditions=operating, parameters=kinetics)
    reaction, _ = reaction_vector(
        state,
        influent_ph=feed.ph,
        temperature_c=operating.temperature_c,
        params=kinetics,
        hydrolysis_multiplier=reactor.hydrolysis_multiplier(0),
        gas_capture_efficiency=reactor.gas_capture_efficiency(0),
    )
    np.testing.assert_allclose(rhs, reaction)


def test_batch_methane_cumulative_increases() -> None:
    service = ADM1SimulationService(store=ScenarioStore())
    simulation = make_default_simulation_config().model_copy(update={"duration_days": 30.0, "evaluation_points": 121, "persist": False, "backend": "reduced"})
    result = service.simulate("batch", simulation=simulation)
    methane = np.asarray(result.series["methane_m3_day"], dtype=float)
    time = np.asarray(result.time_days, dtype=float)
    cumulative = [0.0]
    for index in range(1, len(time)):
        cumulative.append(cumulative[-1] + float(np.trapezoid(methane[index - 1 : index + 1], time[index - 1 : index + 1])))
    assert np.all(np.diff(cumulative) >= -1e-9)


def test_batch_substrate_depletion() -> None:
    service = ADM1SimulationService(store=ScenarioStore())
    simulation = make_default_simulation_config().model_copy(update={"duration_days": 40.0, "evaluation_points": 161, "persist": False, "backend": "reduced"})
    result = service.simulate("batch", simulation=simulation)
    assert result.series["soluble_cod"][-1] < result.series["soluble_cod"][0]
    assert result.summary.methane_cumulative_m3 > 0.0

