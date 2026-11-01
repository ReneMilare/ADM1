from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from simulator.core.defaults import (
    make_default_feed,
    make_default_initial_state,
    make_default_kinetics,
    make_default_operating_conditions,
)
from simulator.core.models import SimulationConfig
from simulator.core.pyadm1_backend import (
    INITIAL_COLUMNS,
    _build_influent_frame,
    _build_initial_frame,
    _patched_pyadm1_source,
)
from simulator.service import ADM1SimulationService


@pytest.fixture
def runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    feed = make_default_feed()
    operating = make_default_operating_conditions()
    _build_influent_frame(
        time_grid=np.asarray([0.0, 5.0]), feed=feed, operating_conditions=operating,
    ).to_csv(tmp_path / "digester_influent.csv", index=False)
    _build_initial_frame(
        initial_state=make_default_initial_state(feed), feed=feed,
    ).to_csv(tmp_path / "digester_initial.csv", index=False)
    source = _patched_pyadm1_source(
        operating_conditions=operating, feed=feed, parameters=make_default_kinetics(),
        simulation=SimulationConfig(persist=False),
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MPLCONFIGDIR", str(tmp_path / "matplotlib"))
    namespace: dict[str, Any] = {}
    exec(compile(source.split("## time array definition")[0], "<PyADM1 runtime>", "exec"), namespace)
    return namespace


def test_rhs_recomputes_algebraic_species_from_current_totals(runtime: dict[str, Any]) -> None:
    state = np.asarray(runtime["state_zero"], dtype=float)
    changed = state.copy()
    for name in ("S_h2", "S_H_ion", "S_va_ion", "S_bu_ion", "S_pro_ion", "S_ac_ion", "S_hco3_ion", "S_nh3"):
        changed[INITIAL_COLUMNS.index(name)] *= 0.1
    expected = runtime["ADM1_ODE"](0.0, state)
    actual = runtime["ADM1_ODE"](0.0, changed)
    np.testing.assert_allclose(actual, expected, rtol=1e-7, atol=1e-10)


@pytest.mark.parametrize("success", [False, True])
def test_incomplete_integration_is_rejected(
    runtime: dict[str, Any], monkeypatch: pytest.MonkeyPatch, success: bool,
) -> None:
    incomplete = SimpleNamespace(
        success=success, t=np.asarray([0.0, 0.5]), y=np.zeros((38, 2)),
        message="integration stopped early",
    )
    monkeypatch.setattr(runtime["scipy"].integrate, "solve_ivp", lambda *a, **kw: incomplete)
    with pytest.raises(RuntimeError, match="PyADM1 integration"):
        runtime["simulate"]([0.0, 5.0], "BDF")


@pytest.mark.parametrize("nitrogen_kg_m3", [0.1, 1.3, 2.8])
def test_algebraic_projection_preserves_totals_and_charge(
    runtime: dict[str, Any], nitrogen_kg_m3: float,
) -> None:
    state = np.asarray(runtime["state_zero"], dtype=float)
    state[INITIAL_COLUMNS.index("S_IN")] = nitrogen_kg_m3 / 14.0
    original = state.copy()
    projected = runtime["_solve_algebraic"](state)
    values = dict(zip(INITIAL_COLUMNS, projected, strict=True))
    np.testing.assert_array_equal(state, original)
    algebraic = {"S_h2", "S_H_ion", "S_va_ion", "S_bu_ion", "S_pro_ion", "S_ac_ion", "S_hco3_ion", "S_co2", "S_nh3", "S_nh4_ion"}
    for name, before, after in zip(INITIAL_COLUMNS, original, projected, strict=True):
        if name not in algebraic:
            assert after == before
    assert values["S_hco3_ion"] + values["S_co2"] - values["S_IC"] == pytest.approx(0.0, abs=1e-12)
    assert values["S_nh3"] + values["S_nh4_ion"] - values["S_IN"] == pytest.approx(0.0, abs=1e-12)
    charge = values["S_cation"] + values["S_nh4_ion"] + values["S_H_ion"]
    charge -= values["S_hco3_ion"] + values["S_anion"] + runtime["K_w"] / values["S_H_ion"]
    for acid, cod_per_kmol in (("va", 208.0), ("bu", 160.0), ("pro", 112.0), ("ac", 64.0)):
        total, ion = values[f"S_{acid}"], values[f"S_{acid}_ion"]
        assert 0.0 <= ion <= total
        assert ion * (runtime[f"K_a_{acid}"] + values["S_H_ion"]) - runtime[f"K_a_{acid}"] * total == pytest.approx(0.0, abs=1e-12)
        charge -= ion / cod_per_kmol
    assert charge == pytest.approx(0.0, abs=1e-12)
    assert values["S_co2"] >= 0.0
    assert 0.0 <= values["S_nh3"] <= values["S_IN"]


@pytest.fixture(scope="module")
def default_results() -> dict[str, Any]:
    service = ADM1SimulationService()
    return {
        backend: service.simulate(
            "cstr",
            operating_conditions=make_default_operating_conditions(),
            feed=make_default_feed(),
            simulation=SimulationConfig(
                duration_days=200, evaluation_points=41, backend=backend, persist=False,
            ),
        )
        for backend in ("pyadm1", "full")
    }


def test_default_absolute_feed_matches_full_without_negative_carbon(default_results: dict[str, Any]) -> None:
    pyadm1, full = default_results["pyadm1"], default_results["full"]
    assert min(pyadm1.series["alkalinity"]) >= 0.0
    for metric in ("ph_final", "vfa_final", "methane_final_m3_day"):
        assert getattr(pyadm1.summary, metric) == pytest.approx(
            getattr(full.summary, metric), rel=0.03,
        )


def test_output_grid_does_not_change_the_solution(default_results: dict[str, Any]) -> None:
    coarse = ADM1SimulationService().simulate(
        "cstr", operating_conditions=make_default_operating_conditions(), feed=make_default_feed(),
        simulation=SimulationConfig(duration_days=200, evaluation_points=21, backend="pyadm1", persist=False),
    )
    reference = default_results["pyadm1"]
    for name in ("ph", "vfa_total", "methane_m3_day", "alkalinity"):
        np.testing.assert_allclose(coarse.series[name], reference.series[name][::2], rtol=1e-3, atol=1e-6)  # PyADM1 restarts the integrator at each output time.
