"""Seção: Revisão técnica antes da execução."""
from __future__ import annotations

import streamlit as st

from webapp.contracts import SimulationReviewSnapshot

_BACKEND_LABELS: dict[str, str] = {
    "pyadm1": "PyADM1 original",
    "full": "ADM1 full nativo",
    "auto": "Auto (CSTR → PyADM1)",
    "reduced": "Reduced",
}


def render_technical_review(review: SimulationReviewSnapshot) -> bool:
    """Renderiza o painel de revisão técnica antes da execução.

    Returns:
        True se o caso pode ser executado (review.is_ready).
    """
    st.subheader("Revisão técnica do caso")

    # Backend solicitado vs previsto
    req_label = _BACKEND_LABELS.get(review.backend_requested, review.backend_requested)
    pred_label = _BACKEND_LABELS.get(review.backend_predicted, review.backend_predicted)

    bcol1, bcol2 = st.columns(2)
    bcol1.metric("Backend solicitado", req_label)
    bcol2.metric("Backend previsto", pred_label)

    if review.fallback_reason:
        st.warning(f"⚠️ **Fallback de backend:** {review.fallback_reason}")
    elif review.backend_predicted != review.backend_requested:
        st.info(
            f"Backend `{review.backend_requested}` → `{review.backend_predicted}` "
            "(resolução automática de modo)"
        )

    # Flags de consistência
    if review.consistency_flags:
        st.markdown("**Flags de consistência:**")
        for flag in review.consistency_flags:
            st.warning(f"🚩 {flag}")

    # Warnings técnicos
    if review.warnings and not review.fallback_reason:
        # fallback_reason já está em warnings — evitar duplicação
        extra_warnings = [w for w in review.warnings if w != review.fallback_reason]
        if extra_warnings:
            st.markdown("**Avisos técnicos:**")
            for w in extra_warnings:
                st.warning(w)
    elif review.warnings and review.fallback_reason:
        extra_warnings = [w for w in review.warnings if w != review.fallback_reason]
        if extra_warnings:
            st.markdown("**Avisos técnicos:**")
            for w in extra_warnings:
                st.warning(w)

    if not review.consistency_flags and not review.warnings:
        st.success("✅ Nenhum aviso técnico detectado.")

    if not review.is_ready:
        st.error(
            "❌ **Não é possível executar.** Corrija os bloqueios acima antes de continuar."
        )

    return review.is_ready
