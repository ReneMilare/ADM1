from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pytest

from simulator.core.defaults import make_default_kinetics
from simulator.core.pyadm1_backend import INITIAL_COLUMNS, _patched_pyadm1_source
from simulator.literature_validation import (
    build_reference_influent_frame,
    build_reference_initial_frame,
    build_reference_operating_conditions,
    build_reference_pyadm1_feed,
    build_reference_simulation_config,
)


@pytest.fixture(scope="module")
def runtime() -> dict:
    source = _patched_pyadm1_source(
        operating_conditions=build_reference_operating_conditions(),
        feed=build_reference_pyadm1_feed(),
        parameters=make_default_kinetics(),
        simulation=build_reference_simulation_config(backend="pyadm1"),
    )
    frames = {
        "digester_influent.csv": build_reference_influent_frame(np.asarray([0., 1.])),
        "digester_initial.csv": build_reference_initial_frame(),
    }
    namespace: dict = {}
    with patch("pandas.read_csv", side_effect=lambda filename: frames[filename].copy()):
        exec(compile(source.split("## time array definition")[0], "<PyADM1 runtime>", "exec"), namespace)
    return namespace


@pytest.mark.parametrize("value", [1e-300, -1., 1e6, 1e300])
def test_algebraic_guesses_do_not_change_solution(runtime: dict, value: float) -> None:
    state = np.asarray(runtime["state_zero"])
    expected = runtime["_solve_algebraic"](state)
    state[7] = value
    state[26:35] = value
    actual = runtime["_solve_algebraic"](state)
    np.testing.assert_array_equal(np.asarray(actual)[[7, *range(26, 35)]], np.asarray(expected)[[7, *range(26, 35)]])


