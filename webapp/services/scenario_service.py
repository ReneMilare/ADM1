from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone
from io import StringIO
from typing import Any

import pandas as pd

from simulator.core.models import SimulationResult
from simulator.scenario_store import ScenarioStore
from webapp.contracts import ScenarioArtifact, SimulationDraft
from webapp.utils.presets import PRESET_LABELS

SERIES_OPTIONS = {
    "methane_m3_day": {
        "label": "Metano",
        "title": "Producao de metano",
        "y_axis_title": "Nm3/d",
    },
    "biogas_m3_day": {
        "label": "Biogas",
        "title": "Producao de biogas",
        "y_axis_title": "Nm3/d",
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
    "free_ammonia_kgN_m3": {
        "label": "Amonia livre (FAN)",
        "title": "Amonia livre (FAN)",
        "y_axis_title": "kgN/m3",
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


def _feed_sic_kmol_m3(feed: Any) -> float | None:
    raw = getattr(feed, "sic_kmol_m3", None)
    if raw in (None, ""):
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def substrate_label(result: SimulationResult) -> str:
    preset_id = str(result.metadata.get("substrate_preset", "") or "").strip()
    if preset_id and preset_id in PRESET_LABELS:
        return PRESET_LABELS[preset_id]
    return result.feed.name


def backend_requested(result: SimulationResult) -> str:
    return str(result.metadata.get("backend_requested", result.simulation.backend))


def backend_used(result: SimulationResult) -> str:
    return str(result.metadata.get("backend_used", result.simulation.backend))


def backend_scope(backend: str) -> str:
    normalized = str(backend).strip().lower()
    if normalized == "pyadm1":
        return "referencia CSTR"
    if normalized == "full":
        return "nativo validado"
    if normalized == "reduced":
        return "operacional/exploratorio"
    if normalized == "auto":
        return "politica de selecao"
    return normalized


def has_fallback(result: SimulationResult) -> bool:
    return backend_requested(result) != backend_used(result)


def reduced_is_exploratory_for_results(results: list[SimulationResult]) -> bool:
    used_backends = {backend_used(result) for result in results}
    return "reduced" in used_backends and bool(used_backends.intersection({"pyadm1", "full"}))


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
        used = backend_used(result)
        rows.append(
            {
                "simulation_id": result.simulation_id,
                "created_at": result.created_at,
                "reactor": result.reactor.reactor_type,
                "substrate": substrate_label(result),
                "feed_name": result.feed.name,
                "backend_requested": backend_requested(result),
                "backend_used": used,
                "backend_scope": backend_scope(used),
                "fallback": "sim" if has_fallback(result) else "nao",
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
    has_fan = any("free_ammonia_kgN_m3" in result.series for result in results)
    has_cn = any(
        result.summary.cn_ratio is not None or result.metadata.get("cn_ratio") is not None
        for result in results
    )
    rows: list[dict[str, Any]] = []
    for result in results:
        used = backend_used(result)
        row: dict[str, Any] = {
            "baseline": "sim" if result.simulation_id == baseline.simulation_id else "",
            "simulation_id": result.simulation_id,
            "reactor": result.reactor.reactor_type,
            "substrate": substrate_label(result),
            "backend_requested": backend_requested(result),
            "backend_used": used,
            "backend_scope": backend_scope(used),
            "fallback": "sim" if has_fallback(result) else "nao",
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
        if has_fan:
            fan_series = result.series.get("free_ammonia_kgN_m3")
            row["free_ammonia_kgN_m3"] = round(float(fan_series[-1]), 6) if fan_series else None
        if has_cn:
            cn_val = result.summary.cn_ratio if result.summary.cn_ratio is not None else result.metadata.get("cn_ratio")
            row["cn_ratio"] = round(float(cn_val), 2) if cn_val is not None else None
        rows.append(row)
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


# ─── Plan 04: artefatos e diff ────────────────────────────────────────────────

def _values_differ(a: Any, b: Any) -> bool:
    """Tolerance-aware comparison to avoid float noise in diff."""
    if a is None and b is None:
        return False
    if a is None or b is None:
        return True
    if isinstance(a, float) and isinstance(b, float):
        return not math.isclose(a, b, rel_tol=1e-6, abs_tol=1e-9)
    return a != b


def duplicate_scenario(simulation_id: str, *, store: ScenarioStore | None = None) -> str | None:
    """Duplica um cenário persistido e retorna o novo simulation_id ou None se falhar."""
    scenario_store = store or ScenarioStore()
    try:
        result = scenario_store.load(simulation_id)
    except Exception:
        return None
    short_id = str(uuid.uuid4())[:8]
    truncated = simulation_id[:20].rstrip("-_")
    new_id = f"copy_{truncated}_{short_id}"
    new_metadata = dict(result.metadata)
    new_metadata["duplicated_from"] = simulation_id
    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
    new_result = result.model_copy(update={
        "simulation_id": new_id,
        "created_at": now_iso,
        "metadata": new_metadata,
    })
    try:
        scenario_store.save(new_result)
        return new_id
    except Exception:
        return None


def build_scenario_artifact(
    simulation_id: str,
    *,
    notes: str = "",
    tags: list[str] | None = None,
    baseline_id: str | None = None,
    store: ScenarioStore | None = None,
) -> ScenarioArtifact | None:
    """Constrói um ScenarioArtifact a partir de um SimulationResult persistido.

    A reconstrução do draft é parcial (lossy): campos como configurações
    específicas de reator multifásico não são capturados no SimulationDraft.
    Use este artefato para relatório e diff, não para re-execução exata.
    """
    scenario_store = store or ScenarioStore()
    try:
        result = scenario_store.load(simulation_id)
    except Exception:
        return None
    preset_id = str(result.metadata.get("substrate_preset", "") or "").strip() or None
    substrate_mode = str(result.metadata.get("substrate_mode", "") or "")
    if not substrate_mode:
        substrate_mode = "preset" if preset_id else "manual"

    feed = result.feed
    feed_sic_kmol_m3 = _feed_sic_kmol_m3(feed)
    feed_params: dict[str, float] = {
        "particulate_cod": feed.particulate_cod,
        "soluble_cod": feed.soluble_cod,
        "acetate": feed.acetate,
        "propionate": feed.propionate,
        "hydrogen": feed.hydrogen,
        "inorganic_nitrogen": feed.inorganic_nitrogen,
        "alkalinity": feed.alkalinity,
        "sic_kmol_m3": float(feed_sic_kmol_m3 or 0.0),
        "ph": feed.ph,
    }

    draft = SimulationDraft(
        reactor_type=result.reactor.reactor_type,
        substrate_mode=substrate_mode,
        preset_id=preset_id,
        feed_name=feed.name,
        feed_params=feed_params,
        volume_m3=result.operating_conditions.volume_m3,
        temperature_c=result.operating_conditions.temperature_c,
        hrt_days=result.operating_conditions.hrt_days,
        backend_requested=str(result.metadata.get("backend_requested", result.simulation.backend)),
        extensions=list(getattr(result.simulation, "full_extensions", []) or []),
        extension_state_overrides=dict(getattr(result.simulation, "full_initial_state_overrides", {}) or {}),
        extension_influent_overrides=dict(getattr(result.simulation, "full_influent_state_overrides", {}) or {}),
        extension_param_overrides=dict(getattr(result.simulation, "full_extension_parameter_overrides", {}) or {}),
        duration_days=result.simulation.duration_days,
        evaluation_points=result.simulation.evaluation_points,
        solver=result.simulation.solver,
        persist=result.simulation.persist,
        ammonia_inhibition_mode=str(result.metadata.get("ammonia_inhibition_mode", "simple")),
        variant_config=dict(result.metadata["variant_config"]) if isinstance(result.metadata.get("variant_config"), dict) else None,
    )

    return ScenarioArtifact(
        result_id=simulation_id,
        draft=draft,
        tags=tags or [],
        notes=notes,
        baseline_id=baseline_id,
    )


def compute_scenario_diff(
    id_a: str,
    id_b: str,
    *,
    store: ScenarioStore | None = None,
) -> dict | None:
    """Compara dois cenários persistidos e retorna um diff estruturado.

    Retorna None se qualquer um dos dois IDs não for encontrado.
    Nunca levanta exceção por campos ausentes — usa getattr com default.
    """
    scenario_store = store or ScenarioStore()
    try:
        result_a = scenario_store.load(id_a)
        result_b = scenario_store.load(id_b)
    except Exception:
        return None

    # Feed inputs diff
    feed_fields = (
        "particulate_cod", "soluble_cod", "acetate", "propionate",
        "hydrogen", "inorganic_nitrogen", "alkalinity", "sic_kmol_m3", "ph", "flow_rate_m3_day",
    )
    inputs_diff: dict[str, dict] = {}
    for field_name in feed_fields:
        val_a = getattr(result_a.feed, field_name, None)
        val_b = getattr(result_b.feed, field_name, None)
        if _values_differ(val_a, val_b):
            inputs_diff[field_name] = {"a": val_a, "b": val_b}

    # Operating conditions + reactor type diff
    op_fields = ("volume_m3", "temperature_c", "hrt_days", "pressure_atm")
    operating_diff: dict[str, dict] = {}
    for field_name in op_fields:
        val_a = getattr(result_a.operating_conditions, field_name, None)
        val_b = getattr(result_b.operating_conditions, field_name, None)
        if _values_differ(val_a, val_b):
            operating_diff[field_name] = {"a": val_a, "b": val_b}
    rtype_a = getattr(result_a.reactor, "reactor_type", None)
    rtype_b = getattr(result_b.reactor, "reactor_type", None)
    if rtype_a != rtype_b:
        operating_diff["reactor_type"] = {"a": rtype_a, "b": rtype_b}

    # Backend diff
    req_a = backend_requested(result_a)
    req_b = backend_requested(result_b)
    used_a = backend_used(result_a)
    used_b = backend_used(result_b)
    backend_diff: dict | None = None
    if req_a != req_b or used_a != used_b:
        backend_diff = {
            "requested": {"a": req_a, "b": req_b},
            "used": {"a": used_a, "b": used_b},
        }

    # Extensions diff
    exts_a = set(getattr(result_a.simulation, "full_extensions", []) or [])
    exts_b = set(getattr(result_b.simulation, "full_extensions", []) or [])
    extensions_diff = {
        "added": sorted(exts_b - exts_a),
        "removed": sorted(exts_a - exts_b),
    }

    # Warnings from metadata
    warnings_a = list(result_a.metadata.get("warnings", []) or [])
    warnings_b = list(result_b.metadata.get("warnings", []) or [])

    # KPI diff helpers
    def _pct_delta(a: float, b: float) -> float | None:
        try:
            denom = abs(a) if abs(a) > 1e-12 else 1e-12
            return round((b - a) / denom * 100.0, 3)
        except Exception:
            return None

    def _abs_delta(a: float, b: float) -> float | None:
        try:
            return round(b - a, 4)
        except Exception:
            return None

    summary_a = result_a.summary
    summary_b = result_b.summary
    kpis: dict[str, dict] = {}
    for kpi_name in ("methane_final_m3_day", "biogas_final_m3_day", "vfa_final", "effluent_cod_final"):
        va = getattr(summary_a, kpi_name, None)
        vb = getattr(summary_b, kpi_name, None)
        if va is not None and vb is not None:
            kpis[kpi_name] = {"a": round(float(va), 4), "b": round(float(vb), 4), "delta_pct": _pct_delta(float(va), float(vb))}
    for kpi_name in ("ph_final", "stability_index"):
        va = getattr(summary_a, kpi_name, None)
        vb = getattr(summary_b, kpi_name, None)
        if va is not None and vb is not None:
            kpis[kpi_name] = {"a": round(float(va), 4), "b": round(float(vb), 4), "delta_abs": _abs_delta(float(va), float(vb))}

    has_changes = bool(
        inputs_diff or operating_diff or backend_diff
        or extensions_diff["added"] or extensions_diff["removed"]
    )

    return {
        "scenario_a": id_a,
        "scenario_b": id_b,
        "inputs": inputs_diff,
        "operating": operating_diff,
        "backend": backend_diff,
        "extensions": extensions_diff,
        "warnings": {"a": warnings_a, "b": warnings_b},
        "kpis": kpis,
        "has_changes": has_changes,
    }


def list_recent_artifacts(limit: int = 5, *, store: ScenarioStore | None = None) -> list[dict]:
    """Lista os cenários mais recentes em formato resumido para a home."""
    results, _ = load_saved_results(store=store, limit=limit)
    rows: list[dict] = []
    for result in results:
        rows.append({
            "simulation_id": result.simulation_id,
            "created_at": result.created_at,
            "reactor": result.reactor.reactor_type,
            "substrate": substrate_label(result),
            "backend_used": backend_used(result),
            "methane_final_m3_day": round(result.summary.methane_final_m3_day, 3),
            "ph_final": round(result.summary.ph_final, 3),
        })
    return rows
