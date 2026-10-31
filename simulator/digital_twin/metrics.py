"""Tracking-error metrics between measured and simulated series (NaN-safe)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from simulator.digital_twin.contracts import MEASUREMENT_COLUMNS


def _pair(y_true, y_pred) -> tuple[np.ndarray, np.ndarray]:
    a = np.asarray(y_true, dtype=float)
    b = np.asarray(y_pred, dtype=float)
    if a.shape != b.shape:
        raise ValueError(f"shape mismatch: {a.shape} vs {b.shape}")
    ok = ~(np.isnan(a) | np.isnan(b))
    return a[ok], b[ok]


def rmse(y_true, y_pred) -> float:
    a, b = _pair(y_true, y_pred)
    return float(np.sqrt(np.mean((b - a) ** 2))) if a.size else float("nan")


def mae(y_true, y_pred) -> float:
    a, b = _pair(y_true, y_pred)
    return float(np.mean(np.abs(b - a))) if a.size else float("nan")


def mape(y_true, y_pred, eps: float = 1e-9) -> float:
    """Mean absolute percentage error [%], ignoring pairs with |y_true| < eps."""
    a, b = _pair(y_true, y_pred)
    keep = np.abs(a) >= eps
    if not keep.any():
        return float("nan")
    return float(np.mean(np.abs((b[keep] - a[keep]) / a[keep])) * 100.0)


def bias(y_true, y_pred) -> float:
    """Mean of (simulated - measured)."""
    a, b = _pair(y_true, y_pred)
    return float(np.mean(b - a)) if a.size else float("nan")


def tracking_report(
    measured: pd.DataFrame,
    simulated: pd.DataFrame,
    columns: list[str] | None = None,
) -> dict[str, dict[str, float]]:
    """Per-column metrics after aligning both tables on day = floor(time_days)."""
    cols = columns or [c for c in MEASUREMENT_COLUMNS if c != "time_days" and c in measured.columns and c in simulated.columns]
    m = measured.assign(_day=np.floor(measured["time_days"]).astype(int)).groupby("_day").mean(numeric_only=True)
    s = simulated.assign(_day=np.floor(simulated["time_days"]).astype(int)).groupby("_day").mean(numeric_only=True)
    days = m.index.intersection(s.index)
    report: dict[str, dict[str, float]] = {}
    for col in cols:
        if col not in m.columns or col not in s.columns:
            raise ValueError(f"column {col!r} missing from measured or simulated table")
        y, yh = m.loc[days, col].to_numpy(), s.loc[days, col].to_numpy()
        n = int((~(np.isnan(y) | np.isnan(yh))).sum())
        report[col] = {"n": float(n), "rmse": rmse(y, yh), "mae": mae(y, yh), "mape": mape(y, yh), "bias": bias(y, yh)}
    return report
