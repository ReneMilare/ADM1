from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from simulator.core.models import FeedDefinition, OperatingConditions, SimulationConfig
from simulator.service import ADM1SimulationService
from simulator.paths import _safe_project_path

SUMMARY_FIELDS = [
    "methane_final_m3_day",
    "methane_cumulative_m3",
    "biogas_final_m3_day",
    "ch4_fraction_final",
    "ph_final",
    "vfa_final",
    "effluent_cod_final",
    "volatile_solids_proxy",
    "stability_index",
]
SERIES_FIELDS = ["methane_m3_day", "biogas_m3_day", "ph", "vfa_total", "effluent_cod"]
DEFAULT_DURATION_DAYS = 30.0
DEFAULT_EVALUATION_POINTS = 121
DEFAULT_OUTPUT_ROOT = Path(__file__).resolve().parent / "benchmarks"


@dataclass(frozen=True)
class ScenarioSpec:
    name: str
    description: str
    operating_conditions: OperatingConditions
    feed: FeedDefinition
    duration_days: float = DEFAULT_DURATION_DAYS
    evaluation_points: int = DEFAULT_EVALUATION_POINTS


@dataclass(frozen=True)
class BackendRun:
    backend: str
    runtime_seconds: float
    summary: dict[str, float]
    series: dict[str, list[float]]
    metadata: dict[str, Any]


def build_default_scenarios() -> list[ScenarioSpec]:
    return [
        ScenarioSpec(
            name="baseline_bsm2_like",
            description="Carga e operacao proximas do baseline atual do projeto.",
            operating_conditions=OperatingConditions(volume_m3=3000.0, temperature_c=35.0, hrt_days=20.0),
            feed=FeedDefinition(
                name="baseline_bsm2_like",
                particulate_cod=14.0,
                soluble_cod=5.5,
                acetate=0.6,
                propionate=0.25,
                hydrogen=0.001,
                inorganic_nitrogen=1.3,
                alkalinity=4.8,
                ph=7.1,
            ),
        ),
        ScenarioSpec(
            name="higher_loading_short_hrt",
            description="Maior carga organica com HRT menor para estressar a resposta dinamica.",
            operating_conditions=OperatingConditions(volume_m3=3000.0, temperature_c=35.0, hrt_days=14.0),
            feed=FeedDefinition(
                name="higher_loading_short_hrt",
                particulate_cod=16.5,
                soluble_cod=6.4,
                acetate=0.9,
                propionate=0.35,
                hydrogen=0.0012,
                inorganic_nitrogen=1.45,
                alkalinity=4.9,
                ph=7.05,
            ),
        ),
        ScenarioSpec(
            name="cooler_buffered_digester",
            description="Digester mais frio e com HRT maior, com buffer alcalino mais alto.",
            operating_conditions=OperatingConditions(volume_m3=3000.0, temperature_c=32.0, hrt_days=24.0),
            feed=FeedDefinition(
                name="cooler_buffered_digester",
                particulate_cod=13.0,
                soluble_cod=4.8,
                acetate=0.55,
                propionate=0.22,
                hydrogen=0.001,
                inorganic_nitrogen=1.25,
                alkalinity=5.3,
                ph=7.2,
            ),
        ),
        ScenarioSpec(
            name="vfa_rich_feed",
            description="Alimentacao mais rica em AGVs para comparar sensibilidade de pH e VFA.",
            operating_conditions=OperatingConditions(volume_m3=3000.0, temperature_c=35.0, hrt_days=18.0),
            feed=FeedDefinition(
                name="vfa_rich_feed",
                particulate_cod=12.2,
                soluble_cod=6.0,
                acetate=1.1,
                propionate=0.55,
                hydrogen=0.0015,
                inorganic_nitrogen=1.35,
                alkalinity=4.5,
                ph=6.95,
            ),
        ),
    ]


