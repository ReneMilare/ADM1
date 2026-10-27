from __future__ import annotations

import importlib
import importlib.util
import json
import platform
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import streamlit as st

from simulator.paths import _safe_project_path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@st.cache_data(ttl=30, show_spinner=False)
def collect_health_snapshot() -> dict[str, Any]:
    dependencies = _check_dependencies()
    services = _check_services()
    latest_reports = {
        "validation": load_latest_report(PROJECT_ROOT / "simulator" / "validation_runs", "phase3_validation.json"),
        "literature": load_latest_report(PROJECT_ROOT / "simulator" / "literature_validation_runs", "literature_validation.json"),
    }
    artifacts = _collect_artifacts(PROJECT_ROOT)
    issues = _build_issues(dependencies, services)
    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "backend_policy": "full default with explicit reduced fallback for uasb and plug_flow.",
        "dependencies": dependencies,
        "services": services,
        "artifacts": artifacts,
        "issues": issues,
        "latest_reports": latest_reports,
        "summary": {
            "critical_issues": sum(1 for issue in issues if issue["severity"] == "error"),
            "warning_issues": sum(1 for issue in issues if issue["severity"] == "warning"),
            "required_dependencies_ok": sum(1 for item in dependencies if item["required"] and item["status"] == "ok"),
            "required_dependencies_total": sum(1 for item in dependencies if item["required"]),
            "services_ok": sum(1 for item in services if item["status"] == "ok"),
            "services_total": len(services),
        },
    }


def list_recent_simulations(limit: int = 8) -> list[dict[str, Any]]:
    runs_dir = PROJECT_ROOT / "simulator" / "runs"
    if not runs_dir.exists():
        return []
    entries: list[dict[str, Any]] = []
    for path in sorted(runs_dir.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)[:limit]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            payload = {}
        entries.append(
            {
                "simulation_id": payload.get("simulation_id", path.stem),
                "reactor": payload.get("reactor", {}).get("reactor_type"),
                "backend_used": payload.get("metadata", {}).get("backend_used"),
                "created_at": payload.get("created_at"),
                "path": _safe_project_path(path),
            }
        )
    return entries


def load_latest_report(root: Path, filename: str) -> dict[str, Any] | None:
    if not root.exists():
        return None
    for candidate in sorted((path for path in root.iterdir() if path.is_dir()), reverse=True):
        report_path = candidate / filename
        if not report_path.exists():
            continue
        try:
            payload = json.loads(report_path.read_text(encoding="utf-8"))
        except Exception as exc:
            return {
                "path": _safe_project_path(report_path),
                "available": False,
                "error": f"{type(exc).__name__}: unable to read report",
                "data": None,
            }
        return {
            "path": _safe_project_path(report_path),
            "available": True,
            "error": None,
            "data": payload,
        }
    return None


def _check_dependencies() -> list[dict[str, Any]]:
    dependency_specs = [
        ("streamlit", True),
        ("numpy", True),
        ("pandas", True),
        ("plotly", True),
        ("pydantic", True),
        ("OMPython", False),
    ]
    results: list[dict[str, Any]] = []
    for module_name, required in dependency_specs:
        spec = importlib.util.find_spec(module_name)
        if spec is None:
            results.append(
                {
                    "name": module_name,
                    "required": required,
                    "status": "error" if required else "warning",
                    "detail": "Module not installed in the local Python environment.",
                }
            )
            continue
        try:
            module = importlib.import_module(module_name)
            version = getattr(module, "__version__", "installed")
            detail = f"Installed ({version})."
        except Exception as exc:
            detail = f"Installed but failed to import cleanly: {exc}"
        results.append(
            {
                "name": module_name,
                "required": required,
                "status": "ok",
                "detail": detail,
            }
        )
    omc_path = shutil.which("omc")
    results.append(
        {
            "name": "OpenModelica CLI",
            "required": False,
            "status": "ok" if omc_path else "warning",
            "detail": "Executable available on PATH." if omc_path else "Executable not found on PATH.",
        }
    )
    return results


def _check_services() -> list[dict[str, Any]]:
    service_specs = [
        ("Simulation service", "simulator.service", "ADM1SimulationService"),
        ("Design pipeline", "simulator.design_pipeline", "ADM1DesignPipeline"),
        ("Phase 3 validation", "simulator.validation", "run_phase3_validation"),
        ("Literature validation", "simulator.literature_validation", "run_literature_validation"),
    ]
    results: list[dict[str, Any]] = []
    for label, module_name, symbol_name in service_specs:
        try:
            module = importlib.import_module(module_name)
            getattr(module, symbol_name)
        except Exception as exc:
            results.append(
                {
                    "name": label,
                    "status": "error",
                    "detail": f"{module_name}.{symbol_name} unavailable: {exc}",
                }
            )
            continue
        results.append(
            {
                "name": label,
                "status": "ok",
                "detail": f"{module_name}.{symbol_name} imported successfully.",
            }
        )
    return results


def _collect_artifacts(root: Path) -> dict[str, Any]:
    scenario_dir = root / "simulator" / "runs"
    benchmark_dir = root / "simulator" / "benchmarks"
    validation_dir = root / "simulator" / "validation_runs"
    literature_dir = root / "simulator" / "literature_validation_runs"
    return {
        "saved_scenario_count": len(list(scenario_dir.glob("*.json"))) if scenario_dir.exists() else 0,
        "benchmark_run_count": len([path for path in benchmark_dir.iterdir() if path.is_dir()]) if benchmark_dir.exists() else 0,
        "validation_run_count": len([path for path in validation_dir.iterdir() if path.is_dir()]) if validation_dir.exists() else 0,
        "literature_validation_count": len([path for path in literature_dir.iterdir() if path.is_dir()]) if literature_dir.exists() else 0,
    }


def _build_issues(
    dependencies: list[dict[str, Any]],
    services: list[dict[str, Any]],
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    for item in dependencies:
        if item["required"] and item["status"] != "ok":
            issues.append({"severity": "error", "message": f"Required dependency missing: {item['name']}. {item['detail']}"})
    for item in services:
        if item["status"] != "ok":
            issues.append({"severity": "error", "message": f"Service unavailable: {item['name']}. {item['detail']}"})
    vendor_path = PROJECT_ROOT / "vendor" / "PyADM1"
    if not vendor_path.exists():
        issues.append({"severity": "error", "message": "The original PyADM1 code was not found in vendor/PyADM1."})
    return issues
