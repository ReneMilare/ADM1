"""Seção: Definição do caso — tipo de reator, modo de substrato, backend e modo UI."""
from __future__ import annotations

import streamlit as st

from webapp.services.simulation_service import get_backend_options, get_reactor_options

_PYADM1_FALLBACK_TYPES: frozenset[str] = frozenset({"two_phase", "tpad", "batch", "uasb", "plug_flow"})


def render_case_definition() -> None:
    """Renderiza seletores de tipo de reator, modo de alimentação, backend e modo de UI."""
    reactor_options = get_reactor_options()
    backend_options = get_backend_options()

    col1, col2, col3 = st.columns(3)
    with col1:
        st.selectbox(
            "Tipo de reator",
            options=list(reactor_options),
            format_func=lambda v: reactor_options[v],
            key="sim_reactor_type",
        )
    with col2:
        st.radio(
            "Modo de alimentação",
            options=["preset", "codigestion", "custom", "manual"],
            horizontal=True,
            format_func=lambda v: {
                "preset": "Preset nativo",
                "codigestion": "Co-digestão",
                "custom": "Personalizado",
                "manual": "Manual",
            }[v],
            key="sim_substrate_mode",
        )
    with col3:
        st.selectbox(
            "Backend",
            options=list(backend_options),
            format_func=lambda v: backend_options[v],
            key="sim_backend_choice",
        )

    st.radio(
        "Modo de operação",
        options=["operador", "especialista"],
        horizontal=True,
        format_func=lambda v: {
            "operador": "🔧 Operador (campos essenciais)",
            "especialista": "🔬 Especialista (todos os campos)",
        }[v],
        key="sim_ui_mode",
        help="Operador: campos essenciais. Especialista: parâmetros avançados visíveis.",
    )

    reactor_type = st.session_state.get("sim_reactor_type", "cstr")
    backend_choice = st.session_state.get("sim_backend_choice", "pyadm1")
    if reactor_type in _PYADM1_FALLBACK_TYPES and backend_choice == "pyadm1":
        st.warning(
            f"PyADM1 suporta apenas CSTR. Para `{reactor_type}`, o backend será `reduced`. "
            "Use `full` para ADM1 nativo."
        )
    elif reactor_type != "cstr" and backend_choice == "full":
        st.info(f"Backend `full` selecionado — suporta `{reactor_type}` com ADM1 nativo completo.")
