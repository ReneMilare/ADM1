from __future__ import annotations

import argparse
import json
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from simulator.core.models import FeedDefinition, OperatingConditions, SimulationConfig
from simulator.service import ADM1SimulationService

DEFAULT_NOTE_ROOT = Path(__file__).resolve().parent.parent / "vaultObsidian" / "Projeto"

SUBSTRATE_PRESETS: dict[str, dict[str, Any]] = {
    "lodo_de_esgoto": {
        "label": "Lodo de Esgoto",
        "note_link": "[[Lodo de Esgoto]]",
        "feed": FeedDefinition(
            name="Lodo de Esgoto",
            particulate_cod=14.0,
            soluble_cod=5.5,
            acetate=0.6,
            propionate=0.25,
            hydrogen=0.001,
            inorganic_nitrogen=1.3,
            alkalinity=4.8,
            ph=7.1,
        ),
        "operating": OperatingConditions(volume_m3=3000.0, temperature_c=35.0, hrt_days=20.0),
    },
    "residuos_alimentares": {
        "label": "Resíduos Alimentares",
        "note_link": "[[Resíduos Alimentares]]",
        "feed": FeedDefinition(
            name="Resíduos Alimentares",
            particulate_cod=11.5,
            soluble_cod=7.2,
            acetate=1.15,
            propionate=0.55,
            hydrogen=0.0015,
            inorganic_nitrogen=1.45,
            alkalinity=4.4,
            ph=6.95,
        ),
        "operating": OperatingConditions(volume_m3=2800.0, temperature_c=35.0, hrt_days=18.0),
    },
    "residuos_agricolas": {
        "label": "Resíduos Agrícolas",
        "note_link": "[[Resíduos Agrícolas]]",
        "feed": FeedDefinition(
            name="Resíduos Agrícolas",
            particulate_cod=16.0,
            soluble_cod=4.6,
            acetate=0.45,
            propionate=0.2,
            hydrogen=0.0009,
            inorganic_nitrogen=1.1,
            alkalinity=5.1,
            ph=7.2,
        ),
        "operating": OperatingConditions(volume_m3=3200.0, temperature_c=34.0, hrt_days=24.0),
    },
}
SUBSTRATE_ALIASES = {
    "lodo de esgoto": "lodo_de_esgoto",
    "sewage sludge": "lodo_de_esgoto",
    "sludge": "lodo_de_esgoto",
    "residuos alimentares": "residuos_alimentares",
    "resíduos alimentares": "residuos_alimentares",
    "food waste": "residuos_alimentares",
    "residuos agricolas": "residuos_agricolas",
    "resíduos agrícolas": "residuos_agricolas",
    "agricultural residues": "residuos_agricolas",
}
GOAL_WEIGHTS = {
    "balanced": {"methane": 0.35, "stability": 0.2, "effluent": 0.2, "vfa": 0.1, "ph": 0.15},
    "maximize_methane": {"methane": 0.6, "stability": 0.1, "effluent": 0.1, "vfa": 0.05, "ph": 0.15},
    "maximize_stability": {"methane": 0.15, "stability": 0.35, "effluent": 0.15, "vfa": 0.15, "ph": 0.2},
    "minimize_effluent_cod": {"methane": 0.25, "stability": 0.15, "effluent": 0.35, "vfa": 0.1, "ph": 0.15},
}
DEFAULT_REACTORS = ["cstr", "uasb", "plug_flow"]


