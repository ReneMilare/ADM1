from __future__ import annotations

import numpy as np
import pytest

from simulator.core.kinetics import (
    ACIDOGENESIS_SPLITS,
    PROPIONATE_SPLITS,
    STATE_INDEX,
    _ammonia_inhibition,
    _hydrogen_inhibition,
    _ph_inhibition,
    _temperature_factor,
    estimate_ph,
    reaction_vector,
)
from simulator.core.models import KineticParameters, STATE_NAMES


# ---------------------------------------------------------------------------
# COD mass-balance
# ---------------------------------------------------------------------------


def test_cod_balance_acidogenesis(default_params: KineticParameters) -> None:
    total = sum(ACIDOGENESIS_SPLITS.values()) + default_params.acidogen_yield
    assert abs(total - 1.0) < 1e-9, f"Acidogenesis COD splits do not sum to 1.0: {total}"


def test_cod_balance_propionate(default_params: KineticParameters) -> None:
    total = sum(PROPIONATE_SPLITS.values()) + default_params.propionate_yield
    assert abs(total - 1.0) < 1e-9, f"Propionate COD splits do not sum to 1.0: {total}"


def test_reaction_vector_cod_liquid_balance(default_state: np.ndarray, default_params: KineticParameters) -> None:
    reaction, diag = reaction_vector(
        default_state,
        influent_ph=7.0,
        temperature_c=35.0,
        params=default_params,
        hydrolysis_multiplier=1.0,
        gas_capture_efficiency=1.0,
    )
    cod_indices = [STATE_INDEX[name] for name in STATE_NAMES if name not in {"inorganic_nitrogen", "alkalinity"}]
    liquid_cod_change = float(np.sum(reaction[cod_indices]))
    expected_sink = -(
        diag["acetate_methanogenesis_rate"] * (1.0 - default_params.acetoclastic_yield)
        + diag["hydrogen_methanogenesis_rate"] * (1.0 - default_params.hydrogenotrophic_yield)
        + default_params.gas_stripping_h2 * default_state[STATE_INDEX["hydrogen"]]
    )
    assert abs(liquid_cod_change - expected_sink) < 1e-9


# ---------------------------------------------------------------------------
# pH inhibition
# ---------------------------------------------------------------------------


def test_ph_inhibition_at_optimum(default_params: KineticParameters) -> None:
    factor = _ph_inhibition(default_params.ph_optimum, default_params)
    assert abs(factor - 1.0) < 1e-6


def test_ph_inhibition_below_optimum(default_params: KineticParameters) -> None:
    factor = _ph_inhibition(default_params.ph_optimum - 1.0, default_params)
    assert factor < 1.0


def test_ph_inhibition_floor(default_params: KineticParameters) -> None:
    factor = _ph_inhibition(4.0, default_params)
    assert abs(factor - 0.05) < 1e-9


# ---------------------------------------------------------------------------
# Ammonia inhibition
# ---------------------------------------------------------------------------


def test_ammonia_inhibition_below_threshold(default_params: KineticParameters) -> None:
    below = max(default_params.nitrogen_inhibition_threshold - 0.5, 0.0)
    factor = _ammonia_inhibition(below, default_params)
    assert abs(factor - 1.0) < 1e-9


def test_ammonia_inhibition_high_nitrogen(default_params: KineticParameters) -> None:
    high = default_params.nitrogen_inhibition_threshold + default_params.ammonia_inhibition_k * 10
    factor = _ammonia_inhibition(high, default_params)
    assert factor < 0.3


def test_ammonia_inhibition_floor(default_params: KineticParameters) -> None:
    factor = _ammonia_inhibition(1e6, default_params)
    assert abs(factor - 0.1) < 1e-9


# ---------------------------------------------------------------------------
# Hydrogen inhibition
# ---------------------------------------------------------------------------


def test_hydrogen_inhibition_near_zero(default_params: KineticParameters) -> None:
    factor = _hydrogen_inhibition(0.0, default_params)
    assert abs(factor - 1.0) < 1e-6


def test_hydrogen_inhibition_high_h2(default_params: KineticParameters) -> None:
    high = default_params.hydrogen_inhibition_k * 100
    factor = _hydrogen_inhibition(high, default_params)
    assert factor < 0.1


def test_hydrogen_inhibition_floor(default_params: KineticParameters) -> None:
    factor = _hydrogen_inhibition(1e6, default_params)
    assert abs(factor - 0.08) < 1e-9


# ---------------------------------------------------------------------------
# Temperature factor
# ---------------------------------------------------------------------------


def test_temperature_factor_at_reference(default_params: KineticParameters) -> None:
    factor = _temperature_factor(35.0, default_params)
    assert abs(factor - 1.0) < 1e-6


def test_temperature_factor_clamped_min(default_params: KineticParameters) -> None:
    factor = _temperature_factor(-100.0, default_params)
    assert abs(factor - 0.25) < 1e-9


def test_temperature_factor_clamped_max(default_params: KineticParameters) -> None:
    factor = _temperature_factor(500.0, default_params)
    assert abs(factor - 3.0) < 1e-9


# ---------------------------------------------------------------------------
# estimate_ph
# ---------------------------------------------------------------------------


def test_estimate_ph_within_bounds(default_state: np.ndarray) -> None:
    ph = estimate_ph(default_state, influent_ph=7.0, temperature_c=35.0)
    assert 4.0 <= ph <= 9.0


# ---------------------------------------------------------------------------
# reaction_vector
# ---------------------------------------------------------------------------


def test_reaction_vector_shape(default_state: np.ndarray, default_params: KineticParameters) -> None:
    reaction, _ = reaction_vector(
        default_state,
        influent_ph=7.0,
        temperature_c=35.0,
        params=default_params,
        hydrolysis_multiplier=1.0,
        gas_capture_efficiency=1.0,
    )
    assert reaction.shape == default_state.shape


def test_reaction_vector_has_diagnostics(default_state: np.ndarray, default_params: KineticParameters) -> None:
    _, diag = reaction_vector(
        default_state,
        influent_ph=7.0,
        temperature_c=35.0,
        params=default_params,
        hydrolysis_multiplier=1.0,
        gas_capture_efficiency=1.0,
    )
    assert "methane_rate_m3_m3_day" in diag
    assert "ph" in diag
    assert "hydrolysis_rate" in diag
    assert "acetate_methanogenesis_rate" in diag


def test_reaction_vector_methane_rate_positive(default_state: np.ndarray, default_params: KineticParameters) -> None:
    _, diag = reaction_vector(
        default_state,
        influent_ph=7.0,
        temperature_c=35.0,
        params=default_params,
        hydrolysis_multiplier=1.0,
        gas_capture_efficiency=1.0,
    )
    assert diag["methane_rate_m3_m3_day"] > 0.0


def test_reaction_vector_zero_capture_gives_zero_methane(
    default_state: np.ndarray, default_params: KineticParameters
) -> None:
    _, diag = reaction_vector(
        default_state,
        influent_ph=7.0,
        temperature_c=35.0,
        params=default_params,
        hydrolysis_multiplier=1.0,
        gas_capture_efficiency=0.0,
    )
    assert diag["methane_rate_m3_m3_day"] == 0.0
