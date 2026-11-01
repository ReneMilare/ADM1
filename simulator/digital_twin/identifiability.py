"""Local, sensor-weighted information for log(k_m_ac) and log(influent N factor)."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd
from pydantic import ConfigDict, Field

from simulator.core.models import StrictModel
from simulator.digital_twin.contracts import InfluentWindow, TwinState, WindowResult
from simulator.digital_twin.engine import TwinEngine
from simulator.digital_twin.measurement import SensorSpec, default_sensor_suite

OUTPUT_COLUMNS = ("biogas_m3_d", "ch4_fraction", "ph", "vfa_kg_cod_m3", "alkalinity_kmol_m3", "nh4_kg_n_m3")


class InformationConfig(StrictModel):
    model_config = ConfigDict(allow_inf_nan=False)

    log_step: float = Field(default=0.02, gt=0.0, le=0.2)
    k_m_ac: float = Field(default=8.0, gt=0.0)
    nitrogen_factor: float = Field(default=1.0, gt=0.0)


def nitrogen_window(window: InfluentWindow, factor: float) -> InfluentWindow:
    """Unknown ammonium N with strong-ion charge compensation.

    Increases match AmmoniaSpike(counter_ion='chloride'). Depletion removes
    anion first, then exchanges NH4+ for strong cation if anions run out.
    Free NH3 ingress needs a different input model.
    """
    if not np.isfinite(factor) or factor <= 0:
        raise ValueError("nitrogen factor must be finite and positive")
    values = dict(window.influent_values)
    extra = values.get("S_IN", 0.0) * (factor - 1.0)
    values["S_IN"] = values.get("S_IN", 0.0) * factor
    anion = values.get("S_anion", 0.0) + extra
    values["S_anion"] = max(anion, 0.0)
    values["S_cation"] = values.get("S_cation", 0.0) + max(-anion, 0.0)
    return window.model_copy(update={"influent_values": values})


def window_observation(result: WindowResult) -> np.ndarray:
    """Mean on [start, end), excluding the endpoint owned by the next day."""
    return np.array([np.mean(result.outputs[c][:-1]) for c in OUTPUT_COLUMNS])


def local_information(
    engine: TwinEngine,
    initial_state: TwinState,
    windows: Sequence[InfluentWindow],
    measured: pd.DataFrame,
    *,
    config: InformationConfig | None = None,
    sensors: Sequence[SensorSpec] | None = None,
) -> dict[str, object]:
    """Conditional Fisher information with fixed initial state and known other inputs.

    Central differences are with respect to dimensionless log parameters.
    Only actually present samples enter J; F = J.T @ J uses the sensor std.
    CR bounds are local/conditional, not evidence of global identifiability or
    of recovering a daily random walk from weekly laboratory samples.
    """
    cfg = config or InformationConfig()
    specs = {s.column: s for s in (sensors if sensors is not None else default_sensor_suite())}
    rows = measured.set_index("time_days")

    def trajectory(theta: np.ndarray) -> np.ndarray:
        state = initial_state.model_copy(deep=True)
        state.parameter_overrides["k_m_ac"] = float(np.exp(theta[0]))
        values = []
        for window in windows:
            result = engine.advance(state, nitrogen_window(window, float(np.exp(theta[1]))))
            values.append(window_observation(result))
            state = result.state
        return np.asarray(values)

    theta = np.log([cfg.k_m_ac, cfg.nitrogen_factor])
    center = trajectory(theta)
    derivatives = []
    for i in range(2):
        step = np.eye(2)[i] * cfg.log_step
        derivatives.append((trajectory(theta + step) - trajectory(theta - step)) / (2 * cfg.log_step))
    jacobian = []
    for i, window in enumerate(windows):
        day = window.t_start_days
        if day not in rows.index:
            continue
        for j, column in enumerate(OUTPUT_COLUMNS):
            if column in specs and column in rows and np.isfinite(rows.loc[day, column]):
                spec = specs[column]
                std = max(spec.noise_abs + spec.noise_rel * abs(center[i, j]), 1e-12)
                jacobian.append([d[i, j] / std for d in derivatives])
    jac = np.asarray(jacobian, dtype=float).reshape(-1, 2)
    fisher = jac.T @ jac
    singular = np.linalg.svd(jac, compute_uv=False)
    rank = int(np.linalg.matrix_rank(jac)) if jac.size else 0
    covariance = np.linalg.inv(fisher) if rank == 2 else np.full((2, 2), np.nan)
    correlation = float(covariance[0, 1] / np.sqrt(covariance[0, 0] * covariance[1, 1])) if rank == 2 else None
    return {
        "parameters": ["log_k_m_ac", "log_nitrogen_factor"],
        "samples": len(jac), "rank": rank, "fisher": fisher.tolist(),
        "singular_values": singular.tolist(),
        "condition_number": float(singular[0] / singular[-1]) if rank == 2 else None,
        "conditional_log_std": np.sqrt(np.diag(covariance)).tolist() if rank == 2 else None,
        "correlation": correlation,
        "assumptions": "Fixed initial state, constant N factor, nominal other kinetics and measured inputs; local conditional bounds only.",
    }