class ADM1DesignPipeline:
    def __init__(self, service: ADM1SimulationService | None = None, note_root: Path | None = None) -> None:
        self.service = service or ADM1SimulationService()
        self.note_root = note_root or DEFAULT_NOTE_ROOT

    def run(
        self,
        *,
        substrate: str,
        design_goal: str = "balanced",
        backend: str = "auto",
        reactor_candidates: list[str] | None = None,
        volume_m3: float | None = None,
        temperature_c: float | None = None,
        hrt_days: float | None = None,
        duration_days: float = 45.0,
        evaluation_points: int = 181,
        persist_note: bool = False,
        note_title: str | None = None,
    ) -> dict[str, Any]:
        if design_goal not in GOAL_WEIGHTS:
            raise ValueError(f"Unsupported design_goal '{design_goal}'. Expected one of: {', '.join(sorted(GOAL_WEIGHTS))}")

        preset_id, preset = self._resolve_substrate(substrate)
        operating = preset["operating"].model_copy(
            update={
                "volume_m3": volume_m3 if volume_m3 is not None else preset["operating"].volume_m3,
                "temperature_c": temperature_c if temperature_c is not None else preset["operating"].temperature_c,
                "hrt_days": hrt_days if hrt_days is not None else preset["operating"].hrt_days,
            }
        )
        feed = preset["feed"].model_copy(deep=True)
        reactors = reactor_candidates or DEFAULT_REACTORS
        simulation = SimulationConfig(
            duration_days=duration_days,
            evaluation_points=evaluation_points,
            backend=backend,
            persist=False,
        )

        candidates: list[dict[str, Any]] = []
        for reactor in reactors:
            result = self.service.simulate(
                reactor,
                operating_conditions=operating,
                feed=feed,
                simulation=simulation,
                metadata={
                    "design_goal": design_goal,
                    "substrate_preset": preset_id,
                },
            )
            candidates.append(
                {
                    "reactor_type": reactor,
                    "backend_requested": result.metadata.get("backend_requested"),
                    "backend_used": result.metadata.get("backend_used"),
                    "summary": result.summary.model_dump(),
                    "simulation_id": result.simulation_id,
                }
            )

        scored_candidates = self._score_candidates(candidates, design_goal)
        recommended = max(scored_candidates, key=lambda item: item["score"])
        note_path = None
        if persist_note:
            note_path = self._write_note(
                preset=preset,
                design_goal=design_goal,
                backend=backend,
                operating=operating,
                scored_candidates=scored_candidates,
                recommended=recommended,
                note_title=note_title,
            )

        return {
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "substrate": {
                "preset_id": preset_id,
                "label": preset["label"],
                "note_link": preset["note_link"],
            },
            "design_goal": design_goal,
            "backend_strategy": backend,
            "operating_conditions": operating.model_dump(),
            "recommended_reactor": recommended["reactor_type"],
            "recommended_backend": recommended["backend_used"],
            "recommendation_reason": recommended["reason"],
            "candidates": scored_candidates,
            "note_path": str(note_path) if note_path is not None else None,
        }

    def _resolve_substrate(self, substrate: str) -> tuple[str, dict[str, Any]]:
        normalized = _normalize_key(substrate)
        preset_id = SUBSTRATE_ALIASES.get(normalized, normalized)
        if preset_id not in SUBSTRATE_PRESETS:
            known = ", ".join(sorted(SUBSTRATE_PRESETS))
            raise ValueError(f"Unsupported substrate '{substrate}'. Expected one of: {known}")
        return preset_id, SUBSTRATE_PRESETS[preset_id]

    def _score_candidates(self, candidates: list[dict[str, Any]], design_goal: str) -> list[dict[str, Any]]:
        weights = GOAL_WEIGHTS[design_goal]
        methane_values = [candidate["summary"]["methane_final_m3_day"] for candidate in candidates]
        stability_values = [candidate["summary"]["stability_index"] for candidate in candidates]
        effluent_values = [candidate["summary"]["effluent_cod_final"] for candidate in candidates]
        vfa_values = [candidate["summary"]["vfa_final"] for candidate in candidates]

        scored: list[dict[str, Any]] = []
        for candidate in candidates:
            summary = candidate["summary"]
            component_scores = {
                "methane": _normalize_positive(summary["methane_final_m3_day"], methane_values),
                "stability": _normalize_negative(summary["stability_index"], stability_values),
                "effluent": _normalize_negative(summary["effluent_cod_final"], effluent_values),
                "vfa": _normalize_negative(summary["vfa_final"], vfa_values),
                "ph": _ph_score(summary["ph_final"]),
            }
            total_score = sum(weights[key] * component_scores[key] for key in weights)
            scored.append({
                **candidate,
                "score": float(total_score),
                "component_scores": {key: float(value) for key, value in component_scores.items()},
            })
        ranked = sorted(scored, key=lambda item: item["score"], reverse=True)
        for rank, candidate in enumerate(ranked, start=1):
            candidate["rank"] = rank
            candidate["reason"] = _build_reason(candidate=candidate, component_scores=candidate["component_scores"], rank=rank)
        return ranked

    def _write_note(
        self,
        *,
        preset: dict[str, Any],
        design_goal: str,
        backend: str,
        operating: OperatingConditions,
        scored_candidates: list[dict[str, Any]],
        recommended: dict[str, Any],
        note_title: str | None,
    ) -> Path:
        self.note_root.mkdir(parents=True, exist_ok=True)
        title = note_title or f"Estudo de Design - {preset['label']} - {datetime.now(UTC).strftime('%Y-%m-%d %H%M')}"
        safe_name = _slugify(title) + ".md"
        path = self.note_root / safe_name
        path.write_text(
            _render_note(
                title=title,
                preset=preset,
                design_goal=design_goal,
                backend=backend,
                operating=operating,
                scored_candidates=scored_candidates,
                recommended=recommended,
            ),
            encoding="utf-8",
        )
        return path


