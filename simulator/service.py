from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Iterable
from uuid import uuid4

import numpy as np
from scipy.integrate import solve_ivp
from scipy.optimize import minimize_scalar

from simulator.core.defaults import (
    make_default_feed,
    make_default_initial_state,
    make_default_kinetics,
    make_default_operating_conditions,
    make_default_reactor_config,
    make_default_simulation_config,
)
from simulator.core.models import (
    CalibrationPoint,
    CalibrationResult,
    CoDigestionBlend,
    FeedDefinition,
    InitialState,
    KineticParameters,
    OBJECTIVE_NAMES,
    OperatingConditions,
    OptimizationEvaluation,
    OptimizationResult,
    ReactorConfig,
    ScenarioComparison,
    ScenarioComparisonEntry,
    SensitivityPoint,
    SensitivityResult,
    SimulationConfig,
    SimulationResult,
    SimulationSummary,
    STATE_NAMES,
)
from simulator.core.pyadm1_backend import simulate_with_pyadm1
from simulator.full_model.solver import simulate_with_full
from simulator.reactor_models import build_reactor
from simulator.scenario_store import ScenarioStore


@dataclass(frozen=True)
class _ResolvedBackend:
    requested: str
    used: str
    fallback_reason: str | None = None


_BACKEND_COMPARISON_METRICS = (
    "methane_final_m3_day",
    "biogas_final_m3_day",
    "ph_final",
    "vfa_final",
    "effluent_cod_final",
    "stability_index",
)


