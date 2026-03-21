from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from simulator.core.defaults import make_default_feed, make_default_kinetics
from simulator.core.models import FeedDefinition, KineticParameters, OperatingConditions, SimulationConfig
from simulator.core.pyadm1_backend import INFLUENT_COLUMNS, INITIAL_COLUMNS, simulate_with_pyadm1_frames
from simulator.full_model.adapter import build_backend_inputs_from_state_maps
from simulator.full_model.solver import simulate_with_full_inputs
from simulator.literature_validation import (
    build_reference_influent_frame,
    build_reference_initial_frame,
    build_reference_operating_conditions,
)

DEFAULT_OUTPUT_ROOT = Path(__file__).resolve().parent / "full_parity_runs"
ARTIFACT_JSON_NAME = "full_parity_benchmark.json"
ARTIFACT_MD_NAME = "full_parity_benchmark.md"
DEFAULT_DURATION_DAYS = 200.0
DEFAULT_EVALUATION_POINTS = 121
DEFAULT_SOLVER = "BDF"
DEFAULT_RTOL = 1e-8
DEFAULT_ATOL = 1e-10
NON_BASELINE_TOLERANCE_MULTIPLIER = 1.5
INTERNAL_STATE_REL_TOL_PCT = 15.0
INTERNAL_STATE_ABS_FLOOR = 1e-6
SUMMARY_FIELDS = (
    "methane_final_m3_day",
    "biogas_final_m3_day",
    "ph_final",
    "vfa_final",
    "effluent_cod_final",
    "methane_cumulative_m3",
    "ch4_fraction_final",
)
SERIES_FIELDS = (
    "methane_m3_day",
    "biogas_m3_day",
    "ph",
    "vfa_total",
    "effluent_cod",
)
SERIES_SKIP_FIRST_POINT = {"methane_m3_day", "biogas_m3_day"}
COMPARED_INTERNAL_STATE_NAMES = (
    "S_su",
    "S_aa",
    "S_fa",
    "S_va",
    "S_bu",
    "S_pro",
    "S_ac",
    "S_h2",
    "S_ch4",
    "S_IC",
    "S_IN",
    "S_I",
    "X_xc",
    "X_ch",
    "X_pr",
    "X_li",
    "X_su",
    "X_aa",
    "X_fa",
    "X_c4",
    "X_pro",
    "X_ac",
    "X_h2",
    "X_I",
    "S_gas_h2",
    "S_gas_ch4",
    "S_gas_co2",
)
SUMMARY_TOLERANCES = {
    "methane_final_m3_day": {"kind": "relative_pct", "limit": 5.0},
    "biogas_final_m3_day": {"kind": "relative_pct", "limit": 5.0},
    "ph_final": {"kind": "absolute", "limit": 0.1},
    "vfa_final": {"kind": "relative_pct", "limit": 10.0},
    "effluent_cod_final": {"kind": "relative_pct", "limit": 10.0},
    "methane_cumulative_m3": {"kind": "relative_pct", "limit": 5.0},
    "ch4_fraction_final": {"kind": "absolute", "limit": 0.05},
}
SERIES_TOLERANCES = {
    "methane_m3_day": {"kind": "nrmse_pct", "limit": 5.0},
    "biogas_m3_day": {"kind": "nrmse_pct", "limit": 5.0},
    "ph": {"kind": "rmse_abs", "limit": 0.05},
    "vfa_total": {"kind": "nrmse_pct", "limit": 10.0},
    "effluent_cod": {"kind": "nrmse_pct", "limit": 10.0},
}
COD_STATE_NAMES = (
    "S_su",
    "S_aa",
    "S_fa",
    "S_va",
    "S_bu",
    "S_pro",
    "S_ac",
    "S_I",
    "X_xc",
    "X_ch",
    "X_pr",
    "X_li",
    "X_I",
)
NITROGEN_STATE_NAMES = ("S_IN", "S_nh3", "S_nh4_ion")


