"""Synthetic plant scenarios: influent windows with disturbances.

The "plant" is the ADM1 itself with hidden parameters. This module only builds
the inputs (``InfluentWindow`` list); it never runs the model.
"""

from __future__ import annotations

import math
from typing import Annotated, Literal

import numpy as np
from pydantic import Field, model_validator

from simulator.core.defaults import (
    make_default_feed,
    make_default_initial_state,
    make_default_kinetics,
    make_default_operating_conditions,
)
from simulator.core.models import StrictModel
from simulator.digital_twin.contracts import InfluentWindow

# Concentrations scaled by the organic-load factor (noise, weekend pattern).
LOAD_SCALED_STATES: tuple[str, ...] = ("S_su", "S_aa", "S_fa", "S_va", "S_bu", "S_pro", "S_ac", "X_xc", "X_ch", "X_pr", "X_li")
# COD-carrying influent states (kgCOD/m3), used for the cod_in measurement.
COD_STATES: tuple[str, ...] = (
    "S_su", "S_aa", "S_fa", "S_va", "S_bu", "S_pro", "S_ac", "S_I",
    "X_xc", "X_ch", "X_pr", "X_li", "X_I",
)
MIN_TEMPERATURE_C = 15.0
MAX_TEMPERATURE_C = 60.0


def base_influent_values(extensions: list[str] | tuple[str, ...] | None = None) -> dict[str, float]:
    """Default full-model ADM1 influent (state name -> value), without ``Q``/``T (C)``."""
    from simulator.full_model.model import build_full_inputs

    feed = make_default_feed()
    inputs = build_full_inputs(
        operating_conditions=make_default_operating_conditions(),
        feed=feed,
        initial_state=make_default_initial_state(feed),
        parameters=make_default_kinetics(),
        active_extensions=extensions,
    )
    return {k: float(v) for k, v in inputs.influent_values.items() if k not in ("Q", "T (C)")}


def influent_cod(values: dict[str, float]) -> float:
    """Total influent COD [kgCOD/m3] from an influent map."""
    return float(sum(values.get(name, 0.0) for name in COD_STATES))


class _Event(StrictModel):
    t0_days: float = Field(ge=0.0)
    t1_days: float = Field(gt=0.0)

    @model_validator(mode="after")
    def _check_interval(self) -> "_Event":
        if self.t1_days <= self.t0_days:
            raise ValueError("t1_days must be greater than t0_days")
        return self

    def active(self, t: float) -> bool:
        return self.t0_days <= t < self.t1_days


class OrganicOverload(_Event):
    kind: Literal["organic_overload"] = "organic_overload"
    factor: float = Field(gt=0.0, description="Multiplier on X_ch, X_pr, X_li and S_su.")


class TemperatureDrop(_Event):
    kind: Literal["temperature_drop"] = "temperature_drop"
    delta_c: float = Field(description="Temperature change at plateau [C]; negative = drop.")
    ramp_days: float = Field(default=2.0, ge=0.0)

    def delta_at(self, t: float) -> float:
        if t < self.t0_days or t >= self.t1_days + self.ramp_days:
            return 0.0
        if self.ramp_days <= 0.0:
            return self.delta_c if t < self.t1_days else 0.0
        if t < self.t0_days + self.ramp_days:
            return self.delta_c * (t - self.t0_days) / self.ramp_days
        if t < self.t1_days:
            return self.delta_c
        return self.delta_c * (1.0 - (t - self.t1_days) / self.ramp_days)


class AmmoniaSpike(_Event):
    kind: Literal["ammonia_spike"] = "ammonia_spike"
    factor: float = Field(gt=0.0, description="Multiplier on influent total ammoniacal N (S_IN, kmolN/m3); measured NH4+-N is speciated by the engine.")
    counter_ion: Literal["chloride", "none"] = Field(
        default="chloride",
        description=(
            "'chloride': the extra N enters as an ammonium salt (NH4Cl), so S_anion rises by the same "
            "kmol/m3 and the charge balance is unchanged. 'none': it enters as free NH3, a base that "
            "raises the pH."
        ),
    )


class FlowStep(_Event):
    kind: Literal["flow_step"] = "flow_step"
    factor: float = Field(gt=0.0, description="Multiplier on influent flow.")


class CompositionDrift(_Event):
    kind: Literal["composition_drift"] = "composition_drift"
    max_shift_fraction: float = Field(
        default=0.3, ge=0.0, le=1.0,
        description="Fraction of (X_ch + X_pr) moved to X_li at t1 (linear from t0); held after t1.",
    )


ScenarioEvent = Annotated[
    OrganicOverload | TemperatureDrop | AmmoniaSpike | FlowStep | CompositionDrift,
    Field(discriminator="kind"),
]


