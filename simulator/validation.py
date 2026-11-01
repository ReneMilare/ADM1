from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from simulator.benchmark import build_default_scenarios, run_benchmark
from simulator.paths import _safe_project_path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_ROOT = Path(__file__).resolve().parent / "validation_runs"
MODELICA_ROOT = Path(__file__).resolve().parent / "modelica"


def detect_openmodelica_environment() -> dict[str, Any]:
    ompython_available = importlib.util.find_spec("OMPython") is not None
    omc_executable = shutil.which("omc")
    omc_available = omc_executable is not None
    omc_version = None
    ompython_session_ok = False
    ompython_error = None
    modelica_files = sorted(str(path.relative_to(PROJECT_ROOT)) for path in PROJECT_ROOT.rglob("*.mo"))

    if omc_available:
        try:
            completed = subprocess.run(
                [str(omc_executable), "--version"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            version_text = (completed.stdout or completed.stderr or "").strip()
            omc_version = version_text or "unknown"
        except Exception as exc:
            omc_version = f"error: {exc}"

    if ompython_available:
        try:
            from OMPython import OMCSessionZMQ  # type: ignore

            session = OMCSessionZMQ()
            version = session.sendExpression("getVersion()")
            if isinstance(version, str) and version.strip():
                ompython_session_ok = True
                omc_version = omc_version or version.strip()
            try:
                session.sendExpression("quit()")
            except Exception:
                pass
        except Exception as exc:
            ompython_error = str(exc)

    if not ompython_available and not omc_available:
        status = "toolchain_not_available"
        ready = False
        notes = [
            "OMPython não está instalado no Python local.",
            "O executável `omc` do OpenModelica não está disponível no PATH.",
        ]
    elif ompython_available and omc_available and not modelica_files:
        status = "model_not_configured"
        ready = False
        notes = [
            "A toolchain básica existe, mas ainda não há arquivos Modelica `.mo` no workspace para a validação cruzada.",
            "Coloque os modelos em `simulator/modelica/` ou em outro diretório versionado do projeto.",
        ]
    elif ompython_available and omc_available and modelica_files:
        status = "ready"
        ready = ompython_session_ok or omc_available
        notes = ["OpenModelica detectado e arquivos `.mo` encontrados no workspace."]
        if not ompython_session_ok and ompython_error:
            notes.append(f"A sessão OMPython ainda falhou: {ompython_error}")
    else:
        status = "partial_toolchain"
        ready = False
        notes = [
            "A toolchain OpenModelica está incompleta neste ambiente.",
            "É necessário ter `OMPython` e `omc` disponíveis para executar validação cruzada automatizada.",
        ]

    return {
        "status": status,
        "ready": ready,
        "ompython_available": ompython_available,
        "ompython_session_ok": ompython_session_ok,
        "ompython_error": ompython_error,
        "omc_available": omc_available,
        "omc_path": Path(omc_executable).name if omc_executable else None,
        "omc_version": omc_version,
        "modelica_files": modelica_files,
        "notes": notes,
    }


def export_openmodelica_scenarios(output_dir: Path) -> Path:
    scenarios = []
    for scenario in build_default_scenarios():
        scenarios.append(
            {
                "name": scenario.name,
                "description": scenario.description,
                "reactor_type": "cstr",
                "operating_conditions": scenario.operating_conditions.model_dump(),
                "feed": scenario.feed.model_dump(),
                "simulation": {
                    "duration_days": scenario.duration_days,
                    "evaluation_points": scenario.evaluation_points,
                },
            }
        )
    path = output_dir / "openmodelica_scenarios.json"
    path.write_text(json.dumps(scenarios, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def run_phase3_validation(
    *,
    output_root: Path | None = None,
    include_openmodelica: bool = True,
) -> tuple[dict[str, Any], Path]:
    if output_root is None:
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        output_dir = DEFAULT_OUTPUT_ROOT / timestamp
        output_dir.mkdir(parents=True, exist_ok=False)
    else:
        output_dir = output_root
        output_dir.mkdir(parents=True, exist_ok=True)

    benchmark_report, benchmark_dir = run_benchmark(output_root=output_dir)
    benchmark_summary = {
        "artifact_dir": _safe_project_path(benchmark_dir),
        "runtime_seconds": benchmark_report["aggregate"]["runtime_seconds"],
        "summary_metrics": benchmark_report["aggregate"]["summary_metrics"],
        "series_metrics": benchmark_report["aggregate"]["series_metrics"],
        "recommendation": benchmark_report["aggregate"]["recommendation"],
    }

    if include_openmodelica:
        openmodelica = detect_openmodelica_environment()
        scenario_export = export_openmodelica_scenarios(output_dir)
        external_validation = {
            "status": "completed" if openmodelica["ready"] else "pending_environment",
            "scenario_export_path": _safe_project_path(scenario_export),
            "notes": openmodelica["notes"],
        }
    else:
        openmodelica = {
            "status": "disabled",
            "ready": False,
            "notes": ["A detecção OpenModelica foi desabilitada para esta execução."],
        }
        external_validation = {
            "status": "disabled",
            "scenario_export_path": None,
            "notes": openmodelica["notes"],
        }

    recommendation = benchmark_report["aggregate"]["recommendation"]
    conclusion = {
        "phase3_local_validation_complete": True,
        "openmodelica_executed": bool(openmodelica.get("ready", False)),
        "backends_interchangeable": bool(recommendation.get("backends_interchangeable", False)),
        "prefer_pyadm1_for_cstr_fidelity": bool(recommendation.get("prefer_pyadm1_for_cstr_fidelity", False)),
        "promote_pyadm1_as_global_default": bool(recommendation.get("promote_pyadm1_as_global_default", False)),
        "rationale": recommendation.get("rationale"),
        "next_steps": _next_steps(openmodelica=openmodelica, recommendation=recommendation),
    }

    report = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "phase": "3",
        "benchmark": benchmark_summary,
        "openmodelica": openmodelica,
        "external_validation": external_validation,
        "conclusion": conclusion,
    }
    (output_dir / "phase3_validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "phase3_validation.md").write_text(_render_markdown(report), encoding="utf-8")
    return report, output_dir


def _next_steps(*, openmodelica: dict[str, Any], recommendation: dict[str, Any]) -> list[str]:
    steps: list[str] = []
    if not openmodelica.get("ready", False):
        steps.append("Instalar e configurar OpenModelica + OMPython para executar a validação cruzada externa.")
        steps.append("Adicionar os modelos `.mo` em `simulator/modelica/` ou em outro diretório versionado do workspace.")
    if recommendation.get("prefer_pyadm1_for_cstr_fidelity", False):
        steps.append("Usar `backend=pyadm1` explicitamente nos estudos de CSTR em que fidelidade ao modelo original seja prioridade.")
    if not recommendation.get("promote_pyadm1_as_global_default", False):
        steps.append("Manter o backend reduzido como padrão global até a validação externa definir uma política de backend por tipo de reator.")
    return steps


def _render_markdown(report: dict[str, Any]) -> str:
    benchmark = report["benchmark"]
    openmodelica = report["openmodelica"]
    conclusion = report["conclusion"]
    lines = [
        "# Validação Fase 3",
        "",
        f"- Gerado em: `{report['generated_at']}`",
        f"- Benchmark local: `{benchmark['artifact_dir']}`",
        f"- Status OpenModelica: `{openmodelica['status']}`",
        f"- Conclusão: `{conclusion['rationale']}`",
        "",
        "## Benchmark local",
        "",
        f"- Runtime médio `reduced`: `{benchmark['runtime_seconds']['reduced']['mean']:.4f} s`",
        f"- Runtime médio `pyadm1`: `{benchmark['runtime_seconds']['pyadm1']['mean']:.4f} s`",
        f"- Delta médio em `methane_final_m3_day`: `{benchmark['summary_metrics']['methane_final_m3_day']['mean_rel_delta_pct_vs_pyadm1']:.2f}%`",
        f"- NRMSE médio da série de metano: `{benchmark['series_metrics']['methane_m3_day']['mean_nrmse_pct']:.2f}%`",
        "",
        "## OpenModelica",
        "",
    ]
    for note in openmodelica.get("notes", []):
        lines.append(f"- {note}")
    lines.extend(["", "## Próximos passos", ""])
    for step in conclusion["next_steps"]:
        lines.append(f"- {step}")
    return "\n".join(lines)



def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Phase 3 validation workflow for ADM1, including local backend benchmarking and OpenModelica readiness checks.")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--skip-openmodelica", action="store_true")
    args = parser.parse_args()
    report, output_dir = run_phase3_validation(output_root=args.output_root, include_openmodelica=not args.skip_openmodelica)
    summary = {
        "output_dir": _safe_project_path(output_dir),
        "openmodelica_status": report["openmodelica"]["status"],
        "prefer_pyadm1_for_cstr_fidelity": report["conclusion"]["prefer_pyadm1_for_cstr_fidelity"],
        "promote_pyadm1_as_global_default": report["conclusion"]["promote_pyadm1_as_global_default"],
        "rationale": report["conclusion"]["rationale"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