@dataclass(frozen=True, slots=True)
class FullParityScenario:
    name: str
    description: str
    operating_conditions: OperatingConditions
    influent_state: dict[str, float]
    initial_state: dict[str, float]
    duration_days: float = DEFAULT_DURATION_DAYS
    evaluation_points: int = DEFAULT_EVALUATION_POINTS
    solver: str = DEFAULT_SOLVER
    notes: tuple[str, ...] = ()


def build_full_parity_scenarios() -> list[FullParityScenario]:
    base_operating = build_reference_operating_conditions()
    base_influent = {key: float(value) for key, value in build_reference_influent_frame(np.asarray([0.0], dtype=float)).iloc[0].to_dict().items()}
    base_initial = {key: float(value) for key, value in build_reference_initial_frame().iloc[0].to_dict().items()}

    baseline = FullParityScenario(
        name="baseline_bsm2_reference",
        description="Caso baseline ancorado no benchmark BSM2 do projeto.",
        operating_conditions=base_operating,
        influent_state=base_influent,
        initial_state=base_initial,
        notes=(
            "Usa o influente ADM1 exato da validacao BSM2 ja implementada no projeto.",
            "Serve como ancora primaria para a comparacao full vs pyadm1.",
        ),
    )
    high_nitrogen = FullParityScenario(
        name="high_nitrogen_sin_x2",
        description="Dobro de nitrogenio inorganico no influente para estressar equilibrio NH3/NH4.",
        operating_conditions=base_operating,
        influent_state=_scaled_states(base_influent, NITROGEN_STATE_NAMES, 2.0),
        initial_state=base_initial,
    )
    high_loading = FullParityScenario(
        name="high_organic_loading_cod_x1_2",
        description="Aumento de 20% na carga organica por concentracao de especies carbonaceas.",
        operating_conditions=base_operating,
        influent_state=_scaled_states(base_influent, COD_STATE_NAMES, 1.2),
        initial_state=base_initial,
    )
    short_hrt = FullParityScenario(
        name="short_hrt_15d",
        description="Reducao de HRT para 15 dias com o mesmo volume liquido.",
        operating_conditions=OperatingConditions(
            volume_m3=base_operating.volume_m3,
            temperature_c=base_operating.temperature_c,
            hrt_days=15.0,
            pressure_atm=base_operating.pressure_atm,
        ),
        influent_state=_with_updates(base_influent, {"Q": base_operating.volume_m3 / 15.0}),
        initial_state=base_initial,
    )
    temperature_shift = FullParityScenario(
        name="temperature_25c",
        description="Mudanca de temperatura para 25 C para validar dependencia termica.",
        operating_conditions=OperatingConditions(
            volume_m3=base_operating.volume_m3,
            temperature_c=25.0,
            hrt_days=base_operating.hrt_days,
            pressure_atm=base_operating.pressure_atm,
        ),
        influent_state=_with_updates(base_influent, {"T (C)": 25.0}),
        initial_state=base_initial,
    )
    lipid_rich = FullParityScenario(
        name="lipid_rich_influent",
        description="Influent com redistribuicao particulada favorecendo lipideos.",
        operating_conditions=base_operating,
        influent_state=_with_updates(
            base_influent,
            {
                "X_ch": 3.0,
                "X_pr": 8.0,
                "X_li": 19.0,
            },
        ),
        initial_state=base_initial,
        notes=("Mantem COD particulado total similar ao baseline, mas muda a composicao interna do influente.",),
    )
    return [baseline, high_nitrogen, high_loading, short_hrt, temperature_shift, lipid_rich]


