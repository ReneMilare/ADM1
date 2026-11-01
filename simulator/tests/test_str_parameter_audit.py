from __future__ import annotations

import math

import numpy as np
import pytest
from pydantic import ValidationError

from simulator.core.defaults import make_default_feed, make_default_initial_state
from simulator.core.models import KineticParameters, OperatingConditions, SimulationConfig
from simulator.full_model.acid_base import solve_acid_base
from simulator.full_model.inhibition import build_inhibition_factors
from simulator.full_model.model import build_full_inputs, resolve_full_parameter_values
from simulator.full_model.parameters import FULL_PARAMETER_DEFAULTS


def resolved(parameter_set: str = "mesophilic_bsm2", mode: str = "off", **kwargs: object) -> dict[str, float]:
    return resolve_full_parameter_values(
        operating_conditions=OperatingConditions(temperature_c=55),
        parameters=KineticParameters(parameter_set=parameter_set, temperature_kinetics=mode),
        **kwargs,
    )


def test_zero_hydrogen_has_exactly_no_hydrogen_inhibition() -> None:
    state = {"S_H_ion": 1e-7, "S_IN": 0.01, "S_h2": 0.0, "S_nh3": 0.0}
    factors = build_inhibition_factors(state, FULL_PARAMETER_DEFAULTS)
    assert factors["I_h2_fa"] == 1.0
    assert factors["I_h2_c4"] == 1.0
    assert factors["I_h2_pro"] == 1.0


def test_acid_base_iteration_limit_returns_species_at_reported_hydrogen() -> None:
    feed = make_default_feed()
    inputs = build_full_inputs(operating_conditions=OperatingConditions(), feed=feed,
                              initial_state=make_default_initial_state(feed), parameters=KineticParameters())
    params = dict(inputs.parameter_values, max_newton_iterations=1.0)
    result = solve_acid_base(inputs.initial_values, params, initial_guess=1e-5)
    assert not result.converged
    assert result.s_hco3_ion == pytest.approx(
        inputs.initial_values["S_IC"] * params["K_a_co2"] / (params["K_a_co2"] + result.s_h_ion), rel=1e-13
    )


THERMOPHILIC_EXPECTED = {
    "k_dis": 1.0, "k_m_su": 70.0, "K_S_su": 1.0, "k_m_aa": 70.0,
    "k_m_fa": 10.0, "k_m_c4": 30.0, "K_S_c4": 0.4, "K_I_h2_c4": 3e-5,
    "k_m_pro": 20.0, "K_S_pro": 0.3, "Y_pro": 0.05, "K_I_h2_pro": 1e-5,
    "k_m_ac": 16.0, "K_S_ac": 0.3, "K_I_nh3": 0.011, "K_S_h2": 5e-5,
    **{f"k_dec_X_{group}": 0.04 for group in ("su", "aa", "fa", "c4", "pro", "ac", "h2")},
}


def test_thermophilic_table62_and_no_unintended_changes() -> None:
    base = resolved()
    thermo = resolved("thermophilic_str")
    for name, value in THERMOPHILIC_EXPECTED.items():
        assert thermo[name] == pytest.approx(value), name
    for name in base.keys() - THERMOPHILIC_EXPECTED.keys():
        assert thermo[name] == base[name], name
    assert thermo["K_I_h2_fa"] == 5e-6


def test_thermophilic_ignores_theta_and_honors_calibration_and_overrides() -> None:
    assert resolved("thermophilic_str") == resolved("thermophilic_str", "siegrist2002")
    calibrated = resolve_full_parameter_values(
        operating_conditions=OperatingConditions(temperature_c=55),
        parameters=KineticParameters(parameter_set="thermophilic_str", k_m_ac=3.0, propionate_yield=0.08),
        extension_parameter_overrides={"k_m_su": 71.0},
    )
    assert calibrated["k_m_ac"] == pytest.approx(32.0)
    assert calibrated["Y_pro"] == pytest.approx(0.1)
    assert calibrated["k_m_su"] == 71.0


