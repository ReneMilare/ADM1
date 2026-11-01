"""Positive reduced-state augmented UKF propagated by the native full ADM1.

The uncertain coordinates are log concentrations, log(k_m_ac) and log of a
charge-balanced ammonium influent multiplier. Other ADM1 states follow the
sigma-weighted mean;
there is no covariance retained for those states. This is a reduced covariance
approximation, not a reduced biochemical model. See UKF.md for assumptions.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import numpy as np
import pandas as pd
from pydantic import ConfigDict, Field, model_validator

from simulator.core.models import StrictModel
from simulator.digital_twin.contracts import InfluentWindow, TwinState
from simulator.digital_twin.engine import TwinEngine
from simulator.digital_twin.identifiability import OUTPUT_COLUMNS, nitrogen_window, window_observation
from simulator.digital_twin.measurement import SensorSpec, default_sensor_suite


class SigmaPointConfig(StrictModel):
    model_config = ConfigDict(allow_inf_nan=False)

    alpha: float = Field(default=1.0, gt=0.0, le=1.0)
    beta: float = Field(default=2.0, ge=0.0)
    kappa: float = Field(default=0.0, ge=0.0)


def sigma_points(mean: np.ndarray, covariance: np.ndarray, config: SigmaPointConfig | None = None) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Scaled UT, Julier & Uhlmann (2004), doi:10.1109/JPROC.2003.823141."""
    cfg = config or SigmaPointConfig()
    mean = np.asarray(mean, dtype=float)
    covariance = np.asarray(covariance, dtype=float)
    n = mean.size
    if mean.ndim != 1 or n == 0 or covariance.shape != (n, n):
        raise ValueError("mean and covariance dimensions must agree")
    scale = cfg.alpha**2 * (n + cfg.kappa)
    root = np.linalg.cholesky(scale * covariance)
    points = np.vstack([mean, mean + root.T, mean - root.T])
    wm = np.full(2 * n + 1, 0.5 / scale)
    wm[0] = 1 - n / scale
    wc = wm.copy()
    wc[0] += 1 - cfg.alpha**2 + cfg.beta
    return points, wm, wc