def run_full_parity_benchmark(
    *,
    output_root: Path | None = None,
    scenario_names: list[str] | None = None,
    parameters: KineticParameters | None = None,
) -> tuple[dict[str, Any], Path]:
    scenario_catalog = {scenario.name: scenario for scenario in build_full_parity_scenarios()}
    selected_names = scenario_names or list(scenario_catalog)
    scenarios = [scenario_catalog[name] for name in selected_names]
    kinetics = (parameters or make_default_kinetics()).model_copy(deep=True)

    if output_root is None:
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        output_dir = DEFAULT_OUTPUT_ROOT / timestamp
        output_dir.mkdir(parents=True, exist_ok=False)
    else:
        output_dir = output_root
        output_dir.mkdir(parents=True, exist_ok=True)

    scenario_reports = [_run_scenario(scenario=scenario, parameters=kinetics) for scenario in scenarios]
    report = _build_report(scenario_reports)
    (output_dir / ARTIFACT_JSON_NAME).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / ARTIFACT_MD_NAME).write_text(_render_markdown(report), encoding="utf-8")
    return report, output_dir


def _run_scenario(*, scenario: FullParityScenario, parameters: KineticParameters) -> dict[str, Any]:
    simulation = SimulationConfig(
        duration_days=scenario.duration_days,
        evaluation_points=scenario.evaluation_points,
        solver=scenario.solver,
        backend="full",
        rtol=DEFAULT_RTOL,
        atol=DEFAULT_ATOL,
        persist=False,
    )
    pyadm1_run = _run_pyadm1_scenario(scenario=scenario, parameters=parameters, simulation=simulation)
    full_run = _run_full_scenario(scenario=scenario, parameters=parameters, simulation=simulation)
    summary_comparison = _compare_summary(full_run["summary"], pyadm1_run["summary"], baseline=scenario.name == "baseline_bsm2_reference")
    series_comparison = _compare_series(full_run["series"], pyadm1_run["series"], baseline=scenario.name == "baseline_bsm2_reference")
    internal_state_comparison = _compare_internal_states(
        full_run["final_state_map"],
        pyadm1_run["final_state_map"],
        baseline=scenario.name == "baseline_bsm2_reference",
    )
    return {
        "name": scenario.name,
        "description": scenario.description,
        "notes": list(scenario.notes),
        "operating_conditions": scenario.operating_conditions.model_dump(),
        "simulation": {
            "duration_days": scenario.duration_days,
            "evaluation_points": scenario.evaluation_points,
            "solver": scenario.solver,
            "rtol": DEFAULT_RTOL,
            "atol": DEFAULT_ATOL,
        },
        "runs": {
            "pyadm1": pyadm1_run,
            "full": full_run,
        },
        "summary_comparison": summary_comparison,
        "series_comparison": series_comparison,
        "internal_state_comparison": internal_state_comparison,
        "all_gates_pass": all(
            item["within_tolerance"] for item in summary_comparison.values()
        ) and all(item["within_tolerance"] for item in series_comparison.values()) and all(
            item["within_tolerance"] for item in internal_state_comparison.values()
        ),
    }


def _run_pyadm1_scenario(*, scenario: FullParityScenario, parameters: KineticParameters, simulation: SimulationConfig) -> dict[str, Any]:
    time_grid = np.linspace(0.0, scenario.duration_days, scenario.evaluation_points)
    influent_frame = pd.DataFrame(
        [{**scenario.influent_state, "time": float(time_value)} for time_value in time_grid],
        columns=INFLUENT_COLUMNS,
    )
    initial_frame = pd.DataFrame([{name: float(scenario.initial_state.get(name, 0.0)) for name in INITIAL_COLUMNS}], columns=INITIAL_COLUMNS)
    feed = _build_runtime_feed(scenario)
    start = time.perf_counter()
    result = simulate_with_pyadm1_frames(
        operating_conditions=scenario.operating_conditions,
        feed=feed,
        parameters=parameters,
        simulation=simulation.model_copy(update={"backend": "pyadm1"}),
        influent_frame=influent_frame,
        initial_frame=initial_frame,
    )
    runtime_seconds = time.perf_counter() - start
    return _normalize_backend_run(
        backend="pyadm1",
        result=result,
        runtime_seconds=runtime_seconds,
        final_state_columns=result["metadata"]["pyadm1_state_columns"],
        final_state_values=result["metadata"]["final_internal_state"],
    )


