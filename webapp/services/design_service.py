from __future__ import annotations

import json
from typing import Any

import pandas as pd

from simulator.design_pipeline import ADM1DesignPipeline, GOAL_WEIGHTS

GOAL_OPTIONS = {
    "balanced": "Balanceado",
    "maximize_methane": "Maximizar metano",
    "maximize_stability": "Maximizar estabilidade",
    "minimize_effluent_cod": "Minimizar COD no efluente",
}
GOAL_DESCRIPTIONS = {
    "balanced": "Equilibra producao de metano, estabilidade, VFA, pH e qualidade do efluente.",
    "maximize_methane": "Puxa a recomendacao para produtividade de metano, sem ignorar completamente estabilidade e pH.",
    "maximize_stability": "Favorece operacao mais robusta, com menor instabilidade e menor risco de acumulo de acidos.",
    "minimize_effluent_cod": "Prioriza qualidade de efluente, mantendo metano e estabilidade como criterios secundarios.",
}
BACKEND_STRATEGIES = {
    "auto": "Auto",
    "pyadm1": "PyADM1 original",
    "reduced": "Reduced",
}
REACTOR_OPTIONS = {
    "cstr": "CSTR",
    "uasb": "UASB",
    "plug_flow": "Plug-Flow",
    "two_phase": "Duas Fases (AD)",
    "tpad": "TPAD",
    "batch": "Batelada (BMP)",
}


def get_goal_options() -> dict[str, str]:
    return GOAL_OPTIONS.copy()


def get_goal_description(goal: str) -> str:
    return GOAL_DESCRIPTIONS[goal]


def get_backend_strategies() -> dict[str, str]:
    return BACKEND_STRATEGIES.copy()


def get_reactor_options() -> dict[str, str]:
    return REACTOR_OPTIONS.copy()


def run_design_study(
    *,
    substrate: str,
    design_goal: str,
    backend: str,
    reactor_candidates: list[str],
    volume_m3: float | None,
    temperature_c: float | None,
    hrt_days: float | None,
    duration_days: float,
    evaluation_points: int,
    persist_note: bool,
    note_title: str | None,
) -> dict[str, Any]:
    pipeline = ADM1DesignPipeline()
    return pipeline.run(
        substrate=substrate,
        design_goal=design_goal,
        backend=backend,
        reactor_candidates=reactor_candidates,
        volume_m3=volume_m3,
        temperature_c=temperature_c,
        hrt_days=hrt_days,
        duration_days=duration_days,
        evaluation_points=evaluation_points,
        persist_note=persist_note,
        note_title=note_title or None,
    )


def candidate_frame(report: dict[str, Any]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for index, candidate in enumerate(report["candidates"], start=1):
        summary = candidate["summary"]
        rows.append(
            {
                "rank": index,
                "reactor": candidate["reactor_type"],
                "backend_requested": candidate["backend_requested"],
                "backend_used": candidate["backend_used"],
                "score": round(float(candidate["score"]), 4),
                "methane_final_m3_day": round(float(summary["methane_final_m3_day"]), 3),
                "biogas_final_m3_day": round(float(summary["biogas_final_m3_day"]), 3),
                "ph_final": round(float(summary["ph_final"]), 3),
                "vfa_final": round(float(summary["vfa_final"]), 3),
                "effluent_cod_final": round(float(summary["effluent_cod_final"]), 3),
                "stability_index": round(float(summary["stability_index"]), 5),
                "reason": candidate["reason"],
            }
        )
    return pd.DataFrame(rows)


def component_score_frame(report: dict[str, Any]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for candidate in report["candidates"]:
        row = {
            "reactor": candidate["reactor_type"],
            "backend_used": candidate["backend_used"],
            "score": round(float(candidate["score"]), 4),
        }
        for component, value in candidate["component_scores"].items():
            row[component] = round(float(value), 4)
        rows.append(row)
    return pd.DataFrame(rows)


def interpretation_rows(report: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for candidate in report["candidates"]:
        strengths = sorted(candidate["component_scores"].items(), key=lambda item: item[1], reverse=True)[:2]
        weak_points = sorted(candidate["component_scores"].items(), key=lambda item: item[1])[:2]
        rows.append(
            {
                "reactor": candidate["reactor_type"],
                "backend_used": str(candidate["backend_used"]),
                "strengths": ", ".join(name for name, _ in strengths),
                "watchouts": ", ".join(name for name, _ in weak_points),
                "interpretation": candidate["reason"],
            }
        )
    return rows


def design_json_bytes(report: dict[str, Any]) -> bytes:
    return json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8")


def goal_weight_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for goal, weights in GOAL_WEIGHTS.items():
        rows.append(
            {
                "goal": goal,
                "methane": weights["methane"],
                "stability": weights["stability"],
                "effluent": weights["effluent"],
                "vfa": weights["vfa"],
                "ph": weights["ph"],
                "description": GOAL_DESCRIPTIONS[goal],
            }
        )
    return rows
