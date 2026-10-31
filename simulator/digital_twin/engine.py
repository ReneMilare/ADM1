"""Window-by-window native ADM1 full CSTR digital twin."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from pathlib import Path

import numpy as np

from simulator.core.defaults import make_default_feed, make_default_initial_state, make_default_kinetics
from simulator.core.models import OperatingConditions, SimulationConfig
from simulator.digital_twin.contracts import InfluentWindow, TwinState, WindowResult
from simulator.full_model.model import FullModelInputs, build_full_inputs, build_full_inputs_from_state_maps
from simulator.full_model.solver import simulate_with_full_inputs


class TwinEngine:
    """Advance a single CSTR with piecewise-constant operating inputs.

    Each window's temperature sets T_op, T_ad and temperature-dependent
    physicochemical constants through the full model's parameter resolver.
    The native CSTR does not apply an additional temperature correction to
    biochemical kinetic constants. Operational parameter overrides are rejected
    so they cannot silently supersede the window or reactor configuration.
    Warmup starts from the project's default inoculum and is not a convergence test.
    """

    def __init__(
        self,
        volume_m3: float,
        active_extensions: Sequence[str] | None = None,
        parameter_overrides: Mapping[str, float] | None = None,
        rtol: float = 1e-5,
        atol: float = 1e-7,
        points_per_day: float = 4.0,
    ) -> None:
        if not math.isfinite(volume_m3) or volume_m3 <= 0:
            raise ValueError("volume_m3 must be finite and positive")
        if not math.isfinite(points_per_day) or points_per_day <= 0:
            raise ValueError("points_per_day must be finite and positive")
        if not math.isfinite(rtol) or not math.isfinite(atol) or not 0 < atol <= rtol:
            raise ValueError("tolerances must be finite and satisfy 0 < atol <= rtol")
        self.volume_m3 = float(volume_m3)
        self.active_extensions = list(active_extensions or ())
        self.parameter_overrides = dict(parameter_overrides or {})
        self._check_overrides(self.parameter_overrides)
        self.rtol, self.atol = rtol, atol
        self.points_per_day = points_per_day

    @staticmethod
    def _check_overrides(overrides: Mapping[str, float]) -> None:
        reserved = {"T_op", "T_ad", "V_liq", "V_gas", "V_ad", "q_ad"}
        conflict = reserved.intersection(overrides)
        if conflict:
            raise ValueError(f"Operating parameters cannot be overridden: {sorted(conflict)}")

    def _simulation(self, duration: float) -> SimulationConfig:
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError("duration must be finite and positive")
        points = max(21, min(4001, math.ceil(duration * self.points_per_day) + 1))
        # The general UI config limits duration to >0.1 d and <=3650 d; the
        # solver itself also supports shorter digital-twin windows.
        config = SimulationConfig(duration_days=1.0, evaluation_points=points, backend="full", rtol=self.rtol, atol=self.atol, persist=False)
        return config.model_copy(update={"duration_days": duration})

    def _inputs(
        self, window: InfluentWindow, initial_values: Mapping[str, float], overrides: Mapping[str, float]
    ) -> FullModelInputs:
        self._check_overrides(overrides)
        return build_full_inputs_from_state_maps(
            operating_conditions=OperatingConditions(volume_m3=self.volume_m3, temperature_c=window.temperature_c),
            parameters=make_default_kinetics(),
            influent_values=window.influent_values,
            initial_values=initial_values,
            flow_rate_m3_day=window.flow_m3_day,
            active_extensions=self.active_extensions,
            extension_parameter_overrides=overrides,
        )

    def initial_state(self, window: InfluentWindow, *, warmup_days: float = 200.0) -> TwinState:
        feed = make_default_feed()
        seed = build_full_inputs(
            operating_conditions=OperatingConditions(volume_m3=self.volume_m3, temperature_c=window.temperature_c),
            feed=feed,
            initial_state=make_default_initial_state(feed),
            parameters=make_default_kinetics(),
            active_extensions=self.active_extensions,
        )
        inputs = self._inputs(window, seed.initial_values, self.parameter_overrides)
        result = simulate_with_full_inputs(inputs=inputs, simulation=self._simulation(warmup_days))
        profiles = result["profiles"]
        return TwinState(time_days=window.t_start_days, volume_m3=self.volume_m3,
                         dynamic_state={name: profiles[name][-1] for name in inputs.assembly.dynamic_state_names},
                         parameter_overrides=dict(self.parameter_overrides), active_extensions=list(self.active_extensions))

    def advance(self, state: TwinState, window: InfluentWindow) -> WindowResult:
        if not math.isclose(state.time_days, window.t_start_days, rel_tol=0.0, abs_tol=1e-9):
            raise ValueError("window must start at state.time_days")
        if state.volume_m3 != self.volume_m3 or state.active_extensions != self.active_extensions:
            raise ValueError("state volume and active extensions must match the engine")
        inputs = self._inputs(window, state.dynamic_state, state.parameter_overrides)
        names = inputs.assembly.dynamic_state_names
        if set(state.dynamic_state) != set(names):
            raise ValueError("state must contain exactly the dynamic states of the active assembly")
        vector = np.asarray([state.dynamic_state[name] for name in names], dtype=float)
        result = simulate_with_full_inputs(inputs=inputs, simulation=self._simulation(window.t_end_days - window.t_start_days),
                                           initial_dynamic_state=vector, t_start_days=window.t_start_days)
        profiles = result["profiles"]
        new_state = TwinState(time_days=window.t_end_days, volume_m3=state.volume_m3,
                              dynamic_state={name: profiles[name][-1] for name in names},
                              parameter_overrides=dict(state.parameter_overrides), active_extensions=list(state.active_extensions))
        outputs = {target: profiles[source] for target, source in {
            "biogas_m3_d": "biogas_m3_day", "ch4_fraction": "ch4_fraction", "ph": "ph",
            "vfa_kg_cod_m3": "vfa_total", "alkalinity_kmol_m3": "alkalinity",
            "nh4_kg_n_m3": "inorganic_nitrogen",
        }.items()}
        return WindowResult(state=new_state, time_days=result["time_days"], outputs=outputs)

    def run(self, state: TwinState, windows: Sequence[InfluentWindow]) -> list[WindowResult]:
        results = []
        for window in windows:
            result = self.advance(state, window)
            results.append(result)
            state = result.state
        return results

    @staticmethod
    def save_state(state: TwinState, path: str | Path) -> None:
        save_state(state, path)

    @staticmethod
    def load_state(path: str | Path) -> TwinState:
        return load_state(path)


def save_state(state: TwinState, path: str | Path) -> None:
    Path(path).write_text(state.model_dump_json(indent=2), encoding="utf-8")


def load_state(path: str | Path) -> TwinState:
    return TwinState.model_validate_json(Path(path).read_text(encoding="utf-8"))