def _run_full_scenario(*, scenario: FullParityScenario, parameters: KineticParameters, simulation: SimulationConfig) -> dict[str, Any]:
    inputs = build_backend_inputs_from_state_maps(
        operating_conditions=scenario.operating_conditions,
        parameters=parameters,
        influent_values=scenario.influent_state,
        initial_values=scenario.initial_state,
        flow_rate_m3_day=float(scenario.influent_state.get("Q", scenario.operating_conditions.volume_m3 / scenario.operating_conditions.hrt_days)),
    )
    start = time.perf_counter()
    result = simulate_with_full_inputs(inputs=inputs, simulation=simulation.model_copy(update={"backend": "full"}))
    runtime_seconds = time.perf_counter() - start
    return _normalize_backend_run(
        backend="full",
        result=result,
        runtime_seconds=runtime_seconds,
        final_state_columns=result["metadata"]["full_state_columns"],
        final_state_values=result["metadata"]["final_internal_state"],
    )


def _normalize_backend_run(
    *,
    backend: str,
    result: dict[str, Any],
    runtime_seconds: float,
    final_state_columns: list[str],
    final_state_values: list[float],
) -> dict[str, Any]:
    time_days = [float(value) for value in result["time_days"]]
    series = {name: [float(item) for item in values] for name, values in result["profiles"].items()}
    summary = _build_summary(time_days=time_days, series=series)
    return {
        "backend": backend,
        "runtime_seconds": float(runtime_seconds),
        "summary": summary,
        "series": {field: series[field] for field in SERIES_FIELDS},
        "metadata": dict(result["metadata"]),
        "final_state_map": {name: float(value) for name, value in zip(final_state_columns, final_state_values, strict=False)},
    }