@pytest.mark.parametrize("name", ["S_h2", "S_H_ion", "S_IC", "S_IN", "X_h2"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_rhs_allows_integrator_step_rejection(runtime: dict, name: str, value: float) -> None:
    state = np.asarray(runtime["state_zero"])
    state[INITIAL_COLUMNS.index(name)] = value
    assert not np.isfinite(runtime["ADM1_ODE"](0., state)).all()


def test_bracketed_newton_handles_flat_and_nonfinite_residuals() -> None:
    from simulator.core.algebraic import bracketed_newton

    # Newton from 0.9 on x**3 - 1e-6 overshoots badly; the bracket must hold it.
    root, _, ok = bracketed_newton(lambda x: (x**3 - 1e-6, 3 * x**2), 0.0, 1.0, 0.9, tolerance=1e-14, max_iterations=1000)
    assert ok and root == pytest.approx(1e-2, rel=1e-6)
    # Zero gradient and NaN gradient must fall back to bisection.
    root, _, ok = bracketed_newton(lambda x: (x - 0.3, float("nan")), 0.0, 1.0, 0.9, tolerance=1e-12, max_iterations=1000)
    assert ok and root == pytest.approx(0.3, abs=1e-11)
    # No sign change or non-finite bracket ends is reported, never silently accepted.
    assert not bracketed_newton(lambda x: (1.0 + x, 1.0), 0.0, 1.0, 0.5, tolerance=1e-12, max_iterations=100)[2]
    assert not bracketed_newton(lambda x: (float("nan"), 1.0), 0.0, 1.0, 0.5, tolerance=1e-12, max_iterations=100)[2]


def test_extreme_finite_states_give_physical_algebraic_values(runtime: dict) -> None:
    base = np.asarray(runtime["state_zero"], dtype=float)
    for name, factor in (("S_ac", 1e3), ("S_IC", 1e-6), ("S_IN", 1e4), ("X_h2", 1e6), ("S_va", 1e-9)):
        state = base.copy()
        state[INITIAL_COLUMNS.index(name)] *= factor
        solved = np.asarray(runtime["_solve_algebraic"](state))
        assert np.isfinite(solved).all(), name
        assert solved[INITIAL_COLUMNS.index("S_h2")] >= 0.0
        assert 1e-14 <= solved[INITIAL_COLUMNS.index("S_H_ion")] <= 1.0


def _full_inputs():
    from simulator.core.defaults import make_default_feed, make_default_initial_state, make_default_operating_conditions
    from simulator.full_model.adapter import build_backend_inputs

    feed = make_default_feed()
    return build_backend_inputs(
        operating_conditions=make_default_operating_conditions(),
        feed=feed,
        initial_state=make_default_initial_state(feed),
        parameters=make_default_kinetics(),
    )


def test_full_model_acid_base_nonfinite_state_does_not_loop_or_raise() -> None:
    from simulator.full_model.acid_base import solve_acid_base

    inputs = _full_inputs()
    state = dict(inputs.initial_values)
    state["S_IC"] = float("nan")
    result = solve_acid_base(state, inputs.parameter_values)
    assert result.converged is False
    assert result.iterations <= 1


@pytest.mark.parametrize("guess", [1e-14, 1e-3, 1.0])
def test_full_model_acid_base_root_independent_of_guess(guess: float) -> None:
    from simulator.full_model.acid_base import solve_acid_base

    inputs = _full_inputs()
    state = dict(inputs.initial_values)
    state["S_IN"] *= 1e3  # strong ammonium buffer: plain Newton from far guesses is fragile
    reference = solve_acid_base(state, inputs.parameter_values, initial_guess=1e-7)
    result = solve_acid_base(state, inputs.parameter_values, initial_guess=guess)
    assert reference.converged and result.converged
    assert result.s_h_ion == pytest.approx(reference.s_h_ion, rel=1e-6)


def _pyadm1_400_day():
    from simulator.bsm2_published import run_published_steady_state_case

    return run_published_steady_state_case("pyadm1", duration_days=400.0)


def test_pyadm1_400_days_bdf_tight_tolerances_matches_published_and_full() -> None:
    """Regression: BDF, rtol=1e-10, atol=1e-12, 401 points used to raise the H2 balance error."""
    from simulator.bsm2_published import RELATIVE_TOLERANCE, run_published_steady_state_case

    pyadm1 = _pyadm1_400_day()
    full = run_published_steady_state_case("full", duration_days=400.0)
    assert pyadm1["execution"]["solver"] == "BDF"
    assert pyadm1["execution"]["rtol"] == 1e-10 and pyadm1["execution"]["atol"] == 1e-12
    assert pyadm1["validated"], {k: v for k, v in pyadm1["comparison"].items() if not v["within_tolerance"]}
    assert max(row["rel_delta_pct"] for row in pyadm1["comparison"].values()) < RELATIVE_TOLERANCE * 100.0
    for name, row in pyadm1["comparison"].items():
        other = full["comparison"][name]["actual"]
        assert row["actual"] == pytest.approx(other, rel=RELATIVE_TOLERANCE, abs=1e-12), name


def test_pyadm1_400_days_201_points_reproduction_from_validation_report() -> None:
    """The exact VALIDATION_REPORT case: SciPy's Jacobian perturbation overflowed into NaN states."""
    from simulator.core.pyadm1_backend import simulate_with_pyadm1_frames

    simulation = build_reference_simulation_config(backend="pyadm1").model_copy(
        update={"duration_days": 400.0, "evaluation_points": 201},
    )
    result = simulate_with_pyadm1_frames(
        operating_conditions=build_reference_operating_conditions(),
        feed=build_reference_pyadm1_feed(),
        parameters=make_default_kinetics(),
        simulation=simulation,
        influent_frame=build_reference_influent_frame(np.linspace(0.0, 400.0, 201)),
        initial_frame=build_reference_initial_frame(),
    )
    final = dict(zip(result["metadata"]["pyadm1_state_columns"], result["metadata"]["final_internal_state"], strict=True))
    assert final["S_h2"] == pytest.approx(0.000000235945059, rel=1e-3)  # BSM2 published S_h2