def _normalize_key(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return "_".join(ascii_value.lower().replace("-", " ").split())


def _slugify(value: str) -> str:
    return _normalize_key(value)


def _normalize_positive(value: float, values: list[float]) -> float:
    low, high = min(values), max(values)
    if abs(high - low) <= 1e-9:
        return 1.0
    return (value - low) / (high - low)


def _normalize_negative(value: float, values: list[float]) -> float:
    low, high = min(values), max(values)
    if abs(high - low) <= 1e-9:
        return 1.0
    return (high - value) / (high - low)


def _ph_score(value: float, target: float = 7.1, tolerance: float = 0.6) -> float:
    return max(0.0, 1.0 - abs(value - target) / tolerance)


def _build_reason(*, candidate: dict[str, Any], component_scores: dict[str, float], rank: int) -> str:
    strengths = sorted(component_scores.items(), key=lambda item: item[1], reverse=True)[:2]
    strength_text = ", ".join(name for name, _ in strengths)
    return (
        f"{candidate['reactor_type']} ficou na posicao {rank} com backend `{candidate['backend_used']}`; "
        f"os componentes mais fortes foram {strength_text}."
    )


def _render_note(
    *,
    title: str,
    preset: dict[str, Any],
    design_goal: str,
    backend: str,
    operating: OperatingConditions,
    scored_candidates: list[dict[str, Any]],
    recommended: dict[str, Any],
) -> str:
    lines = [
        "---",
        "tags: [projeto, design, simulacao]",
        f"created: {datetime.now(UTC).date().isoformat()}",
        "status: ativo",
        "---",
        "",
        f"# {title}",
        "",
        "## Entrada",
        "",
        f"- Substrato: {preset['note_link']}",
        f"- Objetivo: `{design_goal}`",
        f"- Estratégia de backend: `{backend}`",
        f"- Volume: `{operating.volume_m3:.1f} m3`",
        f"- Temperatura: `{operating.temperature_c:.1f} C`",
        f"- HRT: `{operating.hrt_days:.1f} d`",
        "",
        "## Recomendação",
        "",
        f"- Reator recomendado: `{recommended['reactor_type']}`",
        f"- Backend usado: `{recommended['backend_used']}`",
        f"- Justificativa: {recommended['reason']}",
        "",
        "## Comparação",
        "",
        "| Reator | Backend | Score | Methane final | pH final | VFA final | Effluent COD |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for candidate in scored_candidates:
        summary = candidate["summary"]
        lines.append(
            f"| {candidate['reactor_type']} | {candidate['backend_used']} | {candidate['score']:.3f} | {summary['methane_final_m3_day']:.3f} | {summary['ph_final']:.3f} | {summary['vfa_final']:.3f} | {summary['effluent_cod_final']:.3f} |"
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the ADM1 design pipeline for a substrate preset and compare reactor candidates.")
    parser.add_argument("--substrate", required=True)
    parser.add_argument("--goal", default="balanced", choices=sorted(GOAL_WEIGHTS))
    parser.add_argument("--backend", default="auto", choices=["reduced", "pyadm1", "auto"])
    parser.add_argument("--duration-days", type=float, default=45.0)
    parser.add_argument("--evaluation-points", type=int, default=181)
    parser.add_argument("--persist-note", action="store_true")
    args = parser.parse_args()
    pipeline = ADM1DesignPipeline()
    result = pipeline.run(
        substrate=args.substrate,
        design_goal=args.goal,
        backend=args.backend,
        duration_days=args.duration_days,
        evaluation_points=args.evaluation_points,
        persist_note=args.persist_note,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
