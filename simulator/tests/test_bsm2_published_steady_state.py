from __future__ import annotations

import pytest

from simulator.bsm2_published import (
    DERIVED_OUTPUTS,
    PUBLISHED_OUTPUTS,
    compare_published_outputs,
    run_published_steady_state_case,
)
from simulator.full_parity import _compare_internal_states, _compare_series, _compare_summary
from simulator.literature_validation import REFERENCE_OUTPUTS


@pytest.fixture(scope="module")
def published_runs() -> dict:
    return {
        (backend, days): run_published_steady_state_case(backend, duration_days=days)
        for backend, days in (("full", 200.0), ("pyadm1", 200.0), ("full", 400.0))
    }


@pytest.mark.parametrize(("backend", "days"), [("full", 200.0), ("pyadm1", 200.0), ("full", 400.0)])
def test_all_published_states_within_point_one_percent(published_runs: dict, backend: str, days: float) -> None:
    run = published_runs[backend, days]
    assert len(run["comparison"]) == 47
    failures = {name: row for name, row in run["comparison"].items() if not row["within_tolerance"]}
    assert not failures, failures
    assert run["validated"]
    assert run["execution"]["evaluation_points"] == int(days) + 1


@pytest.mark.parametrize("backend", ["full", "pyadm1"])
def test_200_day_outputs_are_close_to_extended_full_steady_state(published_runs: dict, backend: str) -> None:
    first = published_runs[backend, 200.0]["comparison"]
    last = published_runs["full", 400.0]["comparison"]
    for name, row in last.items():
        assert row["actual"] == pytest.approx(first[name]["actual"], rel=0.001, abs=1e-14), name


def test_published_fixture_preserves_existing_reference_values() -> None:
    for name, reference in REFERENCE_OUTPUTS.items():
        assert PUBLISHED_OUTPUTS[name] == reference["value"], name
    assert "Qch4_Nm3_day" not in PUBLISHED_OUTPUTS
    assert DERIVED_OUTPUTS["Qch4_Nm3_day"] == pytest.approx(1799.32828531, abs=1e-8)


@pytest.mark.parametrize("name", ["S_ac", "S_IC", "S_IN", "S_h2", "S_H_ion", "S_gas_h2", "Qgas_Nm3_day"])
def test_published_gate_rejects_small_relative_regressions(name: str) -> None:
    actual = PUBLISHED_OUTPUTS | DERIVED_OUTPUTS
    actual[name] *= 1.002
    assert not compare_published_outputs(actual)[name]["within_tolerance"]


@pytest.mark.parametrize("baseline", [True, False])
def test_parity_gates_reject_one_percent_drift(baseline: bool) -> None:
    reference = {name: 1.0 for name in PUBLISHED_OUTPUTS | DERIVED_OUTPUTS}
    actual = {name: value * 1.01 for name, value in reference.items()}
    assert all(not row["within_tolerance"] for row in _compare_internal_states(actual, reference, baseline=baseline).values())
    summary_names = (
        "methane_final_m3_day", "biogas_final_m3_day", "ph_final", "vfa_final",
        "effluent_cod_final", "methane_cumulative_m3", "ch4_fraction_final",
    )
    reference_summary = dict.fromkeys(summary_names, 1.0)
    actual_summary = dict.fromkeys(summary_names, 1.01)
    assert all(not row["within_tolerance"] for row in _compare_summary(actual_summary, reference_summary, baseline=baseline).values())
    reference_series = {name: [1.0, 1.0] for name in ("methane_m3_day", "biogas_m3_day", "ph", "vfa_total", "effluent_cod")}
    actual_series = {name: [1.01, 1.01] for name in reference_series}
    assert all(not row["within_tolerance"] for row in _compare_series(actual_series, reference_series, baseline=baseline).values())


@pytest.mark.parametrize("name", ["S_h2", "S_gas_h2"])
def test_parity_absolute_floor_does_not_hide_hydrogen_drift(name: str) -> None:
    actual = dict(PUBLISHED_OUTPUTS)
    actual[name] *= 1.002
    assert not _compare_internal_states(actual, PUBLISHED_OUTPUTS, baseline=True)[name]["within_tolerance"]
