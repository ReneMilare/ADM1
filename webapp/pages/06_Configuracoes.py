from __future__ import annotations

from _bootstrap import ensure_project_root

ensure_project_root()

import streamlit as st

from webapp.components.status_cards import (
    render_issue_messages,
    render_sidebar_panel,
    render_summary_cards,
    render_usage_guide,
    render_workflow_links,
)
from webapp.components.tables import render_frame
from webapp.services.health import collect_health_snapshot
from webapp.services.preferences_service import (
    STATE_PATH,
    clear_saved_items,
    delete_simulation_preset,
    export_workbench_state_bytes,
    get_preferences,
    list_favorite_queries,
    list_recent_queries,
    list_recent_simulations,
    list_simulation_presets,
    save_preferences,
)
from webapp.services.simulation_service import get_backend_options, get_reactor_options
from webapp.state.session_state import ensure_session_state
from webapp.utils.page_config import configure_page, render_page_header

FLASH_KEY = "configuracoes_flash"


def _queue_flash(message: str) -> None:
    st.session_state[FLASH_KEY] = message


def _render_flash() -> None:
    message = st.session_state.pop(FLASH_KEY, None)
    if message:
        st.toast(message)


configure_page("Configuracoes")
ensure_session_state()
snapshot = collect_health_snapshot()
st.session_state["recent_page"] = "configuracoes"
render_sidebar_panel(snapshot, current_page="Configuracoes")
render_page_header(
    eyebrow="Fase W7",
    title="Configuracoes",
    description="Preferencias persistentes do workbench, gestao de presets do usuario, favoritos e historicos recentes para operar a ferramenta sem apoio constante do desenvolvedor.",
)
_render_flash()

if snapshot["issues"]:
    render_issue_messages(snapshot)
render_summary_cards(snapshot)
render_workflow_links(
    title="Fluxos relacionados",
    items=[
        {"path": "pages/01_Simular_Reator.py", "label": "Simular Reator", "caption": "Salvar e reaplicar presets do usuario."},
        {"path": "pages/05_Consulta_Tecnica.py", "label": "Consulta Tecnica", "caption": "Gerar favoritos e historico de perguntas."},
    ],
)
render_usage_guide(
    title="Como usar esta tela",
    summary="Aqui ficam as preferencias persistentes do workbench e a gestao dos itens salvos pela camada W7.",
    steps=[
        "Defina defaults tecnicos para reator, backend e profundidade da busca tecnica.",
        "Revise os presets do usuario salvos a partir da tela de simulacao.",
        "Limpe favoritos e historicos quando quiser reiniciar a rotina de uso.",
    ],
    tips=[
        "As alteracoes sao persistidas localmente em JSON na pasta `webapp/user_data/`.",
        "Limpar historicos nao afeta os cenarios persistidos em `simulator/runs/`.",
    ],
)

preferences = get_preferences()
reactor_options = get_reactor_options()
backend_options = get_backend_options()

with st.form("preferences_form"):
    pref_col1, pref_col2, pref_col3 = st.columns(3)
    with pref_col1:
        default_reactor = st.selectbox(
            "Reator padrao",
            options=list(reactor_options),
            index=list(reactor_options).index(str(preferences.get("default_reactor", "cstr"))),
            format_func=lambda value: reactor_options[value],
        )
        default_backend = st.selectbox(
            "Backend padrao da UI",
            options=list(backend_options),
            index=list(backend_options).index(str(preferences.get("default_backend", "full"))),
            format_func=lambda value: backend_options[value],
        )
        ammonia_mode_options = {"simple": "Simples (sem FAN)", "fan": "Inibicao por amonia livre (FAN)"}
        ammonia_inhibition_mode_default = st.selectbox(
            "Modo de inibicao por amonia padrao",
            options=list(ammonia_mode_options),
            index=list(ammonia_mode_options).index(str(preferences.get("ammonia_inhibition_mode_default", "simple"))),
            format_func=lambda value: ammonia_mode_options[value],
        )
    with pref_col2:
        default_top_k = st.slider("Top K padrao da busca tecnica", min_value=3, max_value=8, value=int(preferences.get("default_top_k", 5)), step=1)
        persist_by_default = st.checkbox("Persistir cenarios por padrao", value=bool(preferences.get("persist_scenarios_by_default", True)))
    with pref_col3:
        show_home_onboarding = st.checkbox("Mostrar onboarding na home", value=bool(preferences.get("show_home_onboarding", True)))
        auto_expand_top_result = st.checkbox("Expandir automaticamente o top 1 na busca tecnica", value=bool(preferences.get("auto_expand_top_result", True)))

    submitted = st.form_submit_button("Salvar preferencias", use_container_width=True)