class ADM1SimulationService:
    def __init__(self, store: ScenarioStore | None = None) -> None:
        self.store = store or ScenarioStore()

    def simulate(
        self,
        reactor: ReactorConfig | str = "cstr",
        *,
        operating_conditions: OperatingConditions | None = None,
        feed: FeedDefinition | None = None,
        blend: CoDigestionBlend | None = None,
        initial_state: InitialState | None = None,
        parameters: KineticParameters | None = None,
        simulation: SimulationConfig | None = None,
        metadata: dict[str, object] | None = None,
    ) -> SimulationResult:
        reactor_config = self._resolve_reactor(reactor)
        request_metadata = dict(metadata or {})
        operating = (operating_conditions or make_default_operating_conditions()).model_copy(deep=True)
        if blend is not None:
            feed_model = blend.blend().model_copy(deep=True)
            request_metadata.update(
                {
                    "codigestion": True,
                    "blend_name": blend.name,
                    "blend_components": [component.feed.name for component in blend.components],
                    "blend_fractions": [float(component.volume_fraction) for component in blend.components],
                    "cn_ratio": float(blend.cn_ratio()),
                }
            )
        else:
            feed_model = (feed or make_default_feed()).model_copy(deep=True)
        if feed_model.flow_rate_m3_day is None:
            feed_model = feed_model.model_copy(update={"flow_rate_m3_day": operating.volume_m3 / operating.hrt_days})
        initial = (initial_state or make_default_initial_state(feed_model)).model_copy(deep=True)
        kinetics = (parameters or make_default_kinetics()).model_copy(deep=True)
        sim_config = (simulation or make_default_simulation_config()).model_copy(deep=True)
        backend = self._resolve_backend(reactor_config, sim_config)

        if backend.used == "pyadm1":
            backend_result = simulate_with_pyadm1(
                operating_conditions=operating,
                feed=feed_model,
                initial_state=initial,
                parameters=kinetics,
                simulation=sim_config,
            )
            time_days = np.asarray(backend_result["time_days"], dtype=float)
            profiles = backend_result["profiles"]
            execution_metadata = dict(backend_result["metadata"])
        elif backend.used == "full":
            backend_result = simulate_with_full(
                operating_conditions=operating,
                feed=feed_model,
                initial_state=initial,
                parameters=kinetics,
                simulation=sim_config,
                active_extensions=sim_config.full_extensions,
                extension_parameter_overrides=sim_config.full_extension_parameter_overrides,
            )
            time_days = np.asarray(backend_result["time_days"], dtype=float)
            profiles = backend_result["profiles"]
            execution_metadata = dict(backend_result["metadata"])
        else:
            time_days, profiles, execution_metadata = self._simulate_reduced(
                reactor=reactor_config,
                operating_conditions=operating,
                feed=feed_model,
                initial_state=initial,
                parameters=kinetics,
                simulation=sim_config,
            )

        simulation_id = self._new_simulation_id(reactor_config.reactor_type)
        result_metadata = dict(request_metadata)
        result_metadata.update(execution_metadata)
        result_metadata["backend_requested"] = backend.requested
        result_metadata["backend_used"] = backend.used
        if backend.fallback_reason is not None:
            result_metadata["backend_fallback_reason"] = backend.fallback_reason

        summary = self._build_summary(time_days=time_days, series=profiles, metadata=result_metadata)
        result = SimulationResult(
            simulation_id=simulation_id,
            created_at=datetime.now(UTC).isoformat(timespec="seconds"),
            reactor=reactor_config,
            operating_conditions=operating,
            feed=feed_model,
            initial_state=initial,
            parameters=kinetics,
            simulation=sim_config,
            time_days=[float(value) for value in time_days],
            series={name: [float(item) for item in values] for name, values in profiles.items()},
            summary=summary,
            metadata=result_metadata,
        )
        if sim_config.persist:
            self.store.save(result)
        return result

    def steady_state(
        self,
        reactor: ReactorConfig | str = "cstr",
        *,
        operating_conditions: OperatingConditions | None = None,
        feed: FeedDefinition | None = None,
        blend: CoDigestionBlend | None = None,
        initial_state: InitialState | None = None,
        parameters: KineticParameters | None = None,
        duration_days: float = 180.0,
        tolerance: float = 1e-3,
    ) -> dict[str, object]:
        simulation = make_default_simulation_config().model_copy(update={"duration_days": duration_days})
        result = self.simulate(
            reactor,
            operating_conditions=operating_conditions,
            feed=feed,
            blend=blend,
            initial_state=initial_state,
            parameters=parameters,
            simulation=simulation,
            metadata={"mode": "steady_state"},
        )
        backend_used = str(result.metadata.get("backend_used", "reduced"))
        if backend_used in {"pyadm1", "full"}:
            derivative_norm = self._tail_convergence_metric(result)
            return {
                "simulation_id": result.simulation_id,
                "backend_used": backend_used,
                "derivative_norm": derivative_norm,
                "converged": derivative_norm <= tolerance,
                "tolerance": tolerance,
                "convergence_metric": "tail_relative_change_per_day",
                "summary": result.summary.model_dump(),
            }

        final_internal_state_raw = result.metadata.get("final_internal_state")
        if final_internal_state_raw is None:
            derivative_norm = self._tail_convergence_metric(result)
            return {
                "simulation_id": result.simulation_id,
                "backend_used": backend_used,
                "derivative_norm": derivative_norm,
                "converged": derivative_norm <= tolerance,
                "tolerance": tolerance,
                "convergence_metric": "tail_relative_change_per_day",
                "summary": result.summary.model_dump(),
            }
        final_internal_state = np.asarray(final_internal_state_raw, dtype=float)
        reactor_model = build_reactor(result.reactor)
        derivative = reactor_model.rhs(
            result.time_days[-1],
            final_internal_state,
            feed=result.feed,
            operating_conditions=result.operating_conditions,
            parameters=result.parameters,
        )
        derivative_norm = float(np.linalg.norm(derivative, ord=np.inf))
        return {
            "simulation_id": result.simulation_id,
            "backend_used": backend_used,
            "derivative_norm": derivative_norm,
            "converged": derivative_norm <= tolerance,
            "tolerance": tolerance,
            "convergence_metric": "state_derivative_inf_norm",
            "summary": result.summary.model_dump(),
        }

    def sensitivity_analysis(
        self,
        parameter_path: str,
        *,
        objective: str = "methane_final_m3_day",
        perturbation: float = 0.1,
        reactor: ReactorConfig | str = "cstr",
        operating_conditions: OperatingConditions | None = None,
        feed: FeedDefinition | None = None,
        blend: CoDigestionBlend | None = None,
        initial_state: InitialState | None = None,
        parameters: KineticParameters | None = None,
        simulation: SimulationConfig | None = None,
    ) -> SensitivityResult:
        self._validate_objective(objective)
        base_reactor = self._resolve_reactor(reactor)
        base_operating = (operating_conditions or make_default_operating_conditions()).model_copy(deep=True)
        base_feed = (feed or make_default_feed()).model_copy(deep=True)
        # When a blend is provided, the effective feed for initial state is the blended result —
        # matching how simulate() itself resolves the feed when blend is not None.
        _effective_feed_for_init = blend.blend() if blend is not None else base_feed
        base_initial = (initial_state or make_default_initial_state(_effective_feed_for_init)).model_copy(deep=True)
        base_parameters = (parameters or make_default_kinetics()).model_copy(deep=True)
        base_simulation = (simulation or make_default_simulation_config()).model_copy(update={"persist": False}, deep=True)

        baseline_value = float(self._get_parameter_value(parameter_path, base_reactor, base_operating, base_feed, base_parameters))
        baseline_result = self.simulate(
            base_reactor,
            operating_conditions=base_operating,
            feed=base_feed,
            blend=blend,
            initial_state=base_initial,
            parameters=base_parameters,
            simulation=base_simulation,
        )
        baseline_objective = self._objective_value(baseline_result.summary, objective)
        points: list[SensitivityPoint] = []
        for delta_fraction in (-2 * perturbation, -perturbation, perturbation, 2 * perturbation):
            candidate_value = max(baseline_value * (1.0 + delta_fraction), 1e-6)
            reactor_cfg, operating_cfg, feed_cfg, param_cfg = self._clone_inputs(base_reactor, base_operating, base_feed, base_parameters)
            self._set_parameter_value(parameter_path, candidate_value, reactor_cfg, operating_cfg, feed_cfg, param_cfg)
            candidate_result = self.simulate(
                reactor_cfg,
                operating_conditions=operating_cfg,
                feed=feed_cfg,
                blend=blend,
                initial_state=base_initial,
                parameters=param_cfg,
                simulation=base_simulation,
            )
            points.append(
                SensitivityPoint(
                    delta_fraction=delta_fraction,
                    parameter_value=candidate_value,
                    objective_value=self._objective_value(candidate_result.summary, objective),
                )
            )
        return SensitivityResult(
            parameter_path=parameter_path,
            objective=objective,
            baseline_value=baseline_value,
            baseline_objective=baseline_objective,
            points=points,
        )

    def compare_backends(
        self,
        backends: Iterable[str],
        *,
        reactor: ReactorConfig | str = "cstr",
        operating_conditions: OperatingConditions | None = None,
        feed: FeedDefinition | None = None,
        blend: CoDigestionBlend | None = None,
        initial_state: InitialState | None = None,
        parameters: KineticParameters | None = None,
        simulation: SimulationConfig | None = None,
    ) -> dict[str, object]:
        requested_backends = tuple(dict.fromkeys(str(item) for item in backends))
        if len(requested_backends) < 2:
            raise ValueError("Forneca pelo menos 2 backends para comparar.")

        reactor_config = self._resolve_reactor(reactor)
        base_operating = (operating_conditions or make_default_operating_conditions()).model_copy(deep=True)
        base_feed = (feed or make_default_feed()).model_copy(deep=True)
        effective_feed_for_init = blend.blend() if blend is not None else base_feed
        base_initial = (initial_state or make_default_initial_state(effective_feed_for_init)).model_copy(deep=True)
        base_parameters = (parameters or make_default_kinetics()).model_copy(deep=True)
        base_simulation = (simulation or make_default_simulation_config()).model_copy(update={"persist": False}, deep=True)

        entries: list[dict[str, object]] = []
        baseline_result: SimulationResult | None = None
        for backend_name in requested_backends:
            result = self.simulate(
                reactor_config,
                operating_conditions=base_operating,
                feed=base_feed,
                blend=blend,
                initial_state=base_initial,
                parameters=base_parameters,
                simulation=base_simulation.model_copy(update={"backend": backend_name}, deep=True),
                metadata={"mode": "backend_comparison", "comparison_group": list(requested_backends)},
            )
            if baseline_result is None:
                baseline_result = result
            deltas = {}
            for metric_name in _BACKEND_COMPARISON_METRICS:
                current_value = float(getattr(result.summary, metric_name))
                baseline_value = float(getattr(baseline_result.summary, metric_name))
                denominator = baseline_value if abs(baseline_value) > 1e-12 else 1e-12
                deltas[metric_name] = {
                    "value": current_value,
                    "baseline": baseline_value,
                    "absolute": current_value - baseline_value,
                    "relative_pct": ((current_value - baseline_value) / denominator) * 100.0,
                }
            entries.append(
                {
                    "simulation_id": result.simulation_id,
                    "reactor_type": result.reactor.reactor_type,
                    "backend_requested": str(result.metadata.get("backend_requested", backend_name)),
                    "backend_used": str(result.metadata.get("backend_used", backend_name)),
                    "fallback_reason": str(result.metadata.get("backend_fallback_reason", "") or ""),
                    "summary": result.summary.model_dump(),
                    "delta_vs_baseline": deltas,
                }
            )

        used_backends = {str(entry["backend_used"]) for entry in entries}
        reduced_is_exploratory = "reduced" in used_backends and bool(used_backends.intersection({"pyadm1", "full"}))
        note = None
        if reduced_is_exploratory:
            note = (
                "O backend `reduced` aparece nesta comparacao apenas com carater operacional e exploratorio; "
                "ele nao deve ser tratado como baseline matematico do backend `full`."
            )

        return {
            "reactor_type": reactor_config.reactor_type,
            "requested_backends": list(requested_backends),
            "baseline_backend": str(entries[0]["backend_used"]),
            "entries": entries,
            "reduced_is_exploratory": reduced_is_exploratory,
            "note": note,
        }

    def compare_reactors(
        self,
        reactors: Iterable[ReactorConfig | str],
        *,
        operating_conditions: OperatingConditions | None = None,
        feed: FeedDefinition | None = None,
        blend: CoDigestionBlend | None = None,
        initial_state: InitialState | None = None,
        parameters: KineticParameters | None = None,
        simulation: SimulationConfig | None = None,
    ) -> ScenarioComparison:
        entries: list[ScenarioComparisonEntry] = []
        base_simulation = (simulation or make_default_simulation_config()).model_copy(update={"persist": False}, deep=True)
        for reactor in reactors:
            result = self.simulate(
                reactor,
                operating_conditions=operating_conditions,
                feed=feed,
                blend=blend,
                initial_state=initial_state,
                parameters=parameters,
                simulation=base_simulation,
            )
            entries.append(self._comparison_entry(result))
        return ScenarioComparison(scenario_count=len(entries), scenarios=entries)

    def get_result(self, simulation_id: str) -> SimulationResult:
        return self.store.load(simulation_id)

    def list_simulations(self) -> list[str]:
        return self.store.list_simulation_ids()

    def get_biogas_production(self, simulation_id: str) -> dict[str, object]:
        result = self.get_result(simulation_id)
        return {
            "simulation_id": simulation_id,
            "time_days": result.time_days,
            "methane_m3_day": result.series["methane_m3_day"],
            "co2_m3_day": result.series["co2_m3_day"],
            "h2_m3_day": result.series["h2_m3_day"],
            "biogas_m3_day": result.series["biogas_m3_day"],
            "ch4_fraction": result.series["ch4_fraction"],
            "summary": result.summary.model_dump(),
        }

    def get_vfa_profile(self, simulation_id: str) -> dict[str, object]:
        result = self.get_result(simulation_id)
        return {
            "simulation_id": simulation_id,
            "time_days": result.time_days,
            "acetate": result.series["acetate"],
            "propionate": result.series["propionate"],
            "vfa_total": result.series["vfa_total"],
            "effluent_cod": result.series["effluent_cod"],
        }

    def get_ph_profile(self, simulation_id: str) -> dict[str, object]:
        result = self.get_result(simulation_id)
        return {
            "simulation_id": result.simulation_id,
            "time_days": result.time_days,
            "ph": result.series["ph"],
            "alkalinity": result.series["alkalinity"],
            "inorganic_nitrogen": result.series["inorganic_nitrogen"],
        }

    def compare_scenarios(self, simulation_ids: Iterable[str]) -> ScenarioComparison:
        entries = [self._comparison_entry(self.get_result(simulation_id)) for simulation_id in simulation_ids]
        return ScenarioComparison(scenario_count=len(entries), scenarios=entries)

    def optimize_parameter(
        self,
        parameter_path: str,
        *,
        minimum: float,
        maximum: float,
        steps: int = 7,
        objective: str = "methane_final_m3_day",
        goal: str = "maximize",
        reactor: ReactorConfig | str = "cstr",
        operating_conditions: OperatingConditions | None = None,
        feed: FeedDefinition | None = None,
        blend: CoDigestionBlend | None = None,
        initial_state: InitialState | None = None,
        parameters: KineticParameters | None = None,
        simulation: SimulationConfig | None = None,
    ) -> OptimizationResult:
        self._validate_objective(objective)
        if goal not in {"maximize", "minimize"}:
            raise ValueError("goal must be 'maximize' or 'minimize'")
        if maximum <= minimum:
            raise ValueError("maximum must be greater than minimum")

        base_reactor = self._resolve_reactor(reactor)
        base_operating = (operating_conditions or make_default_operating_conditions()).model_copy(deep=True)
        base_feed = (feed or make_default_feed()).model_copy(deep=True)
        base_initial = (initial_state or make_default_initial_state(base_feed)).model_copy(deep=True)
        base_parameters = (parameters or make_default_kinetics()).model_copy(deep=True)
        base_simulation = (simulation or make_default_simulation_config()).model_copy(update={"persist": False}, deep=True)

        evaluations: list[OptimizationEvaluation] = []
        best_value = None
        best_objective = None

        for candidate_value in np.linspace(minimum, maximum, steps):
            reactor_cfg, operating_cfg, feed_cfg, param_cfg = self._clone_inputs(base_reactor, base_operating, base_feed, base_parameters)
            self._set_parameter_value(parameter_path, float(candidate_value), reactor_cfg, operating_cfg, feed_cfg, param_cfg)
            result = self.simulate(
                reactor_cfg,
                operating_conditions=operating_cfg,
                feed=feed_cfg,
                blend=blend,
                initial_state=base_initial,
                parameters=param_cfg,
                simulation=base_simulation,
            )
            objective_value = self._objective_value(result.summary, objective)
            evaluations.append(OptimizationEvaluation(parameter_value=float(candidate_value), objective_value=objective_value))
            if best_objective is None:
                best_value = float(candidate_value)
                best_objective = objective_value
            elif goal == "maximize" and objective_value > best_objective:
                best_value = float(candidate_value)
                best_objective = objective_value
            elif goal == "minimize" and objective_value < best_objective:
                best_value = float(candidate_value)
                best_objective = objective_value

        if best_value is None or best_objective is None:
            raise RuntimeError("No optimization candidates were evaluated")

        final_reactor, final_operating, final_feed, final_parameters = self._clone_inputs(base_reactor, base_operating, base_feed, base_parameters)
        self._set_parameter_value(parameter_path, best_value, final_reactor, final_operating, final_feed, final_parameters)
        final_result = self.simulate(
            final_reactor,
            operating_conditions=final_operating,
            feed=final_feed,
            blend=blend,
            initial_state=base_initial,
            parameters=final_parameters,
            simulation=(simulation or make_default_simulation_config()).model_copy(deep=True),
            metadata={"mode": "optimization", "parameter_path": parameter_path, "goal": goal},
        )
        return OptimizationResult(
            parameter_path=parameter_path,
            objective=objective,
            goal=goal,
            best_value=best_value,
            best_objective=best_objective,
            simulation_id=final_result.simulation_id,
            evaluations=evaluations,
        )

    def calibrate_model(
        self,
        experimental_data: list[CalibrationPoint],
        *,
        parameter_path: str = "kinetics.k_hyd",
        minimum: float = 0.1,
        maximum: float = 1.5,
        reactor: ReactorConfig | str = "cstr",
        operating_conditions: OperatingConditions | None = None,
        feed: FeedDefinition | None = None,
        blend: CoDigestionBlend | None = None,
        initial_state: InitialState | None = None,
        parameters: KineticParameters | None = None,
        simulation: SimulationConfig | None = None,
    ) -> CalibrationResult:
        if not experimental_data:
            raise ValueError("experimental_data cannot be empty")
        if maximum <= minimum:
            raise ValueError("maximum must be greater than minimum")

        base_reactor = self._resolve_reactor(reactor)
        base_operating = (operating_conditions or make_default_operating_conditions()).model_copy(deep=True)
        base_feed = (feed or make_default_feed()).model_copy(deep=True)
        base_initial = (initial_state or make_default_initial_state(base_feed)).model_copy(deep=True)
        base_parameters = (parameters or make_default_kinetics()).model_copy(deep=True)
        default_simulation = simulation or make_default_simulation_config()
        max_time = max(point.time_days for point in experimental_data)
        base_simulation = default_simulation.model_copy(
            update={"duration_days": max(default_simulation.duration_days, max_time), "persist": False},
            deep=True,
        )
        observation_times = np.asarray([point.time_days for point in experimental_data], dtype=float)
        observed_values = np.asarray([point.observed_methane_m3_day for point in experimental_data], dtype=float)
        initial_value = float(self._get_parameter_value(parameter_path, base_reactor, base_operating, base_feed, base_parameters))

        def rmse_for(candidate_value: float) -> float:
            reactor_cfg, operating_cfg, feed_cfg, param_cfg = self._clone_inputs(base_reactor, base_operating, base_feed, base_parameters)
            self._set_parameter_value(parameter_path, float(candidate_value), reactor_cfg, operating_cfg, feed_cfg, param_cfg)
            result = self.simulate(
                reactor_cfg,
                operating_conditions=operating_cfg,
                feed=feed_cfg,
                blend=blend,
                initial_state=base_initial,
                parameters=param_cfg,
                simulation=base_simulation,
            )
            predicted = np.interp(observation_times, result.time_days, result.series["methane_m3_day"])
            return float(math.sqrt(np.mean((predicted - observed_values) ** 2)))

        rmse_before = rmse_for(initial_value)
        optimisation = minimize_scalar(
            rmse_for,
            bounds=(minimum, maximum),
            method="bounded",
            options={"xatol": 1e-3, "maxiter": 25},
        )
        calibrated_value = float(optimisation.x)
        rmse_after = float(optimisation.fun)

        final_reactor, final_operating, final_feed, final_parameters = self._clone_inputs(base_reactor, base_operating, base_feed, base_parameters)
        self._set_parameter_value(parameter_path, calibrated_value, final_reactor, final_operating, final_feed, final_parameters)
        final_result = self.simulate(
            final_reactor,
            operating_conditions=final_operating,
            feed=final_feed,
            blend=blend,
            initial_state=base_initial,
            parameters=final_parameters,
            simulation=default_simulation.model_copy(update={"duration_days": base_simulation.duration_days}, deep=True),
            metadata={"mode": "calibration", "parameter_path": parameter_path},
        )
        return CalibrationResult(
            parameter_path=parameter_path,
            initial_value=initial_value,
            calibrated_value=calibrated_value,
            rmse_before=rmse_before,
            rmse_after=rmse_after,
            simulation_id=final_result.simulation_id,
        )

    def _resolve_reactor(self, reactor: ReactorConfig | str) -> ReactorConfig:
        if isinstance(reactor, ReactorConfig):
            return reactor.model_copy(deep=True)
        return make_default_reactor_config(str(reactor))

    def _simulate_reduced(
        self,
        *,
        reactor: ReactorConfig,
        operating_conditions: OperatingConditions,
        feed: FeedDefinition,
        initial_state: InitialState,
        parameters: KineticParameters,
        simulation: SimulationConfig,
    ) -> tuple[np.ndarray, dict[str, list[float]], dict[str, object]]:
        reactor_model = build_reactor(reactor)
        time_grid = np.linspace(0.0, simulation.duration_days, simulation.evaluation_points)
        if hasattr(reactor_model, "build_batch_initial_vector"):
            initial_vector = reactor_model.build_batch_initial_vector(feed, initial_state)
        else:
            initial_vector = reactor_model.initial_vector(initial_state)
        solution = solve_ivp(
            lambda t, y: reactor_model.rhs(
                t,
                y,
                feed=feed,
                operating_conditions=operating_conditions,
                parameters=parameters,
            ),
            t_span=(0.0, simulation.duration_days),
            y0=initial_vector,
            method=simulation.solver,
            t_eval=time_grid,
            rtol=simulation.rtol,
            atol=simulation.atol,
        )
        if not solution.success:
            raise RuntimeError(f"Simulation failed for {reactor.reactor_type}: {solution.message}")

        state_matrix = np.clip(solution.y.T.astype(float), a_min=0.0, a_max=None)
        if not np.isfinite(state_matrix).all():
            raise RuntimeError("Simulation produced non-finite values")

        profiles = reactor_model.summarize_profiles(
            state_matrix,
            feed=feed,
            operating_conditions=operating_conditions,
            parameters=parameters,
        )
        return time_grid, profiles, {
            "segment_count": reactor_model.segment_count,
            "solver_status": solution.message,
            "final_internal_state": [float(item) for item in state_matrix[-1].tolist()],
        }

    def _build_summary(
        self,
        *,
        time_days: np.ndarray,
        series: dict[str, list[float]],
        metadata: dict[str, object] | None = None,
    ) -> SimulationSummary:
        methane = np.asarray(series["methane_m3_day"], dtype=float)
        biogas = np.asarray(series["biogas_m3_day"], dtype=float)
        final_states = {state_name: float(series[state_name][-1]) for state_name in STATE_NAMES}
        tail_size = max(len(methane) // 10, 5)
        methane_tail = methane[-tail_size:]
        stability_index = float(np.std(methane_tail) / max(np.mean(methane_tail), 1e-9))
        return SimulationSummary(
            methane_final_m3_day=float(methane[-1]),
            methane_peak_m3_day=float(np.max(methane)),
            methane_cumulative_m3=float(np.trapezoid(methane, time_days)),
            biogas_final_m3_day=float(biogas[-1]),
            ch4_fraction_final=float(series["ch4_fraction"][-1]),
            ph_final=float(series["ph"][-1]),
            vfa_final=float(series["vfa_total"][-1]),
            effluent_cod_final=float(series["effluent_cod"][-1]),
            effluent_particulate_final=float(series["particulate_cod"][-1]),
            volatile_solids_proxy=float(series["volatile_solids_proxy"][-1]),
            stability_index=stability_index,
            cn_ratio=float(metadata["cn_ratio"]) if metadata and metadata.get("cn_ratio") is not None else None,
            blend_components=list(metadata["blend_components"]) if metadata and metadata.get("blend_components") else None,
            final_states=final_states,
        )

    def _comparison_entry(self, result: SimulationResult) -> ScenarioComparisonEntry:
        return ScenarioComparisonEntry(
            simulation_id=result.simulation_id,
            reactor_type=result.reactor.reactor_type,
            backend_used=str(result.metadata.get("backend_used", "reduced")),
            methane_final_m3_day=result.summary.methane_final_m3_day,
            methane_cumulative_m3=result.summary.methane_cumulative_m3,
            biogas_final_m3_day=result.summary.biogas_final_m3_day,
            ch4_fraction_final=result.summary.ch4_fraction_final,
            ph_final=result.summary.ph_final,
            vfa_final=result.summary.vfa_final,
            effluent_cod_final=result.summary.effluent_cod_final,
        )

    def _clone_inputs(
        self,
        reactor: ReactorConfig,
        operating: OperatingConditions,
        feed: FeedDefinition,
        parameters: KineticParameters,
    ) -> tuple[ReactorConfig, OperatingConditions, FeedDefinition, KineticParameters]:
        return (
            reactor.model_copy(deep=True),
            operating.model_copy(deep=True),
            feed.model_copy(deep=True),
            parameters.model_copy(deep=True),
        )

    def _get_parameter_value(
        self,
        parameter_path: str,
        reactor: ReactorConfig,
        operating: OperatingConditions,
        feed: FeedDefinition,
        parameters: KineticParameters,
    ) -> float:
        target, attribute = self._resolve_target(parameter_path, reactor, operating, feed, parameters)
        return float(getattr(target, attribute))

    def _set_parameter_value(
        self,
        parameter_path: str,
        value: float,
        reactor: ReactorConfig,
        operating: OperatingConditions,
        feed: FeedDefinition,
        parameters: KineticParameters,
    ) -> None:
        target, attribute = self._resolve_target(parameter_path, reactor, operating, feed, parameters)
        setattr(target, attribute, float(value))

    def _resolve_target(
        self,
        parameter_path: str,
        reactor: ReactorConfig,
        operating: OperatingConditions,
        feed: FeedDefinition,
        parameters: KineticParameters,
    ) -> tuple[object, str]:
        if "." not in parameter_path:
            raise ValueError("parameter_path must look like 'kinetics.k_hyd' or 'feed.alkalinity'")
        root, remainder = parameter_path.split(".", 1)
        targets = {
            "reactor": reactor,
            "operating": operating,
            "feed": feed,
            "kinetics": parameters,
            "parameters": parameters,
        }
        if root not in targets:
            raise ValueError(f"Unsupported parameter group: {root}")
        target = targets[root]
        parts = remainder.split(".")
        for part in parts[:-1]:
            if not hasattr(target, part):
                raise ValueError(f"Unknown parameter path '{parameter_path}'")
            target = getattr(target, part)
        attribute = parts[-1]
        if not hasattr(target, attribute):
            raise ValueError(f"Unknown parameter path '{parameter_path}'")
        return target, attribute

    def _new_simulation_id(self, reactor_type: str) -> str:
        timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
        return f"{reactor_type}-{timestamp}-{uuid4().hex[:8]}"

    def _validate_objective(self, objective: str) -> None:
        if objective not in OBJECTIVE_NAMES:
            raise ValueError(f"Unsupported objective '{objective}'. Expected one of: {', '.join(OBJECTIVE_NAMES)}")

    def _objective_value(self, summary: SimulationSummary, objective: str) -> float:
        return float(getattr(summary, objective))

    def _resolve_backend(self, reactor: ReactorConfig, simulation: SimulationConfig) -> _ResolvedBackend:
        requested = simulation.backend
        reduced_only_reactors = {"two_phase", "tpad", "batch", "uasb", "plug_flow"}
        if requested == "reduced":
            return _ResolvedBackend(requested=requested, used="reduced")
        if requested == "pyadm1":
            if reactor.reactor_type != "cstr":
                return _ResolvedBackend(
                    requested=requested,
                    used="reduced",
                    fallback_reason=f"PyADM1 nao suporta {reactor.reactor_type}; usando reduced.",
                )
            return _ResolvedBackend(requested=requested, used="pyadm1")
        if requested == "full":
            if reactor.reactor_type != "cstr":
                return _ResolvedBackend(
                    requested=requested,
                    used="reduced",
                    fallback_reason=f"ADM1 full nativo suporta apenas cstr nesta fase; usando reduced para {reactor.reactor_type}.",
                )
            return _ResolvedBackend(requested=requested, used="full")
        if requested == "auto":
            if reactor.reactor_type == "cstr":
                return _ResolvedBackend(requested=requested, used="pyadm1")
            if reactor.reactor_type in reduced_only_reactors:
                return _ResolvedBackend(
                    requested=requested,
                    used="reduced",
                    fallback_reason=f"Auto backend mantem o modelo reduced para {reactor.reactor_type}.",
                )
        raise ValueError(f"Unsupported backend '{requested}'")

    def _tail_convergence_metric(self, result: SimulationResult) -> float:
        tail_size = max(min(len(result.time_days) // 8, 25), 5)
        if len(result.time_days) < 2:
            return float("inf")
        time_tail = np.asarray(result.time_days[-tail_size:], dtype=float)
        state_tail = np.asarray([result.series[state_name][-tail_size:] for state_name in STATE_NAMES], dtype=float)
        delta_time = np.maximum(np.diff(time_tail), 1e-9)
        delta_state = np.abs(np.diff(state_tail, axis=1))
        scale = np.maximum(np.abs(state_tail[:, :-1]), 1e-6)
        return float(np.max((delta_state / scale) / delta_time[None, :]))






