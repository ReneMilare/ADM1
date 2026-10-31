from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from simulator.digital_twin.contracts import MEASUREMENT_COLUMNS, InfluentWindow
from simulator.digital_twin.demo import run_scenario, save_outputs
from simulator.digital_twin.inputs import observed_windows
from simulator.digital_twin.scenarios import COD_STATES, OrganicOverload, SyntheticScenario, influent_cod

NOMINAL = {"S_su": 1.0, "X_ch": 4.0, "S_IN": 0.1, "S_IC": 0.04}


def _windows(n: int) -> list[InfluentWindow]:
    return [
        InfluentWindow(t_start_days=d, t_end_days=d + 1, flow_m3_day=100.0, temperature_c=35.0, influent_values={"S_su": 9.0, "X_ch": 9.0, "S_IN": 0.5, "S_IC": 0.04})
        for d in range(n)
    ]


def _measured(n: int) -> pd.DataFrame:
    frame = pd.DataFrame({column: [np.nan] * n for column in MEASUREMENT_COLUMNS})
    frame["time_days"] = np.arange(n, dtype=float)
    frame["q_in_m3_d"] = 120.0
    frame.loc[3, "q_in_m3_d"] = np.nan
    frame["temperature_c"] = 33.0
    frame.loc[2, "cod_in_kg_m3"] = 10.0
    return frame


def test_observed_windows_hold_last_lab_cod_and_keep_nominal_composition() -> None:
    observed = observed_windows(_windows(5), _measured(5), NOMINAL)
    # Before the first COD sample the nominal load is used.
    assert influent_cod(observed[0].influent_values) == pytest.approx(5.0)
    # From the sample day on, COD is held and the nominal fractions are kept.
    for window in observed[2:]:
        assert influent_cod(window.influent_values) == pytest.approx(10.0)
        assert window.influent_values["S_su"] / window.influent_values["X_ch"] == pytest.approx(0.25)
    # Non-COD states are not rescaled and the true influent is never used.
    assert all(w.influent_values["S_IN"] == pytest.approx(0.1) for w in observed)
    # Missing flow sample falls back to the last online value.
    assert observed[3].flow_m3_day == pytest.approx(120.0)
    assert all(w.temperature_c == pytest.approx(33.0) for w in observed)
    assert set(COD_STATES) >= {"S_su", "X_ch"}


@pytest.mark.parametrize("mode", ["oracle", "observed"])
def test_shadow_run_produces_report_and_artifacts(tmp_path, mode: str) -> None:
    scenario = SyntheticScenario(
        duration_days=10.0,
        events=[OrganicOverload(t0_days=4.0, t1_days=6.0, factor=1.5)],
        hidden_parameter_overrides={"k_m_ac": 6.0},
        seed=7,
    )
    run = run_scenario("smoke", scenario, warmup_days=60.0, twin_influent=mode)
    report = run["report"]
    assert report["biogas_m3_d"]["n"] >= 10
    assert all(math.isfinite(stats["rmse"]) for stats in report.values() if stats["n"] > 0)
    assert run["final_twin_state"].time_days == pytest.approx(10.0)
    target = save_outputs(run, tmp_path)
    for name in ("measured.csv", "twin_open_loop.csv", "plant_truth.csv", "tracking_report.json", "twin_state_final.json", "shadow.png"):
        assert (target / name).exists()


def test_shadow_rejects_unknown_influent_mode() -> None:
    with pytest.raises(ValueError):
        run_scenario("bad", SyntheticScenario(duration_days=2.0), warmup_days=5.0, twin_influent="magic")
