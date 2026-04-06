from __future__ import annotations

import importlib
import importlib.util
import json
import platform
import shutil
import sys
from urllib import error, request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import streamlit as st

from rag.settings import DEFAULT_EMBED_MODEL, DEFAULT_OLLAMA_HOST, get_paths

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@st.cache_data(ttl=30, show_spinner=False)
def collect_health_snapshot() -> dict[str, Any]:
    paths = get_paths()
    dependencies = _check_dependencies()
    services = _check_services()
    rag_runtime = _check_rag_runtime()
    path_checks = _check_paths(paths)
    latest_reports = {
        "validation": load_latest_report(PROJECT_ROOT / "simulator" / "validation_runs", "phase3_validation.json"),
        "literature": load_latest_report(PROJECT_ROOT / "simulator" / "literature_validation_runs", "literature_validation.json"),
    }
    rag_sources = load_rag_sources(paths.extracted / "manifest.json")
    artifacts = _collect_artifacts(paths.root, rag_sources)
    issues = _build_issues(dependencies, services, rag_runtime, path_checks, artifacts)
    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "project_root": str(paths.root),
        "backend_policy": "full default with explicit reduced fallback for uasb and plug_flow.",
        "dependencies": dependencies,
        "services": services,
        "rag_runtime": rag_runtime,
        "paths": path_checks,
        "artifacts": artifacts,
        "issues": issues,
        "latest_reports": latest_reports,
        "rag_sources": rag_sources[:10],
        "summary": {
            "critical_issues": sum(1 for issue in issues if issue["severity"] == "error"),
            "warning_issues": sum(1 for issue in issues if issue["severity"] == "warning"),
            "required_dependencies_ok": sum(1 for item in dependencies if item["required"] and item["status"] == "ok"),
            "required_dependencies_total": sum(1 for item in dependencies if item["required"]),
            "services_ok": sum(1 for item in services if item["status"] == "ok"),
            "services_total": len(services),
            "rag_ready": artifacts["rag_index_ready"],
            "rag_available": artifacts["rag_index_ready"] and any(item["name"] == "RAG repository" and item["status"] == "ok" for item in services) and bool(rag_runtime["runtime_ok"]) and bool(rag_runtime["model_ok"]),
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
                "path": str(path),
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
                "path": str(report_path),
                "available": False,
                "error": str(exc),
                "data": None,
            }
        return {
            "path": str(report_path),
            "available": True,
            "error": None,
            "data": payload,
        }
    return None


def load_rag_sources(manifest_path: Path) -> list[dict[str, Any]]:
    if not manifest_path.exists():
        return []
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    sources = payload.get("sources", [])
    if isinstance(sources, list):
        return [item for item in sources if isinstance(item, dict)]
    return []


def _check_dependencies() -> list[dict[str, Any]]:
    dependency_specs = [
        ("streamlit", True),
        ("numpy", True),
        ("pandas", True),
        ("plotly", True),
        ("pydantic", True),
        ("chromadb", False),
        ("ollama", False),
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
            "detail": omc_path or "Executable not found on PATH.",
        }
    )
    return results


def _check_rag_runtime() -> dict[str, Any]:
    tags_url = f"{DEFAULT_OLLAMA_HOST}/api/tags"
    try:
        with request.urlopen(tags_url, timeout=3) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except error.URLError as exc:
        return {
            "status": "warning",
            "host": DEFAULT_OLLAMA_HOST,
            "embedding_model": DEFAULT_EMBED_MODEL,
            "runtime_ok": False,
            "model_ok": False,
            "models": [],
            "detail": f"Ollama indisponivel em {DEFAULT_OLLAMA_HOST}: {exc.reason}",
        }
    except Exception as exc:
        return {
            "status": "warning",
            "host": DEFAULT_OLLAMA_HOST,
            "embedding_model": DEFAULT_EMBED_MODEL,
            "runtime_ok": False,
            "model_ok": False,
            "models": [],
            "detail": f"Falha ao consultar Ollama local: {exc}",
        }

    models_payload = payload.get("models", []) if isinstance(payload, dict) else []
    models = [str(item.get("name") or "") for item in models_payload if isinstance(item, dict) and item.get("name")]
    model_ok = any(name == DEFAULT_EMBED_MODEL or name.startswith(f"{DEFAULT_EMBED_MODEL}:") for name in models)
    detail = (
        f"Ollama respondendo em {DEFAULT_OLLAMA_HOST}; modelo `{DEFAULT_EMBED_MODEL}` detectado."
        if model_ok
        else f"Ollama respondendo em {DEFAULT_OLLAMA_HOST}, mas o modelo `{DEFAULT_EMBED_MODEL}` nao foi encontrado."
    )
    return {
        "status": "ok" if model_ok else "warning",
        "host": DEFAULT_OLLAMA_HOST,
        "embedding_model": DEFAULT_EMBED_MODEL,
        "runtime_ok": True,
        "model_ok": model_ok,
        "models": models[:20],
        "detail": detail,
    }


