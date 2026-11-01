from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from simulator.digital_twin.demo import OUTPUT_COLUMNS, run_scenario, save_outputs
from simulator.digital_twin.engine import TwinEngine
from simulator.digital_twin.inputs import observed_windows
from simulator.digital_twin.metrics import tracking_report
from simulator.digital_twin.estimator import SigmaPointConfig, TwinUKF, UKFConfig, UnscentedKalmanFilter, moments, sigma_points
from simulator.digital_twin.identifiability import InformationConfig, local_information, nitrogen_window
from simulator.digital_twin.scenarios import OrganicOverload, base_influent_values, build_windows, default_scenarios


def test_sigma_points_recover_mean_covariance() -> None:
    mean = np.array([1.0, -2.0, 0.5])
    covariance = np.array([[2.0, 0.4, 0.1], [0.4, 1.0, -0.1], [0.1, -0.1, 0.3]])
    for alpha in (0.3, 1.0):
        points, wm, wc = sigma_points(mean, covariance, SigmaPointConfig(alpha=alpha))
        recovered_mean, recovered_covariance = moments(points, wm, wc)
        assert wm.sum() == pytest.approx(1.0)
        np.testing.assert_allclose(recovered_mean, mean, atol=1e-14)
        np.testing.assert_allclose(recovered_covariance, covariance, atol=1e-14)
        assert points.shape == (7, 3)


def test_linear_ukf_matches_exact_kalman_with_process_noise() -> None:
    a = np.array([[1.0, 0.3], [0.0, 1.0]])
    h = np.array([[1.0, -0.2]])
    q = np.array([[0.1, 0.02], [0.02, 0.2]])
    r = np.array([[0.15]])
    mean, covariance = np.array([0.2, -0.1]), np.array([[0.7, 0.1], [0.1, 0.4]])
    ukf = UnscentedKalmanFilter(mean, covariance, SigmaPointConfig(alpha=0.7))
    for value in (0.4, 0.7, -0.1, 0.3):
        mean, covariance = a @ mean, a @ covariance @ a.T + q
        gain = covariance @ h.T @ np.linalg.inv(h @ covariance @ h.T + r)
        mean = mean + gain[:, 0] * (value - (h @ mean)[0])
        covariance = covariance - gain @ h @ covariance
        ukf.predict(lambda x: a @ x, q)
        ukf.update(np.array([value]), lambda x: h @ x, r)
        np.testing.assert_allclose(ukf.mean, mean, atol=1e-12)
        np.testing.assert_allclose(ukf.covariance, covariance, atol=1e-12)


def test_filter_config_strict_and_assignment_validated() -> None:
    with pytest.raises(ValidationError):
        UKFConfig(unknown=1)
    with pytest.raises(ValidationError):
        UKFConfig(process_log_std=(0.01,))
    with pytest.raises(ValidationError):
        UKFConfig(process_log_std=(-1, 0, 0, 0, 0))
    cfg = UKFConfig()
    with pytest.raises(ValidationError):
        cfg.initial_k_m_ac = 0


@pytest.mark.parametrize("factor", [0.1, 0.98, 1.0, 4.0])
def test_nitrogen_input_multiplier_preserves_ammonium_salt_charge(factor) -> None:
    window = build_windows(default_scenarios()["steady_noisy"])[0]
    changed = nitrogen_window(window, factor)
    extra = changed.influent_values["S_IN"] - window.influent_values["S_IN"]
    strong_charge_before = window.influent_values["S_cation"] - window.influent_values["S_anion"]
    strong_charge_after = changed.influent_values["S_cation"] - changed.influent_values["S_anion"]
    assert strong_charge_after - strong_charge_before == pytest.approx(-extra)
    assert min(changed.influent_values.values()) >= 0
    assert changed.influent_values["S_IN"] == pytest.approx(factor * window.influent_values["S_IN"])
    assert changed.influent_values["X_ch"] == window.influent_values["X_ch"]
    with pytest.raises(ValueError):
        nitrogen_window(window, 0)


def test_causality_missing_lab_and_positive_states() -> None:
    scenario = default_scenarios()["steady_noisy"].model_copy(update={"duration_days": 2.0})
    windows = build_windows(scenario)
    engine = TwinEngine(scenario.volume_m3)
    state = engine.initial_state(windows[0], warmup_days=30)
    one = TwinUKF(engine, state)
    two = TwinUKF(engine, state)
    frame = pd.DataFrame({"time_days": [0.0, 1.0], "ph": [7.0, 7.2], "nh4_kg_n_m3": [np.nan, 2.0]})
    future_changed = frame.copy()
    future_changed.loc[1, ["ph", "nh4_kg_n_m3"]] = [14, 100]
    prediction = one.advance(windows[0], frame)
    two.advance(windows[0], future_changed)
    np.testing.assert_array_equal(one.mean, two.mean)
    assert one.assimilations == [{"sample_day": 0.0, "available_at": 1.0, "columns": ["ph"]}]
    assert all(v >= 0 for v in one.state.dynamic_state.values())
    assert all(v > 0 for v in one._decode(np.full(7, -1000.0))[0].dynamic_state.values() if v != 0)
    assert one.state.parameter_overrides["k_m_ac"] > 0
    assert prediction["time_days"] == 0
    one.advance(windows[1], frame.drop(columns="nh4_kg_n_m3"))
    assert one.assimilations[-1]["columns"] == ["ph"]
    assert one.assimilations[-1]["available_at"] == 2.0
    three = TwinUKF(engine, state)
    changed = frame.copy()
    changed.loc[0, "ph"] = 7.5
    assert three.advance(windows[0], changed) == pytest.approx(prediction)
    with pytest.raises(ValueError, match="one-day"):
        three.advance(windows[1].model_copy(update={"t_end_days": 3.0}), frame)


