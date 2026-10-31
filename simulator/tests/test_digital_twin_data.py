from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from simulator.digital_twin import dataset, metrics
from simulator.digital_twin.contracts import MEASUREMENT_COLUMNS
from simulator.digital_twin.measurement import SensorSpec, default_sensor_suite, measure
from simulator.digital_twin.scenarios import (
    AmmoniaSpike,
    CompositionDrift,
    FlowStep,
    OrganicOverload,
    SyntheticScenario,
    TemperatureDrop,
    base_influent_values,
    build_windows,
    default_scenarios,
)

BASE = base_influent_values()
PARTICULATE = ("X_ch", "X_pr", "X_li")


def _scn(**kw) -> SyntheticScenario:
    kw.setdefault("duration_days", 30.0)
    kw.setdefault("load_noise_sigma", 0.0)
    return SyntheticScenario(**kw)


def _win(scn):
    return build_windows(scn, BASE)


def test_base_influent_has_no_q():
    assert "Q" not in BASE and "T (C)" not in BASE
    assert BASE["X_ch"] > 0


def test_windows_contiguous_and_deterministic():
    scn = _scn(duration_days=10.5, window_days=2.0, load_noise_sigma=0.1, seed=7)
    w1, w2 = _win(scn), _win(scn)
    assert w1[0].t_start_days == 0.0 and w1[-1].t_end_days == pytest.approx(10.5)
    for a, b in zip(w1, w1[1:]):
        assert a.t_end_days == b.t_start_days
    assert [w.influent_values for w in w1] == [w.influent_values for w in w2]
    w3 = _win(scn.model_copy(update={"seed": 8}))
    assert w3[0].influent_values["X_ch"] != w1[0].influent_values["X_ch"]


def test_noise_off_gives_base_values():
    w = _win(_scn())
    assert w[3].influent_values["X_ch"] == pytest.approx(BASE["X_ch"])


def test_weekly_pattern():
    w = _win(_scn(weekly_pattern=True, weekend_load_factor=0.5))
    assert w[5].influent_values["X_ch"] == pytest.approx(0.5 * BASE["X_ch"])
    assert w[2].influent_values["X_ch"] == pytest.approx(BASE["X_ch"])


def test_organic_overload_interval():
    w = _win(_scn(events=[OrganicOverload(t0_days=10, t1_days=15, factor=2.0)]))
    assert w[12].influent_values["X_pr"] == pytest.approx(2 * BASE["X_pr"])
    assert w[12].influent_values["S_su"] == pytest.approx(2 * BASE["S_su"])
    assert w[12].influent_values["S_ac"] == pytest.approx(BASE["S_ac"])
    assert w[9].influent_values["X_pr"] == pytest.approx(BASE["X_pr"])
    assert w[15].influent_values["X_pr"] == pytest.approx(BASE["X_pr"])


def test_temperature_drop_ramp():
    w = _win(_scn(events=[TemperatureDrop(t0_days=10, t1_days=20, delta_c=-8.0, ramp_days=4.0)]))
    assert w[5].temperature_c == pytest.approx(35.0)
    assert w[15].temperature_c == pytest.approx(27.0)
    assert 27.0 < w[11].temperature_c < 35.0
    assert w[27].temperature_c == pytest.approx(35.0)


def test_ammonia_spike_and_flow_step():
    w = _win(_scn(events=[AmmoniaSpike(t0_days=5, t1_days=8, factor=5.0), FlowStep(t0_days=20, t1_days=25, factor=1.5)]))
    assert w[6].influent_values["S_IN"] == pytest.approx(5 * BASE["S_IN"])
    assert w[9].influent_values["S_IN"] == pytest.approx(BASE["S_IN"])
    assert w[22].flow_m3_day == pytest.approx(1.5 * 150.0)
    assert w[10].flow_m3_day == pytest.approx(150.0)


def test_composition_drift_conserves_particulate_cod():
    w = _win(_scn(events=[CompositionDrift(t0_days=5, t1_days=25, max_shift_fraction=0.4)]))
    total0 = sum(BASE[k] for k in PARTICULATE)
    for win in w:
        assert sum(win.influent_values[k] for k in PARTICULATE) == pytest.approx(total0)
    assert w[0].influent_values["X_li"] == pytest.approx(BASE["X_li"])
    assert w[15].influent_values["X_li"] > BASE["X_li"]
    assert w[29].influent_values["X_li"] > w[15].influent_values["X_li"] - 1e-12