def _check_services() -> list[dict[str, Any]]:
    service_specs = [
        ("Simulation service", "simulator.service", "ADM1SimulationService"),
        ("Design pipeline", "simulator.design_pipeline", "ADM1DesignPipeline"),
        ("Phase 3 validation", "simulator.validation", "run_phase3_validation"),
        ("Literature validation", "simulator.literature_validation", "run_literature_validation"),
        ("RAG repository", "rag.repository", "ADM1RAGRepository"),
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


def _check_paths(paths: Any) -> list[dict[str, Any]]:
    checks = [
        ("documentation", paths.documentation, "directory"),
        ("rag/extracted", paths.extracted, "directory"),
        ("rag/db", paths.db, "directory"),
        ("simulator/runs", PROJECT_ROOT / "simulator" / "runs", "directory"),
        ("simulator/validation_runs", PROJECT_ROOT / "simulator" / "validation_runs", "directory"),
        ("simulator/literature_validation_runs", PROJECT_ROOT / "simulator" / "literature_validation_runs", "directory"),
        ("vendor/PyADM1", PROJECT_ROOT / "vendor" / "PyADM1", "directory"),
    ]
    results: list[dict[str, Any]] = []
    for label, path, kind in checks:
        exists = path.exists()
        item_count = 0
        if exists and kind == "directory":
            try:
                item_count = len(list(path.iterdir()))
            except Exception:
                item_count = 0
        results.append(
            {
                "label": label,
                "path": str(path),
                "status": "ok" if exists else "error",
                "exists": exists,
                "item_count": item_count,
            }
        )
    return results


def _collect_artifacts(root: Path, rag_sources: list[dict[str, Any]]) -> dict[str, Any]:
    documentation_dir = root / "documentation"
    rag_db_dir = root / "rag" / "db"
    scenario_dir = root / "simulator" / "runs"
    benchmark_dir = root / "simulator" / "benchmarks"
    validation_dir = root / "simulator" / "validation_runs"
    literature_dir = root / "simulator" / "literature_validation_runs"
    return {
        "pdf_count": len(list(documentation_dir.glob("*.pdf"))) if documentation_dir.exists() else 0,
        "rag_source_count": len(rag_sources),
        "rag_index_ready": rag_db_dir.exists() and any(rag_db_dir.iterdir()),
        "saved_scenario_count": len(list(scenario_dir.glob("*.json"))) if scenario_dir.exists() else 0,
        "benchmark_run_count": len([path for path in benchmark_dir.iterdir() if path.is_dir()]) if benchmark_dir.exists() else 0,
        "validation_run_count": len([path for path in validation_dir.iterdir() if path.is_dir()]) if validation_dir.exists() else 0,
        "literature_validation_count": len([path for path in literature_dir.iterdir() if path.is_dir()]) if literature_dir.exists() else 0,
        "page_count": 5,
    }


def _build_issues(
    dependencies: list[dict[str, Any]],
    services: list[dict[str, Any]],
    rag_runtime: dict[str, Any],
    path_checks: list[dict[str, Any]],
    artifacts: dict[str, Any],
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    for item in dependencies:
        if item["required"] and item["status"] != "ok":
            issues.append({"severity": "error", "message": f"Required dependency missing: {item['name']}. {item['detail']}"})
    for item in services:
        if item["status"] != "ok":
            issues.append({"severity": "error", "message": f"Service unavailable: {item['name']}. {item['detail']}"})
    for item in path_checks:
        if item["status"] != "ok" and item["label"] == "vendor/PyADM1":
            issues.append({"severity": "error", "message": "The original PyADM1 code was not found in vendor/PyADM1."})
    if artifacts["pdf_count"] == 0:
        issues.append({"severity": "warning", "message": "No PDFs were found in documentation/. The technical search page will be empty."})
    if not artifacts["rag_index_ready"]:
        issues.append({"severity": "warning", "message": "The vector index in rag/db is not ready yet. Technical search will require extraction and indexing first."})
    if artifacts["saved_scenario_count"] == 0:
        issues.append({"severity": "warning", "message": "No saved scenarios were found in simulator/runs/. The comparison page will populate after the first simulations."})
    return issues
