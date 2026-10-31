"""Shared data contracts for the digital twin (Phase 1: digital shadow).

The twin advances the native full ADM1 CSTR window by window. Inside one
window the operating inputs are piecewise-constant (typical daily SCADA/lab
resolution). Between windows the complete dynamic state vector is carried
over, so a run never restarts from t=0.

State and influent maps use the full-model ADM1 names, e.g. ``S_ac``,
``X_ac``, ``S_IC``, ``S_gas_ch4`` (see
``simulator.full_model.model.resolve_full_model_assembly``).
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from simulator.core.models import StrictModel

# Columns of a plant measurement table (synthetic or real). All are optional
# per row: real plants have gaps and lab values arrive at lower frequency.
MEASUREMENT_COLUMNS: tuple[str, ...] = (
    "time_days",
    "q_in_m3_d",  # influent flow
    "temperature_c",
    "cod_in_kg_m3",  # total influent COD (lab, often weekly)
    "biogas_m3_d",  # total biogas flow at normal conditions
    "ch4_fraction",  # CH4 molar fraction in biogas [0-1]
    "ph",  # reactor pH
    "vfa_kg_cod_m3",  # total VFA in reactor (lab)
    "alkalinity_kmol_m3",  # total alkalinity proxy / S_IC
    "nh4_kg_n_m3",  # S_IN
)


class InfluentWindow(StrictModel):
    """Operating inputs held constant over [t_start_days, t_end_days)."""

    t_start_days: float = Field(ge=0.0)
    t_end_days: float = Field(gt=0.0)
    flow_m3_day: float = Field(gt=0.0)
    temperature_c: float = Field(ge=15.0, le=60.0)
    influent_values: dict[str, float] = Field(
        description="Full-model ADM1 influent concentrations (state name -> value)."
    )

    @model_validator(mode="after")
    def check_interval(self) -> "InfluentWindow":
        if self.t_end_days <= self.t_start_days:
            raise ValueError("t_end_days must be greater than t_start_days")
        return self


class TwinState(StrictModel):
    """Checkpoint of the virtual reactor at time ``time_days``."""

    time_days: float = Field(ge=0.0)
    volume_m3: float = Field(gt=0.0)
    dynamic_state: dict[str, float] = Field(
        description="Full-model dynamic state vector keyed by state name."
    )
    parameter_overrides: dict[str, float] = Field(
        default_factory=dict,
        description="Full-model parameter overrides active in this twin (e.g. calibrated k_hyd).",
    )
    active_extensions: list[str] = Field(default_factory=list)
    schema_version: Literal[1] = 1


class WindowResult(StrictModel):
    """Output of advancing the twin over one window."""

    state: TwinState
    time_days: list[float]
    # Model outputs on the same keys as MEASUREMENT_COLUMNS (minus time_days and inputs).
    outputs: dict[str, list[float]]