def moments(points: np.ndarray, wm: np.ndarray, wc: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    mean = wm @ points
    delta = points - mean
    return mean, (delta.T * wc) @ delta


def _positive_covariance(covariance: np.ndarray) -> np.ndarray:
    # Roundoff repair after covariance subtraction (Julier & Uhlmann 2004).
    symmetric = (covariance + covariance.T) / 2
    values, vectors = np.linalg.eigh(symmetric)
    return (vectors * np.maximum(values, 1e-12)) @ vectors.T


def _condition(mean: np.ndarray, covariance: np.ndarray, x: np.ndarray, y: np.ndarray,
               observed: np.ndarray, noise: np.ndarray, wm: np.ndarray, wc: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    y_mean, y_cov = moments(y, wm, wc)
    cross = ((x - mean).T * wc) @ (y - y_mean)
    innovation_cov = y_cov + noise
    gain = np.linalg.solve(innovation_cov, cross.T).T
    return mean + gain @ (observed - y_mean), _positive_covariance(covariance - gain @ innovation_cov @ gain.T)


class UnscentedKalmanFilter:
    """Additive-noise UKF; re-sigma after Q so measurement includes process noise."""

    def __init__(self, mean: np.ndarray, covariance: np.ndarray, config: SigmaPointConfig | None = None) -> None:
        self.mean = np.asarray(mean, dtype=float).copy()
        self.covariance = np.asarray(covariance, dtype=float).copy()
        self.config = config or SigmaPointConfig()
        sigma_points(self.mean, self.covariance, self.config)

    def predict(self, transition: Callable[[np.ndarray], np.ndarray], process_noise: np.ndarray) -> None:
        points, wm, wc = sigma_points(self.mean, self.covariance, self.config)
        self.mean, covariance = moments(np.asarray([transition(p) for p in points]), wm, wc)
        self.covariance = _positive_covariance(covariance + process_noise)

    def update(self, observed: np.ndarray, observation: Callable[[np.ndarray], np.ndarray], measurement_noise: np.ndarray) -> None:
        points, wm, wc = sigma_points(self.mean, self.covariance, self.config)
        y = np.asarray([observation(p) for p in points])
        self.mean, self.covariance = _condition(self.mean, self.covariance, points, y,
                                               np.asarray(observed), measurement_noise, wm, wc)


class UKFConfig(StrictModel):
    model_config = ConfigDict(allow_inf_nan=False)

    sigma: SigmaPointConfig = Field(default_factory=SigmaPointConfig)
    state_names: tuple[str, ...] = ("S_ac", "X_ac", "S_IN", "S_IC", "S_anion")
    initial_log_std: tuple[float, ...] = (0.6, 0.15, 0.1, 0.1, 0.1)
    process_log_std: tuple[float, ...] = (0.15, 0.02, 0.005, 0.01, 0.02)
    initial_k_m_ac: float = Field(default=8.0, gt=0.0)
    initial_nitrogen_factor: float = Field(default=1.0, gt=0.0)
    k_m_ac_log_std: float = Field(default=0.3, gt=0.0)
    nitrogen_log_std: float = Field(default=0.4, gt=0.0)
    k_m_ac_process_log_std: float = Field(default=0.005, ge=0.0)
    nitrogen_process_log_std: float = Field(default=0.12, ge=0.0)

    @model_validator(mode="after")
    def check_scales(self) -> UKFConfig:
        n = len(self.state_names)
        if not n or len(set(self.state_names)) != n or len(self.initial_log_std) != n or len(self.process_log_std) != n:
            raise ValueError("state names must be unique with one initial/process std per state")
        if any(not np.isfinite(s) or s <= 0 for s in self.initial_log_std):
            raise ValueError("initial log std must be finite and positive")
        if any(not np.isfinite(s) or s < 0 for s in self.process_log_std):
            raise ValueError("process log std must be finite and nonnegative")
        if self.sigma.alpha != 1.0:
            raise ValueError("ADM1 requires alpha=1 for nonnegative mean weights on unfiltered states")
        return self


class TwinUKF:
    """One-day causal filter. Assimilate day d only at its completion d+1.

    Process noise is a log random walk applied at each window START before
    deterministic propagation. This permits consistent joint moments between
    end states and the DAILY MEAN observation, unlike an endpoint observation.
    Weekly NaNs are skipped, never held or interpolated. Outputs returned by
    advance are forecasts, before assimilating that day's observations.
    """

    def __init__(self, engine: TwinEngine, state: TwinState, config: UKFConfig | None = None,
                 sensors: Sequence[SensorSpec] | None = None) -> None:
        from simulator.core.defaults import make_default_ukf_config

        self.engine = engine
        self.config = config if config is not None else make_default_ukf_config()
        self.state = state.model_copy(deep=True)
        cfg = self.config
        if not set(cfg.state_names).issubset(state.dynamic_state):
            raise ValueError("filtered state names must be dynamic states of the engine")
        values = [state.dynamic_state[n] for n in cfg.state_names] + [cfg.initial_k_m_ac, cfg.initial_nitrogen_factor]
        if min(values) <= 0:
            raise ValueError("initial filtered concentrations must be positive")
        self.mean = np.log(values)
        self.covariance = np.diag(np.square([*cfg.initial_log_std, cfg.k_m_ac_log_std, cfg.nitrogen_log_std]))
        self.sensors = {s.column: s for s in (sensors if sensors is not None else default_sensor_suite())}
        self.history: list[dict[str, float]] = []
        self.assimilations: list[dict[str, object]] = []

    def _decode(self, point: np.ndarray) -> tuple[TwinState, float]:
        values = np.exp(np.clip(point, -30, 20))
        state = self.state.model_copy(deep=True)
        state.dynamic_state.update(zip(self.config.state_names, values[:-2], strict=True))
        state.parameter_overrides["k_m_ac"] = float(values[-2])
        return state, float(values[-1])

    def advance(self, window: InfluentWindow, measured: pd.DataFrame) -> dict[str, float]:
        if not np.isclose(window.t_start_days, round(window.t_start_days)) or not np.isclose(window.t_end_days - window.t_start_days, 1.0):
            raise ValueError("UKF requires aligned one-day windows for daily mean sensors")
        cfg = self.config
        process_std = np.array([*cfg.process_log_std, cfg.k_m_ac_process_log_std, cfg.nitrogen_process_log_std])
        points, wm, wc = sigma_points(self.mean, self.covariance + np.diag(process_std**2), cfg.sigma)
        propagated, observations, results = [], [], []
        for point in points:
            state, factor = self._decode(point)
            result = self.engine.advance(state, nitrogen_window(window, factor))
            propagated.append([np.log(max(result.state.dynamic_state[n], 1e-13)) for n in cfg.state_names] + list(point[-2:]))
            observations.append(window_observation(result))
            results.append(result)
        x, y = np.array(propagated), np.array(observations)
        mean, covariance = moments(x, wm, wc)
        prediction = dict(zip(OUTPUT_COLUMNS, wm @ y, strict=True))
        prediction["time_days"] = window.t_start_days
        rows = measured.loc[np.isclose(measured["time_days"], window.t_start_days)]
        if len(rows) > 1:
            raise ValueError("measurement day must be unique")
        columns, indices, observed, variance = [], [], [], []
        if len(rows):
            row = rows.iloc[0]
            for j, column in enumerate(OUTPUT_COLUMNS):
                if column in self.sensors and column in row and np.isfinite(row[column]):
                    spec = self.sensors[column]
                    std = spec.noise_abs + spec.noise_rel * abs(prediction[column])
                    columns.append(column)
                    indices.append(j)
                    observed.append(row[column])
                    variance.append(max(std**2, 1e-12))
        if indices:
            mean, covariance = _condition(mean, covariance, x, y[:, indices], np.array(observed), np.diag(variance), wm, wc)
            self.assimilations.append({"sample_day": window.t_start_days, "available_at": window.t_end_days, "columns": columns})
        self.mean, self.covariance = mean, _positive_covariance(covariance)
        names = list(self.state.dynamic_state)
        average = wm @ np.array([[r.state.dynamic_state[n] for n in names] for r in results])
        self.state = results[0].state.model_copy(deep=True)
        self.state.dynamic_state = dict(zip(names, np.maximum(average, 0.0), strict=True))
        self.state, _ = self._decode(self.mean)
        self.history.append(self.parameter_summary())
        return prediction

    def parameter_summary(self) -> dict[str, float]:
        summary = {"time_days": self.state.time_days}
        for index, name in ((-2, "k_m_ac"), (-1, "nitrogen_factor")):
            mu, var = self.mean[index], self.covariance[index, index]
            median = float(np.exp(mu))
            std_log = float(np.sqrt(var))
            summary[name] = median
            summary[name + "_sigma"] = float(np.sqrt(np.expm1(var) * np.exp(2 * mu + var)))
            summary[name + "_lower_2sigma"] = float(np.exp(mu - 2 * std_log))
            summary[name + "_upper_2sigma"] = float(np.exp(mu + 2 * std_log))
        return summary

    def run(self, windows: Sequence[InfluentWindow], measured: pd.DataFrame) -> pd.DataFrame:
        return pd.DataFrame([self.advance(w, measured) for w in windows])
