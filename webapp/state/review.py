"""Construção do SimulationReviewSnapshot a partir de um SimulationDraft.

100% independente de Streamlit.
"""

from __future__ import annotations

from webapp.contracts import SimulationDraft, SimulationReviewSnapshot
from webapp.state.backend_resolver import predict_backend

# Flags que bloqueiam a execução (is_ready = False)
_BLOCKING_FLAGS: frozenset[str] = frozenset({
    "Extensões ativas requerem backend full",
    "COD particulado deve ser positivo",
})


def build_review_snapshot(draft: SimulationDraft) -> SimulationReviewSnapshot:
    """Constrói SimulationReviewSnapshot a partir de um SimulationDraft."""
    backend_predicted, fallback_reason = predict_backend(draft)
    consistency_flags = _check_consistency(draft)
    warnings = _build_warnings(draft, backend_predicted, fallback_reason)
    is_ready = not any(f in _BLOCKING_FLAGS for f in consistency_flags)

    return SimulationReviewSnapshot(
        draft_id=draft.draft_id,
        reactor_type=draft.reactor_type,
        substrate_mode=draft.substrate_mode,
        preset_id=draft.preset_id,
        backend_requested=draft.backend_requested,
        backend_predicted=backend_predicted,
        backend_effective=backend_predicted,
        fallback_reason=fallback_reason,
        extensions=list(draft.extensions),
        consistency_flags=consistency_flags,
        warnings=warnings,
        is_ready=is_ready,
    )


def _effective_hrt(draft: SimulationDraft) -> float:
    """Calcula o HRT efetivo considerando o modo hidráulico."""
    if draft.hydraulic_mode == "flow_rate" and draft.flow_rate_m3_day > 0.0:
        return draft.volume_m3 / draft.flow_rate_m3_day
    return draft.hrt_days


def _check_consistency(draft: SimulationDraft) -> list[str]:
    """Flags de consistência técnica.

    Retorna uma lista de strings descrevendo problemas identificados no draft.
    Flags em _BLOCKING_FLAGS tornam is_ready = False.
    """
    flags: list[str] = []

    if draft.reactor_type != "batch":
        effective_hrt = _effective_hrt(draft)
        if effective_hrt > 0.0 and effective_hrt < 5.0:
            flags.append("HRT muito baixo para digestão anaeróbia estável (< 5 dias)")
        if effective_hrt > 60.0:
            flags.append("HRT muito alto — verifique se o objetivo é BMP/batch")

    if draft.temperature_c < 20.0:
        flags.append("Temperatura abaixo da faixa mesofílica (< 20°C)")
    if draft.temperature_c > 60.0:
        flags.append("Temperatura acima da faixa termofílica (> 60°C)")

    if draft.extensions and draft.backend_requested != "full":
        flags.append("Extensões ativas requerem backend full")

    if draft.substrate_mode == "manual":
        pcod = float(draft.feed_params.get("particulate_cod", 0.0))
        if pcod <= 0.0:
            flags.append("COD particulado deve ser positivo")

    return flags


def _build_warnings(
    draft: SimulationDraft,
    backend_predicted: str,
    fallback_reason: str | None,
) -> list[str]:
    """Warnings técnicos baseados no draft e no backend previsto."""
    warnings: list[str] = []

    if fallback_reason:
        warnings.append(fallback_reason)

    if draft.reactor_type != "batch":
        effective_hrt = _effective_hrt(draft)
        if draft.duration_days > 0 and effective_hrt > 0 and draft.duration_days < effective_hrt:
            warnings.append(
                "Duração da simulação menor que o HRT — o transiente pode ser curto demais para análise técnica."
            )

    if draft.temperature_c > 0 and (draft.temperature_c < 30.0 or draft.temperature_c > 40.0):
        warnings.append(
            "Temperatura fora da faixa mesofílica clássica (30–40°C). Verifique se é intencional para o estudo."
        )

    if draft.evaluation_points < 81:
        warnings.append(
            "Discretização enxuta. Use mais pontos de avaliação para curvas mais suaves para export ou comparação."
        )

    return warnings