def test_default_scenarios_valid_and_nonnegative():
    scns = default_scenarios()
    assert set(scns) == {"steady_noisy", "overload_recovery", "cold_snap_ammonia"}
    for scn in scns.values():
        assert scn.duration_days == 120.0
        for win in build_windows(scn, BASE):
            assert all(v >= 0 for v in win.influent_values.values())
            assert win.flow_m3_day > 0
    w = build_windows(scns["overload_recovery"], BASE)
    assert w[45].influent_values["X_pr"] > 1.3 * w[20].influent_values["X_pr"]
    w = build_windows(scns["cold_snap_ammonia"], BASE)
    assert min(x.temperature_c for x in w) < 28.0


def test_event_discriminator_roundtrip():
    scn = _scn(events=[OrganicOverload(t0_days=1, t1_days=2, factor=2.0)])
    assert type(SyntheticScenario.model_validate(scn.model_dump()).events[0]) is OrganicOverload


# ---- measurement ----


def _signals(n_days=70, per_day=4):
    t = np.linspace(0, n_days, n_days * per_day, endpoint=False)
    ones = [1.0] * t.size
    outs = {
        "biogas_m3_d": [1000.0] * t.size,
        "ch4_fraction": [0.99] * t.size,
        "ph": [7.2] * t.size,
        "vfa_kg_cod_m3": [2.0] * t.size,
        "alkalinity_kmol_m3": [0.05] * t.size,
        "nh4_kg_n_m3": [1.0] * t.size,
    }
    ins = {"q_in_m3_d": [150.0] * t.size, "temperature_c": [35.0] * t.size, "cod_in_kg_m3": [50.0] * t.size}
    return list(t), outs, ins


def test_measure_shape_and_lab_sampling():
    t, outs, ins = _signals()
    df = measure(t, outs, ins, default_sensor_suite(), seed=1)
    assert list(df.columns) == list(MEASUREMENT_COLUMNS)
    assert len(df) == 70
    assert df["biogas_m3_d"].notna().all()
    lab = df["vfa_kg_cod_m3"]
    assert lab.notna().sum() == 10
    assert lab.notna().tolist() == [d % 7 == 0 for d in range(70)]


def test_measure_noise_statistics_and_determinism():
    t, outs, ins = _signals(n_days=2000, per_day=1)
    suite = [SensorSpec(column="biogas_m3_d", noise_rel=0.05)]
    df = measure(t, outs, ins, suite, seed=3)
    x = df["biogas_m3_d"].to_numpy()
    assert abs(x.mean() - 1000.0) < 5.0
    assert x.std() == pytest.approx(50.0, rel=0.08)
    assert df["ph"].isna().all()
    pd.testing.assert_frame_equal(df, measure(t, outs, ins, suite, seed=3))
    assert not df.equals(measure(t, outs, ins, suite, seed=4))


def test_measure_daily_mean_and_ph_absolute_noise():
    t = [0.0, 0.5, 1.0, 1.5]
    outs = {"ph": [7.0, 8.0, 6.0, 6.0]}
    df = measure(t, outs, {}, [SensorSpec(column="ph")], seed=0)
    assert df["ph"].tolist() == [7.5, 6.0]


def test_measure_clips_ch4_and_missing_and_drift():
    t, outs, ins = _signals(n_days=300, per_day=1)
    suite = [
        SensorSpec(column="ch4_fraction", noise_abs=0.2),
        SensorSpec(column="ph", missing_prob=0.5),
        SensorSpec(column="q_in_m3_d", drift_per_day=1.0),
    ]
    df = measure(t, outs, ins, suite, seed=2)
    assert df["ch4_fraction"].max() <= 1.0 and df["ch4_fraction"].min() >= 0.0
    assert (df["ch4_fraction"] == 1.0).any()
    assert 0.35 < df["ph"].isna().mean() < 0.65
    assert df["q_in_m3_d"].iloc[-1] == pytest.approx(150.0 + 299.0)


def test_sensor_spec_rejects_bad_column():
    with pytest.raises(ValueError):
        SensorSpec(column="time_days")


