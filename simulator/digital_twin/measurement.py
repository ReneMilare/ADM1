"""Sensor model: adds noise in the physical units/bases defined by contracts.py.

Gas noise applies to dry Nm3/d and dry CH4 fraction; laboratory noise applies
to species-sum total alkalinity and NH4+-N, after full-model speciation.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from pydantic import Field, field_validator

from simulator.core.models import StrictModel
from simulator.digital_twin.contracts import MEASUREMENT_COLUMNS

DATA_COLUMNS: tuple[str, ...] = tuple(c for c in MEASUREMENT_COLUMNS if c != "time_days")


class SensorSpec(StrictModel):
    column: str
    noise_rel: float = Field(default=0.0, ge=0.0, description="Relative noise std (fraction of value).")
    noise_abs: float = Field(default=0.0, ge=0.0, description="Absolute noise std (column units).")
    sampling_every_days: int = Field(default=1, ge=1)
    drift_per_day: float = 0.0
    outlier_prob: float = Field(default=0.0, ge=0.0, le=1.0)
    outlier_scale: float = Field(default=5.0, gt=0.0, description="Outlier noise std = outlier_scale * normal std.")
    missing_prob: float = Field(default=0.0, ge=0.0, le=1.0)

    @field_validator("column")
    @classmethod
    def check_column(cls, v: str) -> str:
        if v not in DATA_COLUMNS:
            raise ValueError(f"column must be one of {DATA_COLUMNS}, got {v!r}")
        return v


def default_sensor_suite() -> list[SensorSpec]:
    return [
        SensorSpec(column="biogas_m3_d", noise_rel=0.03),
        SensorSpec(column="ch4_fraction", noise_abs=0.01),
        SensorSpec(column="ph", noise_abs=0.03),
        SensorSpec(column="vfa_kg_cod_m3", noise_rel=0.08, noise_abs=0.02, sampling_every_days=7),
        SensorSpec(column="alkalinity_kmol_m3", noise_rel=0.05, sampling_every_days=7),
        SensorSpec(column="nh4_kg_n_m3", noise_rel=0.06, sampling_every_days=7),
        SensorSpec(column="cod_in_kg_m3", noise_rel=0.06, sampling_every_days=7),
        SensorSpec(column="q_in_m3_d", noise_rel=0.01),
        SensorSpec(column="temperature_c", noise_abs=0.2),
    ]


def _daily_mean(time_days: np.ndarray, values: list[float], days: np.ndarray) -> np.ndarray:
    series = pd.Series(np.asarray(values, dtype=float))
    return series.groupby(np.floor(time_days).astype(int)).mean().reindex(days).to_numpy(dtype=float)


def measure(
    time_days: list[float],
    true_outputs: dict[str, list[float]],
    inputs: dict[str, list[float]],
    suite: list[SensorSpec],
    seed: int,
) -> pd.DataFrame:
    """Daily-mean the signals, then apply sensor noise/drift/outliers/gaps.

    ``true_outputs`` and ``inputs`` are keyed by MEASUREMENT_COLUMNS names and
    share the length of ``time_days``. Row label ``time_days`` is the integer
    day start; sample ``d`` is the mean over ``[d, d+1)``. Columns without a
    sensor, or without a source signal, stay NaN.
    """
    t = np.asarray(time_days, dtype=float)
    if t.size == 0:
        return pd.DataFrame(columns=list(MEASUREMENT_COLUMNS), dtype=float)
    days = np.arange(int(np.floor(t.min())), int(np.floor(t.max())) + 1)
    out = pd.DataFrame({"time_days": days.astype(float)})
    for col in DATA_COLUMNS:
        out[col] = np.nan
    source = {**inputs, **true_outputs}
    specs = {s.column: s for s in suite}
    for idx, col in enumerate(DATA_COLUMNS):
        spec = specs.get(col)
        if spec is None or col not in source:
            continue
        if len(source[col]) != t.size:
            raise ValueError(f"signal {col!r} has {len(source[col])} points, expected {t.size}")
        rng = np.random.default_rng([int(seed), idx])
        value = _daily_mean(t, source[col], days)
        sigma = spec.noise_rel * np.abs(value) + spec.noise_abs
        is_outlier = rng.random(days.size) < spec.outlier_prob
        sigma = np.where(is_outlier, sigma * spec.outlier_scale, sigma)
        noisy = value + spec.drift_per_day * (days - days[0]) + sigma * rng.standard_normal(days.size)
        sampled = ((days - days[0]) % spec.sampling_every_days == 0) & (rng.random(days.size) >= spec.missing_prob)
        noisy = np.where(sampled, noisy, np.nan)
        noisy = np.maximum(noisy, 0.0)
        if col == "ch4_fraction":
            noisy = np.clip(noisy, 0.0, 1.0)
        out[col] = noisy
    return out[list(MEASUREMENT_COLUMNS)]