def test_parameter_set_validation_serialization_and_default_equivalence() -> None:
    assert KineticParameters().parameter_set == "mesophilic_bsm2"
    params = KineticParameters(parameter_set="thermophilic_str")
    assert KineticParameters.model_validate_json(params.model_dump_json()).parameter_set == "thermophilic_str"
    with pytest.raises(ValidationError):
        params.parameter_set = "unknown"
    for temp in (25.0, 35.0, 55.0):
        options = dict(operating_conditions=OperatingConditions(temperature_c=temp))
        assert resolve_full_parameter_values(parameters=KineticParameters(), **options) == resolve_full_parameter_values(
            parameters=KineticParameters(parameter_set="mesophilic_bsm2"), **options)


@pytest.mark.parametrize("parameter_set", ["mesophilic_bsm2", "thermophilic_str"])
def test_all_19_processes_conserve_cod_carbon_and_nitrogen(parameter_set: str) -> None:
    from simulator.full_model.model import DEFAULT_FULL_MODEL_ASSEMBLY, build_numeric_biochemical_matrix

    params = resolved(parameter_set)
    assembly = DEFAULT_FULL_MODEL_ASSEMBLY
    matrix = build_numeric_biochemical_matrix(params)
    names = assembly.dynamic_state_names
    carbon = {
        "S_su": "C_su", "S_aa": "C_aa", "S_fa": "C_fa", "S_va": "C_va",
        "S_bu": "C_bu", "S_pro": "C_pro", "S_ac": "C_ac", "S_ch4": "C_ch4",
        "S_I": "C_sI", "X_xc": "C_xc", "X_ch": "C_ch", "X_pr": "C_pr",
        "X_li": "C_li", "X_I": "C_xI", **{f"X_{x}": "C_bac" for x in ("su", "aa", "fa", "c4", "pro", "ac", "h2")},
    }
    nitrogen = {"S_aa": "N_aa", "X_pr": "N_aa", "S_I": "N_I", "X_I": "N_I", "X_xc": "N_xc",
                **{f"X_{x}": "N_bac" for x in ("su", "aa", "fa", "c4", "pro", "ac", "h2")}}
    cod_names = set(carbon) | {"S_h2"}
    cod_vector = np.array([float(n in cod_names) for n in names])
    carbon_vector = np.array([1.0 if n == "S_IC" else params[carbon[n]] if n in carbon else 0.0 for n in names])
    nitrogen_vector = np.array([1.0 if n == "S_IN" else params[nitrogen[n]] if n in nitrogen else 0.0 for n in names])
    for vector in (cod_vector, carbon_vector, nitrogen_vector):
        np.testing.assert_allclose(vector @ matrix, np.zeros(19), atol=1e-15, rtol=0.0)


@pytest.mark.parametrize("mode", ["off", "siegrist2002"])
def test_thermophilic_tpad_keeps_fixed_kinetics_but_updates_equilibria(mode: str) -> None:
    from simulator.full_model.reactor_modes import FullTPADRhs

    feed = make_default_feed()
    inputs = build_full_inputs(
        operating_conditions=OperatingConditions(temperature_c=55), feed=feed,
        initial_state=make_default_initial_state(feed),
        parameters=KineticParameters(parameter_set="thermophilic_str", temperature_kinetics=mode),
    )
    system = FullTPADRhs(inputs=inputs, thermo_temperature_c=55, meso_temperature_c=35)
    for name, value in THERMOPHILIC_EXPECTED.items():
        assert system._params1[name] == pytest.approx(value)
        assert system._params2[name] == pytest.approx(value)
    assert system._params1["K_a_IN"] != system._params2["K_a_IN"]
    assert system._rhs1.inputs.parameter_set == "thermophilic_str"