def test_local_information_only_uses_available_sensor_samples() -> None:
    scenario = default_scenarios()["steady_noisy"].model_copy(update={"duration_days": 2.0})
    windows = build_windows(scenario)
    engine = TwinEngine(scenario.volume_m3)
    state = engine.initial_state(windows[0], warmup_days=30)
    measured = pd.DataFrame({"time_days": [0.0, 1.0], "biogas_m3_d": [100.0, 100.0], "nh4_kg_n_m3": [2.0, np.nan]})
    info = local_information(engine, state, windows, measured, config=InformationConfig())
    assert info["samples"] == 3
    assert info["rank"] == 2
    assert np.linalg.eigvalsh(info["fisher"]).min() > 0
    assert np.all(np.isfinite(info["conditional_log_std"]))
    empty = measured.copy()
    empty[["biogas_m3_d", "nh4_kg_n_m3"]] = np.nan
    missing = local_information(engine, state, windows, empty)
    assert missing["rank"] == 0
    assert missing["samples"] == 0
    assert missing["conditional_log_std"] is None
    assert missing["correlation"] is None


@pytest.fixture(scope="module")
def short_runs():
    runs = {}
    for name, original in default_scenarios().items():
        events = []
        if name == "overload_recovery":
            events = [OrganicOverload(t0_days=8, t1_days=12, factor=1.8)]
        elif name == "cold_snap_ammonia":
            events = list(original.events)
        if name == "cold_snap_ammonia":
            run = run_scenario(name, original, warmup_days=200)
            windows = observed_windows(
                build_windows(original), run["measured"], base_influent_values(),
                nominal_flow_m3_day=original.base_flow_m3_day,
                nominal_temperature_c=original.base_temperature_c,
            )[:84]
            engine = TwinEngine(original.volume_m3)
            ukf = TwinUKF(engine, engine.initial_state(windows[0], warmup_days=200))
            estimated = ukf.run(windows, run["measured"])
            baseline = run["simulated"][run["simulated"].time_days < 84]
            columns = list(OUTPUT_COLUMNS)
            run.update({
                "open_loop_report": tracking_report(run["measured"], baseline, columns),
                "open_loop_truth_report": tracking_report(run["truth"], baseline, columns),
                "report": tracking_report(run["measured"], estimated, columns),
                "truth_report": tracking_report(run["truth"], estimated, columns),
                "simulated": estimated,
                "parameter_history": pd.DataFrame(ukf.history),
                "final_twin_state": ukf.state,
            })
            runs[name] = run
        else:
            scenario = original.model_copy(update={"duration_days": 21.0, "events": events})
            runs[name] = run_scenario(name, scenario, estimator="ukf", warmup_days=200)
    return runs


@pytest.mark.parametrize("name", list(default_scenarios()))
def test_ukf_improves_gas_forecast_on_three_scenarios(short_runs, name) -> None:
    run = short_runs[name]
    assert run["report"]["biogas_m3_d"]["mape"] < run["open_loop_report"]["biogas_m3_d"]["mape"]
    assert run["truth_report"]["biogas_m3_d"]["mape"] < run["open_loop_truth_report"]["biogas_m3_d"]["mape"]
    history = run["parameter_history"]
    assert np.isfinite(history.to_numpy()).all()
    assert (history.drop(columns="time_days") > 0).all().all()
    duration = 84 if name == "cold_snap_ammonia" else 21
    assert len(run["simulated"]) == duration
    assert run["report"]["nh4_kg_n_m3"]["n"] == duration // 7
    assert all(run["final_twin_state"].dynamic_state[n] > 0 for n in UKFConfig().state_names)


def test_k_m_ac_convergence_and_artifacts(short_runs, tmp_path) -> None:
    run = short_runs["steady_noisy"]
    final = run["parameter_history"].iloc[-1]
    assert final.k_m_ac == pytest.approx(5.5, abs=1.0)
    target = save_outputs(run, tmp_path)
    for name in ("twin_ukf_forecast.csv", "estimated_parameters.csv", "comparison.json", "shadow.png", "twin_state_final.json"):
        assert (target / name).exists()
    saved = pd.read_csv(target / "estimated_parameters.csv")
    assert len(saved) == 21
    assert saved.k_m_ac.iloc[-1] == pytest.approx(final.k_m_ac)
    assert set(OUTPUT_COLUMNS).issubset(pd.read_csv(target / "twin_ukf_forecast.csv"))


def test_ukf_demo_rejects_invalid_estimator() -> None:
    scenario = default_scenarios()["steady_noisy"].model_copy(update={"duration_days": 1.0})
    with pytest.raises(ValueError, match="estimator"):
        run_scenario("invalid", scenario, estimator="magic")
