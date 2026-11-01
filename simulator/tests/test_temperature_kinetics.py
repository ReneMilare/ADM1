from __future__ import annotations

import math

import numpy as np
import pytest
from pydantic import ValidationError

from simulator.core.defaults import make_default_feed, make_default_initial_state
from simulator.core.models import KineticParameters, OperatingConditions, SimulationConfig
from simulator.full_model.model import build_full_inputs, resolve_full_parameter_values, _SIEGRIST_THETA
from simulator.full_model.reactor_modes import FullTPADRhs
from simulator.full_model.rhs import FullCSTRRhs
from simulator.service import ADM1SimulationService


def resolved(temp: float, mode: str = "off", **kwargs: object) -> dict[str, float]:
    return resolve_full_parameter_values(
        operating_conditions=OperatingConditions(temperature_c=temp),
        parameters=KineticParameters(temperature_kinetics=mode),
        **kwargs,
    )


def test_default_off_and_validation() -> None:
    assert KineticParameters().temperature_kinetics == "off"
    with pytest.raises(ValidationError):
        KineticParameters(temperature_kinetics="other")
    for temp in (25, 35, 55):
        assert resolved(temp) == resolved(temp, "off")
    assert resolved(35) == resolved(35, "siegrist2002")


def test_all_factors_and_override_reference() -> None:
    base = resolved(25, extension_parameter_overrides={"k_m_ac": 10.0})
    corrected = resolved(25, "siegrist2002", extension_parameter_overrides={"k_m_ac": 10.0})
    for name, theta in _SIEGRIST_THETA.items():
        assert corrected[name] == pytest.approx(base[name] * math.exp(-10 * theta))
    assert corrected["k_m_ac"] == pytest.approx(10 * math.exp(-0.69))
    assert corrected["k_dis"] == base["k_dis"]


def test_tpad_phases_and_stoichiometry() -> None:
    feed = make_default_feed()
    inputs = build_full_inputs(operating_conditions=OperatingConditions(temperature_c=25), feed=feed,
                               initial_state=make_default_initial_state(feed),
                               parameters=KineticParameters(temperature_kinetics="siegrist2002"))
    system = FullTPADRhs(inputs=inputs, thermo_temperature_c=55, meso_temperature_c=35)
    assert system._params1["k_m_ac"] == pytest.approx(8 * math.exp(0.069 * 20))
    assert system._params2["k_m_ac"] == pytest.approx(8)
    off_inputs = build_full_inputs(operating_conditions=OperatingConditions(temperature_c=25), feed=feed,
                                   initial_state=make_default_initial_state(feed), parameters=KineticParameters())
    np.testing.assert_array_equal(FullCSTRRhs(inputs=inputs).biochemical_matrix,
                                  FullCSTRRhs(inputs=off_inputs).biochemical_matrix)


@pytest.mark.parametrize("backend", ["full", "reduced", "pyadm1"])
def test_metadata(backend: str) -> None:
    result = ADM1SimulationService().simulate(parameters=KineticParameters(temperature_kinetics="siegrist2002"),
        simulation=SimulationConfig(backend=backend, duration_days=0.2, evaluation_points=21, persist=False))
    assert result.metadata["temperature_kinetics"] == "siegrist2002"
    assert ("temperature_kinetics_warning" in result.metadata) == (backend != "full")


def test_two_phase_and_extension_rates() -> None:
    from simulator.full_model.reactor_modes import FullTwoPhaseRhs

    feed = make_default_feed()
    inputs = build_full_inputs(operating_conditions=OperatingConditions(temperature_c=25), feed=feed,
                               initial_state=make_default_initial_state(feed),
                               parameters=KineticParameters(temperature_kinetics="siegrist2002"),
                               active_extensions=["lactate"])
    system = FullTwoPhaseRhs(inputs=inputs)
    for phase in (system._params1, system._params2):
        assert phase["k_m_ac"] == pytest.approx(8 * math.exp(-0.69))
    uncorrected = resolve_full_parameter_values(operating_conditions=OperatingConditions(temperature_c=25),
        parameters=KineticParameters(), assembly=inputs.assembly)
    assert inputs.parameter_values["k_m_lac"] == uncorrected["k_m_lac"]


@pytest.mark.parametrize("temperature,mode", [(25, "off"), (35, "siegrist2002")])
def test_full_simulation_reference_equivalence(temperature: float, mode: str) -> None:
    service = ADM1SimulationService()
    settings = dict(operating_conditions=OperatingConditions(temperature_c=temperature),
                    simulation=SimulationConfig(backend="full", duration_days=0.2, evaluation_points=21, persist=False))
    baseline = service.simulate(parameters=KineticParameters(), **settings)
    actual = service.simulate(parameters=KineticParameters(temperature_kinetics=mode), **settings)
    assert actual.series == baseline.series
