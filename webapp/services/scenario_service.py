from __future__ import annotations

from io import StringIO
from typing import Any

import pandas as pd

from simulator.core.models import SimulationResult
from simulator.scenario_store import ScenarioStore
from webapp.utils.presets import PRESET_LABELS

SERIES_OPTIONS = {
    "methane_m3_day": {
        "label": "Metano",
        "title": "Produção de metano",
        "y_axis_title": "m3/d",
    },
    "biogas_m3_day": {
        "label": "Biogás",
        "title": "Produção de biogás",
        "y_axis_title": "m3/d",
    },
    "ph": {
        "label": "pH",
        "title": "Perfil de pH",
        "y_axis_title": "pH",
    },
    "vfa_total": {
        "label": "VFA total",
        "title": "Perfil de VFA total",
        "y_axis_title": "kgCOD/m3",
    },
}


def load_saved_results(*, store: ScenarioStore | None = None, limit: int | None = None) -> tuple[list[SimulationResult], list[str]]:
    scenario_store = store or ScenarioStore()
    results: list[SimulationResult] = []
    errors: list[str] = []
    for simulation_id in scenario_store.list_simulation_ids():
        try:
            results.append(scenario_store.load(simulation_id))
        except Exception as exc:
            errors.append(f"{simulation_id}: {exc}")
    results.sort(key=lambda item: item.created_at, reverse=True)
    if limit is not None:
        results = results[:limit]
    return results, errors


def substrate_label(result: SimulationResult) -> str:
    preset_id = str(result.metadata.get("substrate_preset", "") or "").strip()
    if preset_id and preset_id in PRESET_LABELS:
        return PRESET_LABELS[preset_id]
    return result.feed.name


def backend_requested(result: SimulationResult) -> str:
    return str(result.metadata.get("backend_requested", result.simulation.backend))


def backend_used(result: SimulationResult) -> str:
    return str(result.metadata.get("backend_used", result.simulation.backend))


def has_fallback(result: SimulationResult) -> bool:
    return backend_requested(result) != backend_used(result)


def scenario_option_label(result: SimulationResult) -> str:
    substrate = substrate_label(result)
    return f"{result.simulation_id} | {result.reactor.reactor_type} | {backend_used(result)} | {substrate}"


def scenario_option_labels(results: list[SimulationResult]) -> dict[str, str]:
    return {result.simulation_id: scenario_option_label(result) for result in results}


def filter_values(results: list[SimulationResult]) -> dict[str, list[str]]:
    return {
        "reactors": sorted({result.reactor.reactor_type for result in results}),
        "backends": sorted({backend_used(result) for result in results}),
        "substrates": sorted({substrate_label(result) for result in results}),
    }


def filter_results(
    results: list[SimulationResult],
    *,
    reactor_types: list[str] | None = None,
    backends: list[str] | None = None,
    substrates: list[str] | None = None,
    fallback_mode: str = "all",
    search_text: str = "",
) -> list[SimulationResult]:
    filtered: list[SimulationResult] = []
    query = search_text.casefold().strip()
    for result in results:
        if reactor_types and result.reactor.reactor_type not in reactor_types:
            continue
        if backends and backend_used(result) not in backends:
            continue
        if substrates and substrate_label(result) not in substrates:
            continue
        if fallback_mode == "fallback_only" and not has_fallback(result):
            continue
        if fallback_mode == "no_fallback" and has_fallback(result):
            continue
        if query:
            haystack = " | ".join(
                [
                    result.simulation_id,
                    result.reactor.reactor_type,
                    backend_requested(result),
                    backend_used(result),
                    result.feed.name,
                    substrate_label(result),
                    str(result.metadata.get("substrate_preset", "")),
                ]
            ).casefold()
            if query not in haystack:
                continue
        filtered.append(result)
    return filtered