def run_benchmark(output_root: Path | None = None) -> tuple[dict[str, Any], Path]:
    service = ADM1SimulationService()
    scenarios = build_default_scenarios()
    if output_root is None:
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        output_dir = DEFAULT_OUTPUT_ROOT / timestamp
        output_dir.mkdir(parents=True, exist_ok=False)
    else:
        output_dir = output_root
        output_dir.mkdir(parents=True, exist_ok=True)

    scenario_reports: list[dict[str, Any]] = []
    for scenario in scenarios:
        scenario_reports.append(_run_scenario(service, scenario))

    report = _build_report(scenario_reports)
    (output_dir / "backend_benchmark.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "backend_benchmark.md").write_text(_render_markdown(report), encoding="utf-8")
    return report, output_dir


def _run_scenario(service: ADM1SimulationService, scenario: ScenarioSpec) -> dict[str, Any]:
    backend_runs: dict[str, dict[str, Any]] = {}
    for backend in ("reduced", "pyadm1"):
        simulation = SimulationConfig(
            duration_days=scenario.duration_days,
            evaluation_points=scenario.evaluation_points,
            backend=backend,
            persist=False,
        )
        start = time.perf_counter()
        result = service.simulate(
            "cstr",
            operating_conditions=scenario.operating_conditions,
            feed=scenario.feed,
            simulation=simulation,
        )
        runtime_seconds = time.perf_counter() - start
        backend_runs[backend] = {
            "backend": backend,
            "backend_used": result.metadata.get("backend_used"),
            "runtime_seconds": runtime_seconds,
            "summary": {field: float(getattr(result.summary, field)) for field in SUMMARY_FIELDS},
            "series": {field: [float(item) for item in result.series[field]] for field in SERIES_FIELDS},
            "metadata": {
                "solver_status": result.metadata.get("solver_status"),
                "backend_requested": result.metadata.get("backend_requested"),
                "backend_used": result.metadata.get("backend_used"),
            },
        }

    reduced_run = backend_runs["reduced"]
    pyadm1_run = backend_runs["pyadm1"]
    return {
        "name": scenario.name,
        "description": scenario.description,
        "operating_conditions": scenario.operating_conditions.model_dump(),
        "feed": scenario.feed.model_dump(),
        "simulation": {
            "duration_days": scenario.duration_days,
            "evaluation_points": scenario.evaluation_points,
        },
        "runs": backend_runs,
        "summary_comparison": _compare_summary(reduced_run["summary"], pyadm1_run["summary"]),
        "series_comparison": _compare_series(reduced_run["series"], pyadm1_run["series"]),
    }


def _compare_summary(reduced: dict[str, float], pyadm1: dict[str, float]) -> dict[str, dict[str, float]]:
    comparison: dict[str, dict[str, float]] = {}
    for field in SUMMARY_FIELDS:
        reduced_value = float(reduced[field])
        pyadm1_value = float(pyadm1[field])
        delta = pyadm1_value - reduced_value
        baseline = max(abs(pyadm1_value), 1e-9)
        comparison[field] = {
            "reduced": reduced_value,
            "pyadm1": pyadm1_value,
            "delta": delta,
            "abs_delta": abs(delta),
            "rel_delta_pct_vs_pyadm1": abs(delta) / baseline * 100.0,
        }
    return comparison


def _compare_series(reduced: dict[str, list[float]], pyadm1: dict[str, list[float]]) -> dict[str, dict[str, float]]:
    comparison: dict[str, dict[str, float]] = {}
    for field in SERIES_FIELDS:
        reduced_values = np.asarray(reduced[field], dtype=float)
        pyadm1_values = np.asarray(pyadm1[field], dtype=float)
        diff = pyadm1_values - reduced_values
        rmse = float(np.sqrt(np.mean(diff**2)))
        mae = float(np.mean(np.abs(diff)))
        final_delta = float(diff[-1])
        scale = max(float(np.max(np.abs(pyadm1_values))), float(np.ptp(pyadm1_values)), 1e-9)
        comparison[field] = {
            "rmse": rmse,
            "mae": mae,
            "final_delta": final_delta,
            "final_rel_pct_vs_pyadm1": abs(final_delta) / max(abs(float(pyadm1_values[-1])), 1e-9) * 100.0,
            "nrmse_pct": rmse / scale * 100.0,
        }
    return comparison


def _build_report(scenarios: list[dict[str, Any]]) -> dict[str, Any]:
    runtime_by_backend = {
        backend: [float(scenario["runs"][backend]["runtime_seconds"]) for scenario in scenarios]
        for backend in ("reduced", "pyadm1")
    }
    aggregate_summary = {
        field: {
            "mean_rel_delta_pct_vs_pyadm1": float(np.mean([scenario["summary_comparison"][field]["rel_delta_pct_vs_pyadm1"] for scenario in scenarios])),
            "max_rel_delta_pct_vs_pyadm1": float(np.max([scenario["summary_comparison"][field]["rel_delta_pct_vs_pyadm1"] for scenario in scenarios])),
        }
        for field in SUMMARY_FIELDS
    }
    aggregate_series = {
        field: {
            "mean_nrmse_pct": float(np.mean([scenario["series_comparison"][field]["nrmse_pct"] for scenario in scenarios])),
            "max_nrmse_pct": float(np.max([scenario["series_comparison"][field]["nrmse_pct"] for scenario in scenarios])),
        }
        for field in SERIES_FIELDS
    }
    recommendation = _recommendation(aggregate_summary, aggregate_series)
    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "reactor_type": "cstr",
        "backends": ["reduced", "pyadm1"],
        "scenario_count": len(scenarios),
        "scenarios": scenarios,
        "aggregate": {
            "runtime_seconds": {
                backend: {
                    "mean": float(np.mean(values)),
                    "max": float(np.max(values)),
                    "min": float(np.min(values)),
                }
                for backend, values in runtime_by_backend.items()
            },
            "summary_metrics": aggregate_summary,
            "series_metrics": aggregate_series,
            "recommendation": recommendation,
        },
    }