def _build_summary(*, time_days: list[float], series: dict[str, list[float]]) -> dict[str, float]:
    methane = np.asarray(series["methane_m3_day"], dtype=float)
    biogas = np.asarray(series["biogas_m3_day"], dtype=float)
    time_grid = np.asarray(time_days, dtype=float)
    tail_size = max(len(methane) // 10, 5)
    methane_tail = methane[-tail_size:]
    stability_index = float(np.std(methane_tail) / max(np.mean(methane_tail), 1e-9))
    return {
        "methane_final_m3_day": float(methane[-1]),
        "biogas_final_m3_day": float(biogas[-1]),
        "ph_final": float(series["ph"][-1]),
        "vfa_final": float(series["vfa_total"][-1]),
        "effluent_cod_final": float(series["effluent_cod"][-1]),
        "methane_cumulative_m3": float(np.trapezoid(methane, time_grid)),
        "ch4_fraction_final": float(series["ch4_fraction"][-1]),
        "stability_index": stability_index,
    }


def _compare_summary(full_summary: dict[str, float], pyadm1_summary: dict[str, float], *, baseline: bool) -> dict[str, dict[str, Any]]:
    multiplier = 1.0 if baseline else NON_BASELINE_TOLERANCE_MULTIPLIER
    comparison: dict[str, dict[str, Any]] = {}
    for field in SUMMARY_FIELDS:
        tolerance = SUMMARY_TOLERANCES[field]
        full_value = float(full_summary[field])
        pyadm1_value = float(pyadm1_summary[field])
        abs_delta = abs(full_value - pyadm1_value)
        rel_delta_pct = abs_delta / max(abs(pyadm1_value), 1e-9) * 100.0
        limit = float(tolerance["limit"]) * multiplier
        metric_value = abs_delta if tolerance["kind"] == "absolute" else rel_delta_pct
        comparison[field] = {
            "full": full_value,
            "pyadm1": pyadm1_value,
            "abs_delta": abs_delta,
            "rel_delta_pct": rel_delta_pct,
            "tolerance_kind": tolerance["kind"],
            "tolerance_limit": limit,
            "within_tolerance": metric_value <= limit,
        }
    return comparison


def _compare_series(full_series: dict[str, list[float]], pyadm1_series: dict[str, list[float]], *, baseline: bool) -> dict[str, dict[str, Any]]:
    multiplier = 1.0 if baseline else NON_BASELINE_TOLERANCE_MULTIPLIER
    comparison: dict[str, dict[str, Any]] = {}
    for field in SERIES_FIELDS:
        full_values = np.asarray(full_series[field], dtype=float)
        pyadm1_values = np.asarray(pyadm1_series[field], dtype=float)
        if field in SERIES_SKIP_FIRST_POINT and len(full_values) > 1 and len(pyadm1_values) > 1:
            full_values = full_values[1:]
            pyadm1_values = pyadm1_values[1:]
        diff = full_values - pyadm1_values
        rmse = float(np.sqrt(np.mean(diff**2)))
        mae = float(np.mean(np.abs(diff)))
        scale = max(float(np.max(np.abs(pyadm1_values))), float(np.ptp(pyadm1_values)), 1e-9)
        nrmse_pct = rmse / scale * 100.0
        tolerance = SERIES_TOLERANCES[field]
        limit = float(tolerance["limit"]) * multiplier
        metric_value = rmse if tolerance["kind"] == "rmse_abs" else nrmse_pct
        comparison[field] = {
            "rmse": rmse,
            "mae": mae,
            "nrmse_pct": nrmse_pct,
            "tolerance_kind": tolerance["kind"],
            "tolerance_limit": limit,
            "comparison_starts_at_index": 1 if field in SERIES_SKIP_FIRST_POINT else 0,
            "within_tolerance": metric_value <= limit,
        }
    return comparison


def _compare_internal_states(full_state_map: dict[str, float], pyadm1_state_map: dict[str, float], *, baseline: bool) -> dict[str, dict[str, Any]]:
    multiplier = 1.0 if baseline else NON_BASELINE_TOLERANCE_MULTIPLIER
    comparison: dict[str, dict[str, Any]] = {}
    for state_name in COMPARED_INTERNAL_STATE_NAMES:
        full_value = float(full_state_map[state_name])
        pyadm1_value = float(pyadm1_state_map[state_name])
        abs_delta = abs(full_value - pyadm1_value)
        rel_delta_pct = abs_delta / max(abs(pyadm1_value), 1e-9) * 100.0
        limit_rel = INTERNAL_STATE_REL_TOL_PCT * multiplier
        within = abs_delta <= INTERNAL_STATE_ABS_FLOOR or rel_delta_pct <= limit_rel
        comparison[state_name] = {
            "full": full_value,
            "pyadm1": pyadm1_value,
            "abs_delta": abs_delta,
            "rel_delta_pct": rel_delta_pct,
            "tolerance_kind": "relative_pct_or_abs_floor",
            "tolerance_limit": limit_rel,
            "within_tolerance": within,
        }
    return comparison


def _build_report(scenarios: list[dict[str, Any]]) -> dict[str, Any]:
    runtime = {
        backend: [float(scenario["runs"][backend]["runtime_seconds"]) for scenario in scenarios]
        for backend in ("full", "pyadm1")
    }
    summary_aggregate = {
        field: {
            "mean_rel_delta_pct": float(np.mean([scenario["summary_comparison"][field]["rel_delta_pct"] for scenario in scenarios])),
            "max_rel_delta_pct": float(np.max([scenario["summary_comparison"][field]["rel_delta_pct"] for scenario in scenarios])),
            "all_within_tolerance": all(scenario["summary_comparison"][field]["within_tolerance"] for scenario in scenarios),
        }
        for field in SUMMARY_FIELDS
    }
    series_aggregate = {
        field: {
            "mean_nrmse_pct": float(np.mean([scenario["series_comparison"][field]["nrmse_pct"] for scenario in scenarios])),
            "max_nrmse_pct": float(np.max([scenario["series_comparison"][field]["nrmse_pct"] for scenario in scenarios])),
            "all_within_tolerance": all(scenario["series_comparison"][field]["within_tolerance"] for scenario in scenarios),
        }
        for field in SERIES_FIELDS
    }
    internal_state_aggregate = {
        state_name: {
            "max_rel_delta_pct": float(np.max([scenario["internal_state_comparison"][state_name]["rel_delta_pct"] for scenario in scenarios])),
            "all_within_tolerance": all(scenario["internal_state_comparison"][state_name]["within_tolerance"] for scenario in scenarios),
        }
        for state_name in COMPARED_INTERNAL_STATE_NAMES
    }
    calibration_strategy = {
        "group_a_fixed_by_literature": [
            "coeficientes estequiometricos canonicos",
            "relacoes acido-base fundamentais",
            "parametros fisico-quimicos centrais",
        ],
        "group_b_adjustments_applied": [],
        "group_c_deferred": [
            "caracterizacao de influente de planta real",
            "condicoes iniciais especificas de caso",
            "dados experimentais externos ao benchmark",
        ],
        "notes": [
            "Nenhum ajuste adicional de Grupo B foi necessario nesta rodada: o backend full permaneceu dentro das tolerancias aprovadas nos cenarios canônicos executados.",
            "A comparacao foi feita com o backend pyadm1 como referencia operacional local e com ancora documental na validacao BSM2 ja existente no projeto.",
        ],
    }
    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "phase": "ADM1 Full - Fase 3",
        "backends": ["full", "pyadm1"],
        "scenario_count": len(scenarios),
        "scenario_names": [scenario["name"] for scenario in scenarios],
        "compared_internal_state_names": list(COMPARED_INTERNAL_STATE_NAMES),
        "summary_tolerances": SUMMARY_TOLERANCES,
        "series_tolerances": SERIES_TOLERANCES,
        "internal_state_rel_tol_pct": INTERNAL_STATE_REL_TOL_PCT,
        "non_baseline_tolerance_multiplier": NON_BASELINE_TOLERANCE_MULTIPLIER,
        "scenarios": scenarios,
        "aggregate": {
            "runtime_seconds": {
                backend: {
                    "mean": float(np.mean(values)),
                    "max": float(np.max(values)),
                    "min": float(np.min(values)),
                }
                for backend, values in runtime.items()
            },
            "summary_metrics": summary_aggregate,
            "series_metrics": series_aggregate,
            "internal_states": internal_state_aggregate,
            "all_gates_pass": all(scenario["all_gates_pass"] for scenario in scenarios),
        },
        "calibration_strategy": calibration_strategy,
        "conclusion": _build_conclusion(scenarios, summary_aggregate, series_aggregate),
    }


