"""Shared data contracts for the digital twin (Phase 1: digital shadow).

The twin advances the native full ADM1 CSTR window by window. Inside one
window the operating inputs are piecewise-constant (typical daily SCADA/lab
resolution). Between windows the complete dynamic state vector is carried
over, so a run never restarts from t=0.

State and influent maps use the full-model ADM1 names, e.g. ``S_ac``,
``X_ac``, ``S_IC``, ``S_gas_ch4`` (see
``simulator.full_model.model.resolve_full_model_assembly``).

Observable columns retain their historical names but use physical bases:
``biogas_m3_d`` is dry normal volume at 273.15 K and 1.01325 bar (Nm3/d),
``ch4_fraction`` excludes water and includes all active headspace gases,
and ``nh4_kg_n_m3`` is 14*(S_IN - S_nh3), with both N species in kmolN/m3.

``alkalinity_kmol_m3`` uses the agreed ADM1 total-alkalinity species sum:
S_hco3_ion + S_ac_ion/64 + S_pro_ion/112 + S_bu_ion/160 + S_va_ion/208
+ S_nh3. The VFA divisors are kgCOD/kmol of monovalent anion (Rosén &
Jeppsson 2006, §4.2.1); the result is kmol charge/m3 = (eq/m3)/1000.
The laboratory reporting convention is acid titration to pH 4.3 (DIN
38409-7:2005-12, §4, https://www.dinmedia.de/de/norm/din-38409-7/85208100).
This species sum is the requested ADM1 approximation, not a simulation of
the finite-endpoint titration curve; residual bases at pH 4.3, water ions
and additional titratable extension species are outside this convention.
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
    "biogas_m3_d",  # dry normal biogas [Nm3/d], 0 °C, 1 atm
    "ch4_fraction",  # dry CH4 molar fraction, including extension gases [0-1]
    "ph",  # reactor pH
    "vfa_kg_cod_m3",  # total VFA in reactor (lab)
    "alkalinity_kmol_m3",  # HCO3- + VFA anions + NH3 [kmol charge/m3]
    "nh4_kg_n_m3",  # NH4+-N only [kgN/m3], excluding free NH3
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