if submitted:
    save_preferences(
        {
            "default_reactor": default_reactor,
            "default_backend": default_backend,
            "ammonia_inhibition_mode_default": ammonia_inhibition_mode_default,
            "default_top_k": int(default_top_k),
            "persist_scenarios_by_default": bool(persist_by_default),
            "show_home_onboarding": bool(show_home_onboarding),
            "auto_expand_top_result": bool(auto_expand_top_result),
        }
    )
    _queue_flash("Preferencias salvas com sucesso.")
    st.rerun()

st.subheader("Persistencia local do workbench")
meta_col1, meta_col2, meta_col3 = st.columns(3)
meta_col1.metric("Presets do usuario", str(len(list_simulation_presets())))
meta_col2.metric("Consultas favoritas", str(len(list_favorite_queries())))
meta_col3.metric("Consultas recentes", str(len(list_recent_queries(limit=20))))
st.caption(f"Arquivo de estado local: `{STATE_PATH}`")
st.download_button(
    label="Baixar workbench_state.json",
    data=export_workbench_state_bytes(),
    file_name="workbench_state.json",
    mime="application/json",
    use_container_width=False,
)

st.subheader("Presets do usuario")
presets = list_simulation_presets()
if presets:
    preset_table = []
    for item in presets:
        summary = item.get("summary", {}) if isinstance(item.get("summary"), dict) else {}
        preset_table.append(
            {
                "preset": item.get("name"),
                "reator": summary.get("reactor_type"),
                "modo": summary.get("substrate_mode"),
                "substrato": summary.get("preset_id") or "manual",
                "backend": summary.get("backend_choice"),
                "atualizado_em": item.get("updated_at"),
            }
        )
    render_frame(preset_table)
    selected_preset = st.selectbox("Preset para excluir", options=[str(item.get("name")) for item in presets])
    preset_col1, preset_col2 = st.columns(2)
    with preset_col1:
        if st.button("Excluir preset selecionado", use_container_width=True):
            delete_simulation_preset(selected_preset)
            _queue_flash(f"Preset `{selected_preset}` excluido.")
            st.rerun()
    with preset_col2:
        if st.button("Limpar todos os presets", use_container_width=True):
            clear_saved_items("simulation_presets")
            _queue_flash("Todos os presets foram removidos.")
            st.rerun()
else:
    st.caption("Nenhum preset do usuario foi salvo ainda.")

history_col1, history_col2 = st.columns(2)
with history_col1:
    st.subheader("Favoritos e consultas recentes")
    favorites = list_favorite_queries()
    if favorites:
        st.markdown("**Favoritos**")
        render_frame(favorites)
    else:
        st.caption("Nenhuma consulta favoritada ainda.")
    recent_queries = list_recent_queries(limit=12)
    if recent_queries:
        st.markdown("**Historico recente**")
        render_frame(recent_queries)
    else:
        st.caption("Nenhuma consulta recente registrada ainda.")
    query_col1, query_col2 = st.columns(2)
    with query_col1:
        if st.button("Limpar favoritos", use_container_width=True):
            clear_saved_items("favorite_queries")
            _queue_flash("Favoritos removidos.")
            st.rerun()
    with query_col2:
        if st.button("Limpar historico de consultas", use_container_width=True):
            clear_saved_items("recent_queries")
            _queue_flash("Historico de consultas limpo.")
            st.rerun()
with history_col2:
    st.subheader("Simulacoes recentes")
    recent_simulations = list_recent_simulations(limit=12)
    if recent_simulations:
        render_frame(recent_simulations)
    else:
        st.caption("As simulacoes mais recentes aparecerao aqui apos as primeiras execucoes com sucesso.")
    if st.button("Limpar historico de simulacoes", use_container_width=True):
        clear_saved_items("recent_simulations")
        st.rerun()