def catalog_rows(results: list[SimulationResult]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for result in results:
        rows.append(
            {
                "simulation_id": result.simulation_id,
                "created_at": result.created_at,
                "reactor": result.reactor.reactor_type,
                "substrate": substrate_label(result),
                "feed_name": result.feed.name,
                "backend_requested": backend_requested(result),
                "backend_used": backend_used(result),
                "fallback": "sim" if has_fallback(result) else "não",
                "duration_days": round(result.simulation.duration_days, 2),
                "temperature_c": round(result.operating_conditions.temperature_c, 2),
                "hrt_days": round(result.operating_conditions.hrt_days, 2),
                "methane_final_m3_day": round(result.summary.methane_final_m3_day, 3),
                "biogas_final_m3_day": round(result.summary.biogas_final_m3_day, 3),
                "ph_final": round(result.summary.ph_final, 3),
                "vfa_final": round(result.summary.vfa_final, 3),
                "fallback_reason": str(result.metadata.get("backend_fallback_reason", "") or ""),
            }
        )
    return rows


def selected_results(results: list[SimulationResult], selected_ids: list[str]) -> list[SimulationResult]:
    result_map = {result.simulation_id: result for result in results}
    return [result_map[simulation_id] for simulation_id in selected_ids if simulation_id in result_map]


def comparison_frame(results: list[SimulationResult], *, baseline_id: str) -> pd.DataFrame:
    if not results:
        return pd.DataFrame()
    baseline = next((result for result in results if result.simulation_id == baseline_id), results[0])
    rows: list[dict[str, Any]] = []
    for result in results:
        rows.append(
            {
                "baseline": "sim" if result.simulation_id == baseline.simulation_id else "",
                "simulation_id": result.simulation_id,
                "reactor": result.reactor.reactor_type,
                "substrate": substrate_label(result),
                "backend_requested": backend_requested(result),
                "backend_used": backend_used(result),
                "fallback": "sim" if has_fallback(result) else "não",
                "methane_final_m3_day": round(result.summary.methane_final_m3_day, 3),
                "delta_methane_pct": round(_relative_delta_pct(result.summary.methane_final_m3_day, baseline.summary.methane_final_m3_day), 3),
                "biogas_final_m3_day": round(result.summary.biogas_final_m3_day, 3),
                "delta_biogas_pct": round(_relative_delta_pct(result.summary.biogas_final_m3_day, baseline.summary.biogas_final_m3_day), 3),
                "ph_final": round(result.summary.ph_final, 3),
                "delta_ph_abs": round(result.summary.ph_final - baseline.summary.ph_final, 3),
                "vfa_final": round(result.summary.vfa_final, 3),
                "delta_vfa_pct": round(_relative_delta_pct(result.summary.vfa_final, baseline.summary.vfa_final), 3),
                "effluent_cod_final": round(result.summary.effluent_cod_final, 3),
                "delta_effluent_cod_pct": round(_relative_delta_pct(result.summary.effluent_cod_final, baseline.summary.effluent_cod_final), 3),
                "stability_index": round(result.summary.stability_index, 5),
                "fallback_reason": str(result.metadata.get("backend_fallback_reason", "") or ""),
            }
        )
    return pd.DataFrame(rows)


def fallback_rows(results: list[SimulationResult]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for result in results:
        if not has_fallback(result):
            continue
        rows.append(
            {
                "simulation_id": result.simulation_id,
                "reactor": result.reactor.reactor_type,
                "backend_requested": backend_requested(result),
                "backend_used": backend_used(result),
                "reason": str(result.metadata.get("backend_fallback_reason", "") or ""),
            }
        )
    return rows


def comparison_csv_bytes(results: list[SimulationResult], *, baseline_id: str) -> bytes:
    buffer = StringIO()
    comparison_frame(results, baseline_id=baseline_id).to_csv(buffer, index=False)
    return buffer.getvalue().encode("utf-8")


def _relative_delta_pct(value: float, baseline: float) -> float:
    denominator = baseline if abs(baseline) > 1e-12 else 1e-12
    return (value - baseline) / denominator * 100.0