def _recommendation(aggregate_summary: dict[str, dict[str, float]], aggregate_series: dict[str, dict[str, float]]) -> dict[str, Any]:
    methane_delta = aggregate_summary["methane_final_m3_day"]["mean_rel_delta_pct_vs_pyadm1"]
    ph_delta = aggregate_summary["ph_final"]["mean_rel_delta_pct_vs_pyadm1"]
    methane_nrmse = aggregate_series["methane_m3_day"]["mean_nrmse_pct"]
    backends_interchangeable = methane_delta <= 15.0 and ph_delta <= 3.0 and methane_nrmse <= 20.0
    prefer_pyadm1_for_cstr_fidelity = not backends_interchangeable
    promote_pyadm1_as_global_default = not backends_interchangeable
    if backends_interchangeable:
        rationale = "Backends proximos nesta amostra; manter o backend atual continua aceitavel para operacao rotineira."
    else:
        rationale = "Backends nao sao intercambiaveis numericamente. A politica operacional passa a usar pyadm1 como backend padrao, com fallback para reduced em reatores ainda nao suportados pelo original."
    return {
        "backends_interchangeable": backends_interchangeable,
        "prefer_pyadm1_for_cstr_fidelity": prefer_pyadm1_for_cstr_fidelity,
        "promote_pyadm1_as_global_default": promote_pyadm1_as_global_default,
        "rationale": rationale,
        "thresholds": {
            "methane_final_mean_rel_delta_pct_max": 15.0,
            "ph_final_mean_rel_delta_pct_max": 3.0,
            "methane_series_mean_nrmse_pct_max": 20.0,
        },
    }


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Benchmark Reduced vs PyADM1",
        "",
        f"- Gerado em: `{report['generated_at']}`",
        f"- Reator avaliado: `{report['reactor_type']}`",
        f"- Cenarios: `{report['scenario_count']}`",
        f"- Recomendacao automatica: `{report['aggregate']['recommendation']['rationale']}`",
        "",
        "## Runtime medio",
        "",
        "| Backend | Mean (s) | Min (s) | Max (s) |",
        "| --- | ---: | ---: | ---: |",
    ]
    for backend, stats in report["aggregate"]["runtime_seconds"].items():
        lines.append(f"| {backend} | {stats['mean']:.3f} | {stats['min']:.3f} | {stats['max']:.3f} |")
    lines.extend(["", "## Delta medio das metricas principais", "", "| Metrica | Mean rel delta vs PyADM1 (%) | Max rel delta vs PyADM1 (%) |", "| --- | ---: | ---: |"])
    for field in SUMMARY_FIELDS:
        stats = report["aggregate"]["summary_metrics"][field]
        lines.append(f"| {field} | {stats['mean_rel_delta_pct_vs_pyadm1']:.2f} | {stats['max_rel_delta_pct_vs_pyadm1']:.2f} |")
    lines.extend(["", "## NRMSE medio das series", "", "| Serie | Mean NRMSE (%) | Max NRMSE (%) |", "| --- | ---: | ---: |"])
    for field in SERIES_FIELDS:
        stats = report["aggregate"]["series_metrics"][field]
        lines.append(f"| {field} | {stats['mean_nrmse_pct']:.2f} | {stats['max_nrmse_pct']:.2f} |")
    lines.append("")
    lines.append("## Cenarios")
    lines.append("")
    for scenario in report["scenarios"]:
        lines.append(f"### {scenario['name']}")
        lines.append("")
        lines.append(f"{scenario['description']}")
        lines.append("")
        lines.append("| Metrica | Reduced | PyADM1 | Delta | Rel delta vs PyADM1 (%) |")
        lines.append("| --- | ---: | ---: | ---: | ---: |")
        for field in ("methane_final_m3_day", "biogas_final_m3_day", "ph_final", "vfa_final", "effluent_cod_final"):
            metric = scenario["summary_comparison"][field]
            lines.append(
                f"| {field} | {metric['reduced']:.3f} | {metric['pyadm1']:.3f} | {metric['delta']:.3f} | {metric['rel_delta_pct_vs_pyadm1']:.2f} |"
            )
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a reproducible benchmark between the reduced backend and the integrated original PyADM1 backend.")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    args = parser.parse_args()
    report, output_dir = run_benchmark(output_root=args.output_root)
    summary = {
        "output_dir": _safe_project_path(output_dir),
        "scenario_count": report["scenario_count"],
        "runtime_mean_seconds": {
            backend: round(stats["mean"], 4) for backend, stats in report["aggregate"]["runtime_seconds"].items()
        },
        "methane_final_mean_rel_delta_pct": round(
            report["aggregate"]["summary_metrics"]["methane_final_m3_day"]["mean_rel_delta_pct_vs_pyadm1"], 3
        ),
        "ph_final_mean_rel_delta_pct": round(
            report["aggregate"]["summary_metrics"]["ph_final"]["mean_rel_delta_pct_vs_pyadm1"], 3
        ),
        "recommendation": report["aggregate"]["recommendation"]["rationale"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