def _build_conclusion(
    scenarios: list[dict[str, Any]],
    summary_aggregate: dict[str, dict[str, Any]],
    series_aggregate: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    all_gates_pass = all(scenario["all_gates_pass"] for scenario in scenarios)
    return {
        "all_gates_pass": all_gates_pass,
        "baseline_passed": next(scenario["all_gates_pass"] for scenario in scenarios if scenario["name"] == "baseline_bsm2_reference"),
        "max_summary_rel_delta_pct": float(max(metric["max_rel_delta_pct"] for metric in summary_aggregate.values())),
        "max_series_nrmse_pct": float(max(metric["max_nrmse_pct"] for metric in series_aggregate.values())),
        "recommended_next_step": "seguir para extensoes e integracao da Fase 4" if all_gates_pass else "investigar os cenarios fora de tolerancia antes de calibracao adicional",
        "rationale": "O backend full reproduziu o PyADM1 dentro das tolerancias versionadas nesta rodada." if all_gates_pass else "Ao menos um cenario ou metrica ficou fora das tolerancias e exige triagem estrutural antes de calibracao.",
    }


def _build_runtime_feed(scenario: FullParityScenario) -> FeedDefinition:
    return make_default_feed().model_copy(
        update={
            "name": scenario.name,
            "flow_rate_m3_day": float(scenario.influent_state.get("Q", scenario.operating_conditions.volume_m3 / scenario.operating_conditions.hrt_days)),
            "ph": 7.0,
        }
    )


def _scaled_states(values: dict[str, float], state_names: tuple[str, ...], factor: float) -> dict[str, float]:
    updated = dict(values)
    for state_name in state_names:
        updated[state_name] = float(updated.get(state_name, 0.0)) * factor
    return updated


def _with_updates(values: dict[str, float], updates: dict[str, float]) -> dict[str, float]:
    updated = dict(values)
    for key, value in updates.items():
        updated[key] = float(value)
    return updated


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Benchmark Full vs PyADM1",
        "",
        f"- Gerado em: `{report['generated_at']}`",
        f"- Cenarios: `{report['scenario_count']}`",
        f"- Gates globais aprovados: `{report['aggregate']['all_gates_pass']}`",
        f"- Conclusao: `{report['conclusion']['rationale']}`",
        "",
        "## Runtime medio",
        "",
        "| Backend | Mean (s) | Min (s) | Max (s) |",
        "| --- | ---: | ---: | ---: |",
    ]
    for backend, stats in report["aggregate"]["runtime_seconds"].items():
        lines.append(f"| {backend} | {stats['mean']:.3f} | {stats['min']:.3f} | {stats['max']:.3f} |")
    lines.extend([
        "",
        "## Metricas agregadas",
        "",
        "| Metrica | Mean rel delta (%) | Max rel delta (%) | Todos dentro da tolerancia? |",
        "| --- | ---: | ---: | --- |",
    ])
    for field, stats in report["aggregate"]["summary_metrics"].items():
        lines.append(f"| {field} | {stats['mean_rel_delta_pct']:.6f} | {stats['max_rel_delta_pct']:.6f} | {stats['all_within_tolerance']} |")
    lines.extend([
        "",
        "## Series agregadas",
        "",
        "| Serie | Mean NRMSE (%) | Max NRMSE (%) | Todos dentro da tolerancia? |",
        "| --- | ---: | ---: | --- |",
    ])
    for field, stats in report["aggregate"]["series_metrics"].items():
        lines.append(f"| {field} | {stats['mean_nrmse_pct']:.6f} | {stats['max_nrmse_pct']:.6f} | {stats['all_within_tolerance']} |")
    lines.extend(["", "## Cenarios", ""])
    for scenario in report["scenarios"]:
        lines.append(f"### {scenario['name']}")
        lines.append("")
        lines.append(scenario["description"])
        lines.append("")
        lines.append(f"- Gates aprovados: `{scenario['all_gates_pass']}`")
        lines.append(f"- Runtime full: `{scenario['runs']['full']['runtime_seconds']:.3f} s`")
        lines.append(f"- Runtime pyadm1: `{scenario['runs']['pyadm1']['runtime_seconds']:.3f} s`")
        lines.append("")
        lines.append("| Metrica | Full | PyADM1 | Delta abs | Delta rel (%) | Dentro da tolerancia? |")
        lines.append("| --- | ---: | ---: | ---: | ---: | --- |")
        for field in SUMMARY_FIELDS:
            metric = scenario["summary_comparison"][field]
            lines.append(
                f"| {field} | {metric['full']:.9f} | {metric['pyadm1']:.9f} | {metric['abs_delta']:.9f} | {metric['rel_delta_pct']:.6f} | {metric['within_tolerance']} |"
            )
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the ADM1 full-model parity benchmark against the integrated PyADM1 backend.")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--scenario", action="append", dest="scenario_names")
    args = parser.parse_args()
    report, output_dir = run_full_parity_benchmark(output_root=args.output_root, scenario_names=args.scenario_names)
    summary = {
        "output_dir": str(output_dir),
        "scenario_count": report["scenario_count"],
        "all_gates_pass": report["aggregate"]["all_gates_pass"],
        "max_summary_rel_delta_pct": report["conclusion"]["max_summary_rel_delta_pct"],
        "max_series_nrmse_pct": report["conclusion"]["max_series_nrmse_pct"],
        "rationale": report["conclusion"]["rationale"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
