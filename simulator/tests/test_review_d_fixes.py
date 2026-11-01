from __future__ import annotations

import math

import numpy as np
import pytest

from simulator.core.defaults import make_default_feed, make_default_initial_state
from simulator.core.pyadm1_backend import _build_influent_frame, _build_initial_frame
from simulator.core.defaults import make_default_operating_conditions


def _charge_balance_ph(row: dict[str, float], temperature_c: float) -> float:
    """Solve the charge balance of a frame row for pH by bisection (independent of the builder)."""
    t_k = temperature_c + 273.15

    def vh(dh: float) -> float:
        return math.exp((dh / (100.0 * 0.083145)) * (1.0 / 298.15 - 1.0 / t_k))

    k_w = 1e-14 * vh(55900.0)
    kco2 = 10 ** -6.35 * vh(7646.0)
    kin = 10 ** -9.25 * vh(51965.0)

    def f(ph: float) -> float:
        h = 10 ** -ph
        return (
            row["S_cation"] - row["S_anion"] + row["S_IN"] * h / (kin + h) + h
            - kco2 * row["S_IC"] / (kco2 + h)
            - 10 ** -4.76 * row["S_ac"] / (10 ** -4.76 + h) / 64.0
            - 10 ** -4.88 * row["S_pro"] / (10 ** -4.88 + h) / 112.0
            - 10 ** -4.82 * row["S_bu"] / (10 ** -4.82 + h) / 160.0
            - 10 ** -4.86 * row["S_va"] / (10 ** -4.86 + h) / 208.0
            - k_w / h
        )

    lo, hi = 2.0, 12.0
    for _ in range(100):
        mid = 0.5 * (lo + hi)
        if f(mid) > 0:  # f decreases with pH
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


@pytest.mark.parametrize("ph", [5.5, 7.0, 8.5])
def test_requested_feed_ph_is_preserved_by_charge_balance(ph: float) -> None:
    feed = make_default_feed().model_copy(update={"ph": ph})
    operating = make_default_operating_conditions()
    influent = _build_influent_frame(time_grid=np.asarray([0.0]), feed=feed, operating_conditions=operating)
    initial = _build_initial_frame(
        initial_state=make_default_initial_state(feed), feed=feed, temperature_c=operating.temperature_c
    )
    for frame in (influent, initial):
        row = frame.iloc[0].to_dict()
        assert _charge_balance_ph(row, operating.temperature_c) == pytest.approx(ph, abs=0.01)
        assert min(row["S_cation"], row["S_anion"]) == 0.0


# --- 2. phenolics: nitrogen limitation -------------------------------------------------

from simulator.full_model.extension_registry import resolve_full_model_assembly  # noqa: E402
from simulator.full_model.kinetics import biochemical_rates  # noqa: E402
from simulator.full_model.model import build_numeric_biochemical_matrix  # noqa: E402
from simulator.tests.test_extensions import _make_params  # noqa: E402


def _full_state(extensions: list[str], **overrides: float) -> tuple[dict[str, float], dict[str, float], object]:
    assembly = resolve_full_model_assembly(extensions)
    params = _make_params(extensions)
    state = {name: 0.1 for name in assembly.full_state_names}
    state.update({"S_H_ion": 10 ** -7.3, "S_nh3": 0.001})
    state.update(overrides)
    return state, params, assembly


def test_phenolics_uptake_needs_inorganic_nitrogen() -> None:
    state, params, assembly = _full_state(["phenolics"], S_IN=0.0, S_phen=0.2, S_ben=0.2)
    rates, _ = biochemical_rates(state, params, assembly=assembly)
    assert rates["rho_E11_uptake_phenolics"] == 0.0
    assert rates["rho_E11_uptake_benzoate"] == 0.0
    matrix = build_numeric_biochemical_matrix(params, assembly=assembly)
    index = assembly.dynamic_state_index["S_IN"]
    vector = np.asarray([rates[name] for name in assembly.biochemical_process_names])
    d_sin = float(matrix[index, :] @ vector)
    assert d_sin >= 0.0