def test_thermophilic_backend_metadata_and_requires_full() -> None:
    from simulator.service import ADM1SimulationService

    service = ADM1SimulationService()
    params = KineticParameters(parameter_set="thermophilic_str", temperature_kinetics="siegrist2002")
    sim = SimulationConfig(backend="full", duration_days=0.2, evaluation_points=21, persist=False)
    result = service.simulate(parameters=params, operating_conditions=OperatingConditions(temperature_c=55), simulation=sim)
    assert result.metadata["parameter_set"] == "thermophilic_str"
    assert result.metadata["temperature_kinetics"] == "siegrist2002"
    assert result.metadata["temperature_kinetics_effective"] == "off"
    assert "K_I_h2_fa" in result.metadata["parameter_set_notes"]
    assert math.isfinite(result.summary.methane_final_m3_day)
    for backend in ("reduced", "pyadm1"):
        with pytest.raises(ValueError, match="requer o backend full"):
            service.simulate(parameters=params, simulation=SimulationConfig(backend=backend, persist=False))


def test_nineteen_cod_stoichiometric_columns_against_str_tables_3_1_and_3_2() -> None:
    from simulator.full_model.model import DEFAULT_FULL_MODEL_ASSEMBLY, build_numeric_biochemical_matrix

    assembly = DEFAULT_FULL_MODEL_ASSEMBLY
    matrix = build_numeric_biochemical_matrix(resolved())
    expected = [
        {"X_xc": -1, "S_I": .1, "X_ch": .2, "X_pr": .2, "X_li": .3, "X_I": .2},
        {"X_ch": -1, "S_su": 1},
        {"X_pr": -1, "S_aa": 1},
        {"X_li": -1, "S_su": .05, "S_fa": .95},
        {"S_su": -1, "S_bu": .117, "S_pro": .243, "S_ac": .369, "S_h2": .171, "X_su": .1},
        {"S_aa": -1, "S_va": .2116, "S_bu": .2392, "S_pro": .046, "S_ac": .368, "S_h2": .0552, "X_aa": .08},
        {"S_fa": -1, "S_ac": .658, "S_h2": .282, "X_fa": .06},
        {"S_va": -1, "S_pro": .5076, "S_ac": .2914, "S_h2": .141, "X_c4": .06},
        {"S_bu": -1, "S_ac": .752, "S_h2": .188, "X_c4": .06},
        {"S_pro": -1, "S_ac": .5472, "S_h2": .4128, "X_pro": .04},
        {"S_ac": -1, "S_ch4": .95, "X_ac": .05},
        {"S_h2": -1, "S_ch4": .94, "X_h2": .06},
        *({"X_xc": 1, f"X_{x}": -1} for x in ("su", "aa", "fa", "c4", "pro", "ac", "h2")),
    ]
    cod_states = [state.name for state in assembly.state_catalog if state.cod_role == "cod" and state.role == "dynamic"]
    for column, expected_values in enumerate(expected):
        for state in cod_states:
            actual = matrix[assembly.dynamic_state_index[state], column]
            assert actual == pytest.approx(expected_values.get(state, 0.0), abs=1e-15), (column + 1, state)


def test_inhibitions_match_bsm2_factors() -> None:
    params = resolved()
    state = {"S_H_ion": 10**-6.5, "S_IN": 1e-4, "S_h2": 1e-5, "S_nh3": .0018}
    factors = build_inhibition_factors(state, params)
    expected_ph_aa = params["K_pH_aa"]**2 / (state["S_H_ion"]**2 + params["K_pH_aa"]**2)
    expected_ph_ac = .5
    expected_ph_h2 = params["K_pH_h2"]**3 / (state["S_H_ion"]**3 + params["K_pH_h2"]**3)
    assert factors["I_IN_lim"] == pytest.approx(.5)
    assert factors["I_h2_fa"] == pytest.approx(1 / 3)
    assert factors["I_h2_c4"] == pytest.approx(.5)
    assert factors["I_h2_pro"] == pytest.approx(1 / (1 + 1e-5 / 3.5e-6))
    assert factors["I_nh3"] == pytest.approx(.5)
    for name, expected in {
        "I_5": expected_ph_aa * .5, "I_6": expected_ph_aa * .5,
        "I_7": expected_ph_aa * .5 / 3, "I_8": expected_ph_aa * .25,
        "I_9": expected_ph_aa * .25, "I_10": expected_ph_aa * .5 / (1 + 1e-5 / 3.5e-6),
        "I_11": expected_ph_ac * .25, "I_12": expected_ph_h2 * .5,
    }.items():
        assert factors[name] == pytest.approx(expected), name
