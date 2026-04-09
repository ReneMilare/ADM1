"""Seção: Definição do caso — tipo de reator, modo de substrato, backend e modo UI."""
from __future__ import annotations

import streamlit as st

from webapp.services.simulation_service import get_backend_options, get_reactor_options

_PYADM1_FALLBACK_TYPES: frozenset[str] = frozenset({"two_phase", "tpad", "batch", "uasb", "plug_flow"})


def render_case_definition() -> None:
    """Renderiza seletores de tipo de reator, modo de alimentação, backend e modo de UI."""
    reactor_options = get_reactor_options()
    backend_options = get_backend_options()
    substrate_mode_options = ["preset", "codigestion", "custom", "manual"]
    ui_mode_options = ["operador", "especialista"]

    col1, col2, col3 = st.columns(3)
    with col1:
        current_reactor = str(st.session_state.get("sim_reactor_type", "cstr"))
        reactor_values = list(reactor_options)
        reactor_index = reactor_values.index(current_reactor) if current_reactor in reactor_values else 0
        selected_reactor = st.selectbox(
            "Tipo de reator",
            options=reactor_values,
            index=reactor_index,
            format_func=lambda v: reactor_options[v],
        )
        if selected_reactor != current_reactor:
            st.session_state["sim_reactor_type"] = selected_reactor
    with col2:
        current_substrate_mode = str(st.session_state.get("sim_substrate_mode", "preset"))
        selector_key = "sim_substrate_mode_selector"
        if st.session_state.get(selector_key) not in substrate_mode_options:
            st.session_state[selector_key] = current_substrate_mode
        substrate_mode_index = (
            substrate_mode_options.index(current_substrate_mode)
            if current_substrate_mode in substrate_mode_options
            else 0
        )
        selected_substrate_mode = st.radio(
            "Modo de alimentação",
            options=substrate_mode_options,
            index=substrate_mode_index,
            horizontal=True,
            key=selector_key,
            format_func=lambda v: {
                "preset": "Preset nativo",
                "codigestion": "Co-digestão",
                "custom": "Personalizado",
                "manual": "Manual",
            }[v],
        )
        if selected_substrate_mode != current_substrate_mode:
            st.session_state["sim_substrate_mode"] = selected_substrate_mode
    with col3:
        current_backend = str(st.session_state.get("sim_backend_choice", "full"))
        backend_values = list(backend_options)
        backend_index = backend_values.index(current_backend) if current_backend in backend_values else 0
        selected_backend = st.selectbox(
            "Backend",
            options=backend_values,
            index=backend_index,
            format_func=lambda v: backend_options[v],
        )
        if selected_backend != current_backend:
            st.session_state["sim_backend_choice"] = selected_backend

    current_ui_mode = str(st.session_state.get("sim_ui_mode", "operador"))
    ui_mode_index = ui_mode_options.index(current_ui_mode) if current_ui_mode in ui_mode_options else 0
    selected_ui_mode = st.radio(
        "Modo de operação",
        options=ui_mode_options,
        index=ui_mode_index,
        horizontal=True,
        format_func=lambda v: {
            "operador": "🔧 Operador (campos essenciais)",
            "especialista": "🔬 Especialista (todos os campos)",
        }[v],
        help="Operador: campos essenciais. Especialista: parâmetros avançados visíveis.",
    )
    if selected_ui_mode != current_ui_mode:
        st.session_state["sim_ui_mode"] = selected_ui_mode

    reactor_type = st.session_state.get("sim_reactor_type", "cstr")
    backend_choice = st.session_state.get("sim_backend_choice", "pyadm1")
    if reactor_type in _PYADM1_FALLBACK_TYPES and backend_choice == "pyadm1":
        st.warning(
            f"PyADM1 suporta apenas CSTR. Para `{reactor_type}`, o backend será `reduced`. "
            "Use `full` para ADM1 nativo."
        )
    elif reactor_type != "cstr" and backend_choice == "full":
        st.info(f"Backend `full` selecionado — suporta `{reactor_type}` com ADM1 nativo completo.")
