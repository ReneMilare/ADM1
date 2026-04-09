"""Serviço de relatório técnico para simulações ADM1.

Sem imports de streamlit — todas as funções são puras e testáveis fora da UI.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from simulator.core.models import SimulationResult
from webapp.contracts import (
    ReportPayload,
    SimulationDraft,
    SimulationReviewSnapshot,
)

DEFAULT_VAULT_PATH = str(Path(__file__).resolve().parents[2] / "vaultObsidianAMD1")


# ─── Helpers internos ─────────────────────────────────────────────────────────

def _feed_sic_kmol_m3(feed: Any) -> float | None:
    raw = getattr(feed, "sic_kmol_m3", None)
    if raw in (None, ""):
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None

def _draft_from_result(result: SimulationResult) -> SimulationDraft:
    """Reconstrói SimulationDraft a partir de SimulationResult (parcial/lossy)."""
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

    flow_rate = feed.flow_rate_m3_day
    if flow_rate is None and result.operating_conditions.hrt_days > 0:
        flow_rate = result.operating_conditions.volume_m3 / result.operating_conditions.hrt_days

    hydraulic_mode = str(result.metadata.get("hydraulic_mode", "hrt"))
    custom_name = str(result.metadata.get("custom_substrate_name", "") or "") or None
    ammonia_inhibition_mode = str(result.metadata.get("ammonia_inhibition_mode", "simple"))
    variant_config_raw = result.metadata.get("variant_config")
    variant_config = dict(variant_config_raw) if isinstance(variant_config_raw, dict) else None

    return SimulationDraft(
        reactor_type=result.reactor.reactor_type,
        substrate_mode=substrate_mode,
        preset_id=preset_id,
        custom_substrate_name=custom_name,
        feed_name=feed.name,
        feed_params=feed_params,
        hydraulic_mode=hydraulic_mode,
        volume_m3=result.operating_conditions.volume_m3,
        temperature_c=result.operating_conditions.temperature_c,
        hrt_days=result.operating_conditions.hrt_days,
        flow_rate_m3_day=float(flow_rate or 0.0),
        backend_requested=str(result.metadata.get("backend_requested", result.simulation.backend)),
        extensions=list(getattr(result.simulation, "full_extensions", []) or []),
        extension_state_overrides=dict(getattr(result.simulation, "full_initial_state_overrides", {}) or {}),
        extension_influent_overrides=dict(getattr(result.simulation, "full_influent_state_overrides", {}) or {}),
        extension_param_overrides=dict(getattr(result.simulation, "full_extension_parameter_overrides", {}) or {}),
        duration_days=result.simulation.duration_days,
        evaluation_points=result.simulation.evaluation_points,
        solver=result.simulation.solver,
        persist=result.simulation.persist,
        ammonia_inhibition_mode=ammonia_inhibition_mode,
        variant_config=variant_config,
    )


def _review_from_result(result: SimulationResult, draft: SimulationDraft) -> SimulationReviewSnapshot:
    """Constrói SimulationReviewSnapshot via build_review_snapshot com fallback manual."""
    try:
        from webapp.state.review import build_review_snapshot
        return build_review_snapshot(draft)
    except Exception:
        backend_req = str(result.metadata.get("backend_requested", result.simulation.backend))
        backend_eff = str(result.metadata.get("backend_used", result.simulation.backend))
        fallback_reason = str(result.metadata.get("backend_fallback_reason", "") or "") or None
        return SimulationReviewSnapshot(
            draft_id=draft.draft_id,
            reactor_type=draft.reactor_type,
            substrate_mode=draft.substrate_mode,
            preset_id=draft.preset_id,
            backend_requested=backend_req,
            backend_predicted=backend_eff,
            backend_effective=backend_eff,
            fallback_reason=fallback_reason,
            extensions=list(draft.extensions),
            consistency_flags=[],
            warnings=[],
            is_ready=True,
        )


def _extract_kpis(result: SimulationResult) -> dict[str, float]:
    """Extrai KPIs principais do SimulationResult."""
    s = result.summary
    kpis: dict[str, float] = {}
    for attr in (
        "methane_final_m3_day",
        "biogas_final_m3_day",
        "ph_final",
        "vfa_final",
        "effluent_cod_final",
        "stability_index",
    ):
        val = getattr(s, attr, None)
        if val is not None:
            try:
                kpis[attr] = round(float(val), 6)
            except (TypeError, ValueError):
                pass
    return kpis


def _extract_warnings(result: SimulationResult) -> list[str]:
    """Extrai warnings do metadata do resultado."""
    raw = result.metadata.get("warnings")
    if isinstance(raw, list):
        return [str(w) for w in raw if w]
    return []


def _generate_interpretation(kpis: dict[str, float]) -> str:
    """Gera texto de interpretação automática baseado nos KPIs."""
    parts: list[str] = []
    ph = kpis.get("ph_final")
    stability = kpis.get("stability_index")
    vfa = kpis.get("vfa_final")

    if ph is not None:
        if 6.8 <= ph <= 7.4:
            parts.append("pH dentro da faixa ótima para digestão anaeróbia.")
        elif ph < 6.5:
            parts.append("pH baixo — risco de acidificação.")
        elif ph > 7.8:
            parts.append("pH alto — possível inibição por amônia.")

    if stability is not None:
        if stability > 0.95:
            parts.append("Processo estável.")
        elif stability < 0.80:
            parts.append("Atenção: estabilidade abaixo do limiar recomendado.")

    if vfa is not None and vfa > 0.5:
        parts.append("VFA elevado — monitorar acidificação.")

    return " ".join(parts) if parts else ""


# ─── API pública ──────────────────────────────────────────────────────────────

def build_report_payload(
    result: SimulationResult,
    *,
    scenario_id: str | None = None,
    baseline_id: str | None = None,
) -> ReportPayload:
    """Constrói ReportPayload sem depender da UI.

    Args:
        result: SimulationResult já executado.
        scenario_id: ID externo do cenário (usa result.simulation_id se omitido).
        baseline_id: simulation_id do cenário baseline para calcular diff.

    Returns:
        ReportPayload pronto para serialização ou renderização Markdown.
    """
    draft = _draft_from_result(result)
    review = _review_from_result(result, draft)
    kpis = _extract_kpis(result)
    warnings = _extract_warnings(result)
    interpretation = _generate_interpretation(kpis)

    diff_with_baseline: dict[str, Any] | None = None
    if baseline_id:
        try:
            from webapp.services.scenario_service import compute_scenario_diff
            diff_with_baseline = compute_scenario_diff(result.simulation_id, baseline_id)
        except Exception:
            pass

    return ReportPayload(
        scenario_id=scenario_id or result.simulation_id,
        draft=draft,
        review=review,
        kpis=kpis,
        warnings=warnings,
        interpretation=interpretation,
        diff_with_baseline=diff_with_baseline,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )


def render_report_markdown(payload: ReportPayload) -> str:
    """Gera conteúdo Markdown do relatório a partir do ReportPayload.

    Sem Streamlit. Retorna string Markdown válida no Obsidian
    (frontmatter YAML + Markdown padrão).
    """
    draft = payload.draft
    review = payload.review
    kpis = payload.kpis

    sim_id = payload.scenario_id or draft.draft_id
    date_str = payload.generated_at[:10] if payload.generated_at else datetime.now(timezone.utc).strftime("%Y-%m-%d")

    has_fallback = review.backend_requested != review.backend_effective
    if has_fallback and review.fallback_reason:
        fallback_str = f"Sim ({review.fallback_reason})"
    elif has_fallback:
        fallback_str = "Sim"
    else:
        fallback_str = "Não"

    exts_str = ", ".join(f"`{e}`" for e in review.extensions) if review.extensions else "nenhuma"

    lines: list[str] = [
        "---",
        "tags: [relatorio, adm1, simulacao]",
        f"created: {date_str}",
        f"simulation_id: {sim_id}",
        "---",
        "",
        "# Relatório de Simulação ADM1",
        "",
        "## Contexto",
        "",
        f"- **Reator:** {draft.reactor_type}",
        f"- **Substrato:** {draft.substrate_mode} / {draft.preset_id or 'manual'}",
        f"- **Backend solicitado:** {review.backend_requested}",
        f"- **Backend efetivo:** {review.backend_effective}",
        f"- **Fallback:** {fallback_str}",
        f"- **Extensões ativas:** {exts_str}",
        "",
        "## Configuração Principal",
        "",
        "| Parâmetro | Valor |",
        "|---|---|",
        f"| Volume (m³) | {draft.volume_m3:.1f} |",
        f"| Temperatura (°C) | {draft.temperature_c:.1f} |",
        f"| HRT (dias) | {draft.hrt_days:.1f} |",
        f"| Duração (dias) | {draft.duration_days:.1f} |",
        "",
        "## KPIs Principais",
        "",
        "| Indicador | Valor |",
        "|---|---|",
    ]

    _kpi_rows: list[tuple[str, str, str]] = [
        ("Metano final (m³/dia)", "methane_final_m3_day", ".3f"),
        ("Biogás final (m³/dia)", "biogas_final_m3_day", ".3f"),
        ("pH final", "ph_final", ".3f"),
        ("VFA total (kgCOD/m³)", "vfa_final", ".4f"),
        ("COD efluente (kgCOD/m³)", "effluent_cod_final", ".4f"),
        ("Índice de estabilidade", "stability_index", ".5f"),
    ]
    for label, key, fmt in _kpi_rows:
        val = kpis.get(key)
        val_str = format(val, fmt) if val is not None else "N/A"
        lines.append(f"| {label} | {val_str} |")

    lines += [
        "",
        "## Interpretação",
        "",
        payload.interpretation if payload.interpretation else "_Sem interpretação automática disponível._",
        "",
        "## Avisos Técnicos",
        "",
    ]

    if payload.warnings:
        for w in payload.warnings:
            lines.append(f"- {w}")
    else:
        lines.append("Nenhum aviso.")

    # Seção de diff — só aparece se baseline foi fornecido
    if payload.diff_with_baseline is not None:
        diff = payload.diff_with_baseline
        lines += [
            "",
            "## Comparação com Baseline",
            "",
            f"Cenário A: `{diff.get('scenario_a', 'N/A')}` | Cenário B (baseline): `{diff.get('scenario_b', 'N/A')}`",
            "",
        ]

        inputs_diff = diff.get("inputs", {})
        operating_diff = diff.get("operating", {})
        if inputs_diff or operating_diff:
            lines += [
                "### Mudanças em Inputs/Operação",
                "",
                "| Seção | Campo | Cenário A | Baseline |",
                "|---|---|---|---|",
            ]
            for fld, vals in inputs_diff.items():
                lines.append(f"| feed | {fld} | {vals['a']} | {vals['b']} |")
            for fld, vals in operating_diff.items():
                lines.append(f"| operação | {fld} | {vals['a']} | {vals['b']} |")
            lines.append("")

        backend_diff = diff.get("backend")
        if backend_diff:
            bd = backend_diff
            lines += [
                "### Mudanças de Backend",
                "",
                f"- Backend solicitado: `{bd['requested']['a']}` → `{bd['requested']['b']}`",
                f"- Backend executado: `{bd['used']['a']}` → `{bd['used']['b']}`",
                "",
            ]

        ext_diff = diff.get("extensions", {})
        if ext_diff.get("added") or ext_diff.get("removed"):
            lines.append("### Mudanças em Extensões")
            lines.append("")
            for e in ext_diff.get("added", []):
                lines.append(f"- Adicionada em B: `{e}`")
            for e in ext_diff.get("removed", []):
                lines.append(f"- Removida de B: `{e}`")
            lines.append("")

        kpis_diff = diff.get("kpis", {})
        if kpis_diff:
            lines += [
                "### Mudanças em KPIs",
                "",
                "| KPI | Cenário A | Baseline | Delta |",
                "|---|---|---|---|",
            ]
            for kpi_name, kpi_vals in kpis_diff.items():
                delta = kpi_vals.get("delta_pct", kpi_vals.get("delta_abs", "N/A"))
                delta_str = f"{delta:+.3f}" if isinstance(delta, float) else str(delta)
                lines.append(f"| {kpi_name} | {kpi_vals.get('a', 'N/A')} | {kpi_vals.get('b', 'N/A')} | {delta_str} |")
            lines.append("")

    lines.append("")
    return "\n".join(lines)


def export_report_to_vault(payload: ReportPayload, vault_path: str = DEFAULT_VAULT_PATH) -> str:
    """Salva o relatório Markdown no vault do Obsidian.

    Args:
        payload: ReportPayload com os dados do relatório.
        vault_path: Caminho para o vault Obsidian. Usa DEFAULT_VAULT_PATH se omitido.

    Returns:
        Caminho absoluto do arquivo criado.
    """
    sim_id = payload.scenario_id or payload.draft.draft_id
    date_str = payload.generated_at[:10] if payload.generated_at else datetime.now(timezone.utc).strftime("%Y-%m-%d")
    filename = f"Relatorio_Sim_{sim_id}_{date_str}.md"

    reports_dir = Path(vault_path) / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    file_path = reports_dir / filename
    content = render_report_markdown(payload)
    file_path.write_text(content, encoding="utf-8")
    return str(file_path)


def report_payload_to_csv_bytes(payload: ReportPayload) -> bytes:
    """Gera CSV bytes com os KPIs do relatório (para download na UI)."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["indicador", "valor"])

    _kpi_labels: list[tuple[str, str]] = [
        ("methane_final_m3_day", "Metano final (m³/dia)"),
        ("biogas_final_m3_day", "Biogás final (m³/dia)"),
        ("ph_final", "pH final"),
        ("vfa_final", "VFA total (kgCOD/m³)"),
        ("effluent_cod_final", "COD efluente (kgCOD/m³)"),
        ("stability_index", "Índice de estabilidade"),
    ]
    for key, label in _kpi_labels:
        val = payload.kpis.get(key)
        if val is not None:
            writer.writerow([label, val])

    return buffer.getvalue().encode("utf-8")
