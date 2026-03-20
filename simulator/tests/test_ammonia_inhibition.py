from __future__ import annotations

import numpy as np

from simulator.core.kinetics import _fan_inhibition, _free_ammonia_concentration, _pka_ammonia, reaction_vector
from simulator.core.models import KineticParameters


def _state_with_nitrogen(default_state: np.ndarray, inorganic_nitrogen: float) -> np.ndarray:
    state = np.asarray(default_state, dtype=float).copy()
    state[9] = inorganic_nitrogen
    state[2] = 0.25
    state[3] = 0.08
    state[10] = 5.6
    return state


def test_pka_ammonia_35c() -> None:
    assert abs(_pka_ammonia(35.0) - 8.95) < 0.02


def test_fan_fraction_ph7_35c() -> None:
    fan = _free_ammonia_concentration(1.0, ph=7.0, temperature_c=35.0)
    assert abs(fan - 0.011) < 0.002


def test_fan_fraction_ph8_35c() -> None:
    fan = _free_ammonia_concentration(1.0, ph=8.0, temperature_c=35.0)
    assert abs(fan - 0.10) < 0.02


def test_fan_inhibition_acetoclastic() -> None:
    assert abs(_fan_inhibition(0.015, 0.015) - 0.5) < 1e-9


def test_simple_mode_unchanged(default_state: np.ndarray, default_params: KineticParameters) -> None:
    baseline_reaction, baseline_diag = reaction_vector(
        default_state,
        influent_ph=7.0,
        temperature_c=35.0,
        params=default_params,
        hydrolysis_multiplier=1.0,
        gas_capture_efficiency=1.0,
    )
    explicit_simple = default_params.model_copy(update={"ammonia_inhibition_mode": "simple"})
    candidate_reaction, candidate_diag = reaction_vector(
        default_state,
        influent_ph=7.0,
        temperature_c=35.0,
        params=explicit_simple,
        hydrolysis_multiplier=1.0,
        gas_capture_efficiency=1.0,
    )
    np.testing.assert_allclose(candidate_reaction, baseline_reaction)
    assert candidate_diag["methane_rate_m3_m3_day"] == baseline_diag["methane_rate_m3_m3_day"]


def test_fan_mode_reduces_methane_high_nitrogen(default_state: np.ndarray, default_params: KineticParameters) -> None:
    state = _state_with_nitrogen(default_state, inorganic_nitrogen=3.5)
    _, simple_diag = reaction_vector(
        state,
        influent_ph=7.8,
        temperature_c=35.0,
        params=default_params.model_copy(update={"ammonia_inhibition_mode": "simple"}),
        hydrolysis_multiplier=1.0,
        gas_capture_efficiency=1.0,
    )
    _, fan_diag = reaction_vector(
        state,
        influent_ph=7.8,
        temperature_c=35.0,
        params=default_params.model_copy(update={"ammonia_inhibition_mode": "fan"}),
        hydrolysis_multiplier=1.0,
        gas_capture_efficiency=1.0,
    )
    assert fan_diag["methane_rate_m3_m3_day"] < simple_diag["methane_rate_m3_m3_day"]
    assert fan_diag["free_ammonia_kgN_m3"] > 0.0


def test_fan_mode_low_nitrogen_minimal_effect(default_state: np.ndarray, default_params: KineticParameters) -> None:
    # Use N=0.1 kgN/m³ to ensure truly minimal FAN inhibition.
    # At pH=7.0, T=35°C and N=0.1: FAN ≈ 1.1 mgN/L << Ki_ac=15 mgN/L → <7% inhibition.
    # N=0.5 would give FAN≈5.5 mgN/L causing ~27% inhibition — non-trivial, not "minimal".
    state = _state_with_nitrogen(default_state, inorganic_nitrogen=0.1)
    _, simple_diag = reaction_vector(
        state,
        influent_ph=7.0,
        temperature_c=35.0,
        params=default_params.model_copy(update={"ammonia_inhibition_mode": "simple"}),
        hydrolysis_multiplier=1.0,
        gas_capture_efficiency=1.0,
    )
    _, fan_diag = reaction_vector(
        state,
        influent_ph=7.0,
        temperature_c=35.0,
        params=default_params.model_copy(update={"ammonia_inhibition_mode": "fan"}),
        hydrolysis_multiplier=1.0,
        gas_capture_efficiency=1.0,
    )
    assert abs(fan_diag["methane_rate_m3_m3_day"] - simple_diag["methane_rate_m3_m3_day"]) < 0.05


def test_differential_sensitivity(default_state: np.ndarray, default_params: KineticParameters) -> None:
    state = _state_with_nitrogen(default_state, inorganic_nitrogen=3.0)
    _, diagnostics = reaction_vector(
        state,
        influent_ph=7.8,
        temperature_c=35.0,
        params=default_params.model_copy(update={"ammonia_inhibition_mode": "fan"}),
        hydrolysis_multiplier=1.0,
        gas_capture_efficiency=1.0,
    )
    assert diagnostics["inh_nh3_acetoclastic"] < diagnostics["inh_nh3_hydrogenotrophic"]
    assert diagnostics["inh_nh3_propionate"] < diagnostics["inh_nh3_acidogens"]