# ---- dataset ----


def test_dataset_roundtrip(tmp_path):
    t, outs, ins = _signals(n_days=20)
    df = measure(t, outs, ins, default_sensor_suite(), seed=1)
    p = tmp_path / "m.csv"
    dataset.write_measurements(df, p)
    back = dataset.read_measurements(p)
    pd.testing.assert_frame_equal(df, back)


def test_dataset_missing_columns_filled(tmp_path):
    p = tmp_path / "m.csv"
    pd.DataFrame({"time_days": [0, 1, 2], "ph": [7.0, 7.1, ""]}).to_csv(p, index=False)
    df = dataset.read_measurements(p)
    assert list(df.columns) == list(MEASUREMENT_COLUMNS)
    assert df["biogas_m3_d"].isna().all() and math.isnan(df["ph"].iloc[2])


def test_dataset_errors(tmp_path):
    with pytest.raises(FileNotFoundError):
        dataset.read_measurements(tmp_path / "nope.csv")
    p = tmp_path / "bad.csv"
    pd.DataFrame({"ph": [7.0]}).to_csv(p, index=False)
    with pytest.raises(ValueError, match="time_days"):
        dataset.read_measurements(p)
    pd.DataFrame({"time_days": [0, 1], "foo": [1, 2]}).to_csv(p, index=False)
    with pytest.raises(ValueError, match="unknown columns"):
        dataset.read_measurements(p)
    pd.DataFrame({"time_days": [0, 2, 1]}).to_csv(p, index=False)
    with pytest.raises(ValueError, match="increasing"):
        dataset.read_measurements(p)
    pd.DataFrame({"time_days": [0, 1], "ph": ["a", "b"]}).to_csv(p, index=False)
    with pytest.raises(ValueError, match="numeric"):
        dataset.read_measurements(p)


def test_to_daily_means_and_gaps():
    df = pd.DataFrame({"time_days": [0.0, 0.5, 3.0], "ph": [7.0, 8.0, 6.0]})
    d = dataset.to_daily(df)
    assert d["time_days"].tolist() == [0.0, 1.0, 2.0, 3.0]
    assert d["ph"].iloc[0] == 7.5 and d["ph"].iloc[3] == 6.0 and math.isnan(d["ph"].iloc[1])


# ---- metrics ----


def test_basic_metrics():
    y, yh = [1.0, 2.0, 4.0], [2.0, 2.0, 2.0]
    assert metrics.rmse(y, yh) == pytest.approx(math.sqrt((1 + 0 + 4) / 3))
    assert metrics.mae(y, yh) == pytest.approx(1.0)
    assert metrics.bias(y, yh) == pytest.approx(-1 / 3)
    assert metrics.mape(y, yh) == pytest.approx((100 + 0 + 50) / 3)


def test_metrics_ignore_nan_and_small_y():
    y, yh = [1.0, float("nan"), 3.0, 0.0], [2.0, 5.0, float("nan"), 1.0]
    assert metrics.rmse(y, yh) == pytest.approx(1.0)
    assert metrics.mape(y, yh) == pytest.approx(100.0)
    assert math.isnan(metrics.rmse([float("nan")], [1.0]))


def test_tracking_report_alignment():
    meas = pd.DataFrame({"time_days": [0.0, 1.0, 2.0], "ph": [7.0, float("nan"), 7.4], "biogas_m3_d": [10.0, 10.0, 10.0]})
    sim = pd.DataFrame({"time_days": [1.0, 2.0, 3.0], "ph": [7.0, 7.0, 7.0], "biogas_m3_d": [11.0, 12.0, 13.0]})
    rep = metrics.tracking_report(meas, sim, columns=["ph", "biogas_m3_d"])
    assert rep["ph"]["n"] == 1 and rep["ph"]["bias"] == pytest.approx(-0.4)
    assert rep["biogas_m3_d"]["rmse"] == pytest.approx(math.sqrt((1 + 4) / 2))
    assert set(rep["ph"]) == {"n", "rmse", "mae", "mape", "bias"}


def test_events_reject_empty_interval():
    from simulator.digital_twin.scenarios import CompositionDrift

    with pytest.raises(ValueError):
        CompositionDrift(t0_days=1.0, t1_days=1.0, max_shift_fraction=0.2)
