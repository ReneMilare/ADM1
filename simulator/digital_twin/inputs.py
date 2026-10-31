"""Build the twin's influent from what a plant actually measures.

A real plant knows the influent flow (online) and the total influent COD
(lab, typically weekly). It does not know the daily COD fractionation. The
twin therefore keeps a nominal composition and rescales its COD states to the
last measured total COD. The unknown part of the load is what Phase 2 (data
assimilation) has to estimate.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

import pandas as pd

from simulator.digital_twin.contracts import InfluentWindow
from simulator.digital_twin.scenarios import COD_STATES, influent_cod


def _held(series: pd.Series, day: float) -> float | None:
    """Last finite value measured at or before ``day`` (zero-order hold)."""
    known = series[(series.index <= day + 1e-9) & series.notna()]
    if known.empty:
        return None
    return float(known.iloc[-1])


def _first_known(value: float | None, fallback: float) -> float:
    return fallback if value is None else value


def observed_windows(
    windows: Sequence[InfluentWindow],
    measured: pd.DataFrame,
    nominal_influent: Mapping[str, float],
    *,
    nominal_flow_m3_day: float,
    nominal_temperature_c: float,
    report_delay_days: float = 1.0,
) -> list[InfluentWindow]:
    """Replace each window's true influent by the one the twin can infer from measurements.

    Flow and temperature come from the online sensors, COD from the last lab
    sample. A measurement row labelled ``d`` is the mean over ``[d, d+1)``, so
    it only exists from ``d + report_delay_days`` on (default: one day). A
    window starting at ``t`` therefore sees rows labelled ``<= t - delay``.
    Before the first available sample of a signal, the nominal value is used.
    """
    if report_delay_days < 1.0:
        raise ValueError("report_delay_days must be >= 1: a daily mean is only known after its day ends")
    frame = measured.set_index("time_days")
    nominal_cod = influent_cod(dict(nominal_influent))
    if nominal_cod <= 0.0:
        raise ValueError("nominal influent must contain COD")
    observed: list[InfluentWindow] = []
    for window in windows:
        day = math.floor(window.t_start_days - report_delay_days + 1e-9)
        flow = _first_known(_held(frame["q_in_m3_d"], day), nominal_flow_m3_day)
        temperature = _first_known(_held(frame["temperature_c"], day), nominal_temperature_c)
        cod = _first_known(_held(frame["cod_in_kg_m3"], day), nominal_cod)
        scale = cod / nominal_cod
        values = {name: (value * scale if name in COD_STATES else value) for name, value in nominal_influent.items()}
        observed.append(
            window.model_copy(
                update={
                    "flow_m3_day": max(flow, 1e-6),
                    "temperature_c": min(max(temperature, 15.0), 60.0),
                    "influent_values": values,
                }
            )
        )
    return observed