class SyntheticScenario(StrictModel):
    duration_days: float = Field(gt=0.0)
    window_days: float = Field(default=1.0, gt=0.0)
    volume_m3: float = Field(default=3000.0, gt=0.0)
    base_flow_m3_day: float = Field(default=150.0, gt=0.0)
    base_temperature_c: float = Field(default=35.0, ge=MIN_TEMPERATURE_C, le=MAX_TEMPERATURE_C)
    load_noise_phi: float = Field(default=0.7, ge=0.0, lt=1.0, description="AR(1) coefficient of daily load noise.")
    load_noise_sigma: float = Field(default=0.05, ge=0.0, description="Relative std of the stationary load noise.")
    weekly_pattern: bool = False
    weekend_load_factor: float = Field(default=0.7, gt=0.0)
    events: list[ScenarioEvent] = Field(default_factory=list)
    seed: int = 0
    hidden_parameter_overrides: dict[str, float] = Field(
        default_factory=dict,
        description="Full-model parameter overrides = the plant 'truth' (e.g. k_hyd_ch, k_m_ac).",
    )


def build_windows(scenario: SyntheticScenario, base_values: dict[str, float] | None = None) -> list[InfluentWindow]:
    """Contiguous influent windows covering ``duration_days``; deterministic given the seed."""
    base = dict(base_values) if base_values is not None else base_influent_values()
    rng = np.random.default_rng(scenario.seed)
    n = max(int(math.ceil(scenario.duration_days / scenario.window_days - 1e-9)), 1)
    phi = scenario.load_noise_phi
    # Stationary std = sigma, so the innovation std is sigma*sqrt(1-phi^2).
    innovation = scenario.load_noise_sigma * math.sqrt(1.0 - phi * phi)
    noise = 0.0
    windows: list[InfluentWindow] = []
    for i in range(n):
        t0 = i * scenario.window_days
        t1 = min((i + 1) * scenario.window_days, scenario.duration_days)
        if t1 <= t0:
            break
        tm = 0.5 * (t0 + t1)
        noise = phi * noise + innovation * float(rng.standard_normal())
        load = max(1.0 + noise, 0.05)
        if scenario.weekly_pattern and int(math.floor(tm)) % 7 in (5, 6):
            load *= scenario.weekend_load_factor

        values = dict(base)
        flow = scenario.base_flow_m3_day
        temperature = scenario.base_temperature_c
        for ev in scenario.events:
            if isinstance(ev, CompositionDrift):
                if tm >= ev.t0_days:
                    progress = min((tm - ev.t0_days) / (ev.t1_days - ev.t0_days), 1.0)
                    moved = ev.max_shift_fraction * progress
                    for name in ("X_ch", "X_pr"):
                        shift = values.get(name, 0.0) * moved
                        values[name] = values.get(name, 0.0) - shift
                        values["X_li"] = values.get("X_li", 0.0) + shift
            elif isinstance(ev, TemperatureDrop):
                temperature += ev.delta_at(tm)
            elif ev.active(tm):
                if isinstance(ev, OrganicOverload):
                    for name in ("X_ch", "X_pr", "X_li", "S_su"):
                        values[name] = values.get(name, 0.0) * ev.factor
                elif isinstance(ev, AmmoniaSpike):
                    extra_n = values.get("S_IN", 0.0) * (ev.factor - 1.0)
                    values["S_IN"] = values.get("S_IN", 0.0) + extra_n
                    if ev.counter_ion == "chloride":
                        # NH4+ and Cl- are both 1 kmol charge per kmol.
                        values["S_anion"] = values.get("S_anion", 0.0) + extra_n
                elif isinstance(ev, FlowStep):
                    flow *= ev.factor
        for name in LOAD_SCALED_STATES:
            if name in values:
                values[name] *= load
        values = {k: max(float(v), 0.0) for k, v in values.items()}
        windows.append(
            InfluentWindow(
                t_start_days=t0,
                t_end_days=t1,
                flow_m3_day=max(flow, 1e-6),
                temperature_c=float(min(max(temperature, MIN_TEMPERATURE_C), MAX_TEMPERATURE_C)),
                influent_values=values,
            )
        )
    return windows


# Hidden "true plant" kinetics: slower carbohydrate hydrolysis and acetoclastic
# uptake than the nominal ADM1 values (k_hyd_ch 10 d-1, k_m_ac 8 d-1). Large
# enough that an open-loop twin with nominal values visibly drifts.
HIDDEN_TRUTH: dict[str, float] = {"k_hyd_ch": 6.0, "k_m_ac": 5.5}


def default_scenarios() -> dict[str, SyntheticScenario]:
    """Three ready-made ~120-day cases."""
    common = dict(duration_days=120.0, window_days=1.0, weekly_pattern=True)
    return {
        "steady_noisy": SyntheticScenario(**common, seed=1, hidden_parameter_overrides=dict(HIDDEN_TRUTH)),
        "overload_recovery": SyntheticScenario(
            **common,
            seed=2,
            events=[OrganicOverload(t0_days=40.0, t1_days=50.0, factor=1.8)],
            hidden_parameter_overrides=dict(HIDDEN_TRUTH),
        ),
        "cold_snap_ammonia": SyntheticScenario(
            **common,
            seed=3,
            events=[
                TemperatureDrop(t0_days=60.0, t1_days=75.0, delta_c=-8.0, ramp_days=3.0),
                AmmoniaSpike(t0_days=65.0, t1_days=72.0, factor=4.0),
            ],
            hidden_parameter_overrides=dict(HIDDEN_TRUTH),
        ),
    }