# --- 3. multi_population forwards trace-element limitation ---------------------------

def test_multi_population_receives_trace_element_factors() -> None:
    exts = ["multi_population", "trace_elements"]
    state, params, assembly = _full_state(exts, S_Ni=0.0, S_Co=0.0, S_Fe2_te=0.0)
    rates, _ = biochemical_rates(state, params, assembly=assembly)
    # Ni/Co/Fe = 0 -> Monod factors are 0 -> the sub-populations are fully limited.
    for name in ("rho_E12_uptake_ac_1", "rho_E12_uptake_ac_2", "rho_E12_uptake_h2_1", "rho_E12_uptake_h2_2"):
        assert rates[name] == pytest.approx(0.0, abs=1e-12)
    # With trace elements supplied they are scaled by the same factor the core process would get.
    state2, params2, assembly2 = _full_state(exts, S_Ni=1e-6, S_Co=1e-7, S_Fe2_te=1e-5)
    rates2, _ = biochemical_rates(state2, params2, assembly=assembly2)
    from simulator.full_model.trace_elements_extension import TRACE_ELEMENTS_EXTENSION

    factors = TRACE_ELEMENTS_EXTENSION._inhibition(state2, params2)
    base = _full_state(["multi_population"], S_Ni=1e-6)
    unlimited, _ = biochemical_rates(base[0], base[1], assembly=base[2])
    assert rates2["rho_E12_uptake_ac_1"] == pytest.approx(
        unlimited["rho_E12_uptake_ac_1"] * factors["rho_11_uptake_acetate"], rel=1e-9)
    assert rates2["rho_E12_uptake_h2_2"] == pytest.approx(
        unlimited["rho_E12_uptake_h2_2"] * factors["rho_12_uptake_hydrogen"], rel=1e-9)


# --- 4. multi_population seeding -----------------------------------------------------

from simulator.full_model.model import _seed_multi_population  # noqa: E402


def test_seed_moves_core_biomass_even_if_subpopulations_given() -> None:
    values = {"X_ac": 1.0, "X_ac_1": 0.1, "X_ac_2": 0.0, "X_h2": 0.0, "X_h2_1": 0.0, "X_h2_2": 0.0}
    _seed_multi_population(values)
    assert values["X_ac"] == 0.0
    assert values["X_ac_1"] + values["X_ac_2"] == pytest.approx(1.1)


# --- 5. AmmoniaSpike ---------------------------------------------------------------

from pydantic import ValidationError  # noqa: E402

from simulator.digital_twin.scenarios import AmmoniaSpike  # noqa: E402


def test_chloride_ammonia_spike_cannot_remove_nitrogen() -> None:
    with pytest.raises(ValidationError, match="factor >= 1"):
        AmmoniaSpike(t0_days=1.0, t1_days=2.0, factor=0.5, counter_ion="chloride")
    AmmoniaSpike(t0_days=1.0, t1_days=2.0, factor=0.5, counter_ion="none")
    AmmoniaSpike(t0_days=1.0, t1_days=2.0, factor=2.0, counter_ion="chloride")


# --- 6. zero denominators -----------------------------------------------------------

from simulator.core.defaults import make_default_kinetics  # noqa: E402
from simulator.core.models import OperatingConditions  # noqa: E402
from simulator.full_model.model import resolve_full_parameter_values  # noqa: E402


@pytest.mark.parametrize("name,extensions", [("K_I_phen", ["phenolics"]), ("K_S_ac", [])])
def test_zero_denominator_parameter_is_rejected(name: str, extensions: list[str]) -> None:
    with pytest.raises(ValueError, match=name):
        resolve_full_parameter_values(
            operating_conditions=OperatingConditions(volume_m3=3400.0, temperature_c=35.0, hrt_days=20.0),
            parameters=make_default_kinetics(),
            flow_rate_m3_day=170.0,
            assembly=resolve_full_model_assembly(extensions),
            extension_parameter_overrides={name: 0.0},
        )
