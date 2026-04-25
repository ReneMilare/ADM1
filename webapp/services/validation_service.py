from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from simulator.literature_validation import run_literature_validation
from simulator.validation import detect_openmodelica_environment, run_phase3_validation
from webapp.services.health import load_latest_report

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PHASE3_ROOT = PROJECT_ROOT / "simulator" / "validation_runs"
LITERATURE_ROOT = PROJECT_ROOT / "simulator" / "literature_validation_runs"


def get_openmodelica_status() -> dict[str, Any]:
    return detect_openmodelica_environment()


def run_phase3_workflow(*, include_openmodelica: bool) -> dict[str, Any]:
    report, output_dir = run_phase3_validation(include_openmodelica=include_openmodelica)
    json_path = output_dir / "phase3_validation.json"
    md_path = output_dir / "phase3_validation.md"
    return {
        "report": report,
        "output_dir": str(output_dir),
        "json_path": str(json_path),
        "markdown_path": str(md_path),
    }


def run_literature_workflow() -> dict[str, Any]:
    report, output_dir = run_literature_validation()
    json_path = output_dir / "literature_validation.json"
    md_path = output_dir / "literature_validation.md"
    return {
        "report": report,
        "output_dir": str(output_dir),
        "json_path": str(json_path),
        "markdown_path": str(md_path),
    }


def load_latest_phase3_bundle() -> dict[str, Any] | None:
    latest = load_latest_report(PHASE3_ROOT, "phase3_validation.json")
    return _bundle_from_latest(latest, markdown_name="phase3_validation.md")


def load_latest_literature_bundle() -> dict[str, Any] | None:
    latest = load_latest_report(LITERATURE_ROOT, "literature_validation.json")
    return _bundle_from_latest(latest, markdown_name="literature_validation.md")


def phase3_runtime_frame(report: dict[str, Any]) -> pd.DataFrame:
    runtime = report["benchmark"]["runtime_seconds"]
    rows = []
    for backend, metrics in runtime.items():
        rows.append(
            {
                "backend": backend,
                "mean_seconds": round(float(metrics["mean"]), 6),
                "min_seconds": round(float(metrics["min"]), 6),
                "max_seconds": round(float(metrics["max"]), 6),
            }
        )
    return pd.DataFrame(rows)


def phase3_metric_frame(report: dict[str, Any]) -> pd.DataFrame:
    summary_metrics = report["benchmark"]["summary_metrics"]
    series_metrics = report["benchmark"]["series_metrics"]
    rows = []
    for metric_name, metrics in summary_metrics.items():
        rows.append(
            {
                "kind": "summary",
                "metric": metric_name,
                "mean_rel_delta_pct_vs_pyadm1": round(float(metrics["mean_rel_delta_pct_vs_pyadm1"]), 4),
                "max_rel_delta_pct_vs_pyadm1": round(float(metrics["max_rel_delta_pct_vs_pyadm1"]), 4),
            }
        )
    for metric_name, metrics in series_metrics.items():
        rows.append(
            {
                "kind": "series",
                "metric": metric_name,
                "mean_nrmse_pct": round(float(metrics["mean_nrmse_pct"]), 4),
                "max_nrmse_pct": round(float(metrics["max_nrmse_pct"]), 4),
            }
        )
    return pd.DataFrame(rows)


def literature_comparison_frame(report: dict[str, Any], *, backend: str) -> pd.DataFrame:
    rows = []
    payload = report[backend]["comparison"]
    for metric_name, metrics in payload.items():
        rows.append(
            {
                "metric": metric_name,
                "reference": round(float(metrics["reference"]), 9),
                "actual": round(float(metrics["actual"]), 9),
                "abs_delta": round(float(metrics["abs_delta"]), 9),
                "rel_delta_pct": round(float(metrics["rel_delta_pct"]), 6),
                "unit": metrics["unit"],
                "within_tolerance": metrics.get("within_tolerance"),
            }
        )
    return pd.DataFrame(rows)


def phase3_next_steps(report: dict[str, Any]) -> list[str]:
    return [str(item) for item in report["conclusion"].get("next_steps", [])]


def artifact_bytes(path: str | Path | None) -> bytes | None:
    if path is None:
        return None
    candidate = Path(path)
    if not candidate.exists():
        return None
    return candidate.read_bytes()


def markdown_artifact_text(path: str | Path | None) -> str | None:
    if path is None:
        return None
    candidate = Path(path)
    if not candidate.exists():
        return None
    return candidate.read_text(encoding="utf-8")


def _bundle_from_latest(latest: dict[str, Any] | None, *, markdown_name: str) -> dict[str, Any] | None:
    if latest is None:
        return None
    if not latest.get("available"):
        return {
            "report": None,
            "output_dir": None,
            "json_path": latest.get("path"),
            "markdown_path": None,
            "error": latest.get("error"),
        }
    json_path = Path(str(latest["path"]))
    output_dir = json_path.parent
    markdown_path = output_dir / markdown_name
    bundle = {
        "report": latest.get("data"),
        "output_dir": str(output_dir),
        "json_path": str(json_path),
        "markdown_path": str(markdown_path) if markdown_path.exists() else None,
        "error": None,
    }
    return bundle
