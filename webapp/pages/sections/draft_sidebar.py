"""Seção: Resumo lateral do draft — renderizado no sidebar."""
from __future__ import annotations

import streamlit as st

from webapp.contracts import SimulationDraft, SimulationReviewSnapshot

_REACTOR_LABELS: dict[str, str] = {
    "cstr": "CSTR",
    "uasb": "UASB",
    "plug_flow": "Plug-Flow",
    "two_phase": "Duas Fases (AD)",
    "tpad": "TPAD",
    "batch": "Batelada (BMP)",
}

_BACKEND_LABELS: dict[str, str] = {
    "pyadm1": "PyADM1",
    "full": "Full nativo",
    "auto": "Auto",
    "reduced": "Reduced",
}

_MODE_LABELS: dict[str, str] = {
    "preset": "Preset nativo",
    "codigestion": "Co-digestão",
    "custom": "Personalizado",
    "manual": "Manual",
}


def render_draft_sidebar(draft: SimulationDraft, review: SimulationReviewSnapshot) -> None:
    """Renderiza o resumo técnico do draft no sidebar.

    O chamador deve garantir que este código está dentro de `with st.sidebar:`.
    """
    st.divider()
    st.caption("**Caso atual**")

    # Reator
    reactor_label = _REACTOR_LABELS.get(draft.reactor_type, draft.reactor_type)
    st.markdown(f"🏭 **Reator:** {reactor_label}")

    # Substrato
    mode_label = _MODE_LABELS.get(draft.substrate_mode, draft.substrate_mode)
    if draft.substrate_mode in ("preset", "codigestion") and draft.preset_id:
        sub_detail = f"{mode_label} — `{draft.preset_id}`"
    elif draft.substrate_mode == "custom" and draft.custom_substrate_name:
        sub_detail = f"{mode_label} — `{draft.custom_substrate_name}`"
    else:
        sub_detail = mode_label
    st.markdown(f"🌾 **Substrato:** {sub_detail}")

    # Backend
    req_label = _BACKEND_LABELS.get(draft.backend_requested, draft.backend_requested)
    pred_label = _BACKEND_LABELS.get(review.backend_predicted, review.backend_predicted)
    if review.fallback_reason:
        st.markdown(f"⚙️ **Backend:** `{req_label}` → **`{pred_label}`** ⚠️")
    else:
        st.markdown(f"⚙️ **Backend:** `{pred_label}`")

    # Extensões
    if draft.extensions:
        st.markdown(f"🧪 **Extensões:** {', '.join(draft.extensions)}")

    # Condições operacionais resumidas
    st.caption(
        f"V={draft.volume_m3:.0f} m³ | T={draft.temperature_c:.1f}°C | "
        f"HRT={draft.hrt_days:.1f} d | {draft.duration_days:.0f} dias sim."
    )

    # Warnings
    for warning in review.warnings:
        st.warning(warning)

    # Flags de consistência
    for flag in review.consistency_flags:
        st.warning(f"🚩 {flag}")

    # Status geral
    if review.is_ready:
        st.success("✅ Pronto para executar")
    else:
        st.error("❌ Bloqueios detectados — veja revisão técnica")
