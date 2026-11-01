from __future__ import annotations

from _bootstrap import ensure_project_root

ensure_project_root()

import streamlit as st

from simulator.paths import _safe_project_path
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
    delete_custom_substrate,
    delete_simulation_preset,
    export_workbench_state_bytes,
    get_preferences,
    list_custom_substrates,
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
    title="Configuracoes",
    description="Preferencias persistentes do workbench, gestao de presets do usuario, substratos personalizados e historicos locais para operar a ferramenta sem apoio constante do desenvolvedor.",
)
_render_flash()

if snapshot["issues"]:
    render_issue_messages(snapshot)
render_summary_cards(snapshot)
render_workflow_links(
    title="Fluxos relacionados",
    items=[
        {"path": "pages/01_Simular_Reator.py", "label": "Simular Reator", "caption": "Salvar e reaplicar presets do usuario."},
    ],
)
render_usage_guide(
    title="Como usar esta tela",
    summary="Aqui ficam as preferencias persistentes do workbench e a gestao dos itens salvos pela camada W7.",
    steps=[
        "Defina defaults tecnicos para reator, backend e exibicao da interface.",
        "Revise os presets do usuario salvos a partir da tela de simulacao.",
        "Gerencie substratos personalizados quando estiver consolidando entradas recorrentes.",
        "Limpe historicos quando quiser reiniciar a rotina de uso.",
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
        st.caption("Modelo reduzido: exploratório, use para tendências, não para dimensionamento.")
        ammonia_mode_options = {"simple": "Simples (sem FAN)", "fan": "Inibicao por amonia livre (FAN)"}
        ammonia_inhibition_mode_default = st.selectbox(
            "Modo de inibicao por amonia padrao",
            options=list(ammonia_mode_options),
            index=list(ammonia_mode_options).index(str(preferences.get("ammonia_inhibition_mode_default", "simple"))),
            format_func=lambda value: ammonia_mode_options[value],
        )
    with pref_col2:
        persist_by_default = st.checkbox("Persistir cenarios por padrao", value=bool(preferences.get("persist_scenarios_by_default", True)))
    with pref_col3:
        show_home_onboarding = st.checkbox("Mostrar onboarding na home", value=bool(preferences.get("show_home_onboarding", True)))

    submitted = st.form_submit_button("Salvar preferencias", width="stretch")

if submitted:
    save_preferences(
        {
            "default_reactor": default_reactor,
            "default_backend": default_backend,
            "ammonia_inhibition_mode_default": ammonia_inhibition_mode_default,
            "persist_scenarios_by_default": bool(persist_by_default),
            "show_home_onboarding": bool(show_home_onboarding),
        }
    )
    _queue_flash("Preferencias salvas com sucesso.")
    st.rerun()

st.subheader("Persistencia local do workbench")
meta_col1, meta_col2, meta_col3 = st.columns(3)
meta_col1.metric("Presets do usuario", str(len(list_simulation_presets())))
meta_col2.metric("Substratos personalizados", str(len(list_custom_substrates())))
meta_col3.metric("Simulacoes recentes", str(len(list_recent_simulations(limit=20))))
st.caption(f"Arquivo de estado local: `{_safe_project_path(STATE_PATH)}`")
st.download_button(
    label="Baixar workbench_state.json",
    data=export_workbench_state_bytes(),
    file_name="workbench_state.json",
    mime="application/json",
    width="content",
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
        if st.button("Excluir preset selecionado", width="stretch"):
            delete_simulation_preset(selected_preset)
            _queue_flash(f"Preset `{selected_preset}` excluido.")
            st.rerun()
    with preset_col2:
        if st.button("Limpar todos os presets", width="stretch"):
            clear_saved_items("simulation_presets")
            _queue_flash("Todos os presets foram removidos.")
            st.rerun()
else:
    st.caption("Nenhum preset do usuario foi salvo ainda.")

st.subheader("Substratos personalizados")
custom_substrates = list_custom_substrates()
if custom_substrates:
    substrate_rows = []
    for item in custom_substrates:
        substrate_rows.append(
            {
                "substrato": item.get("name"),
                "ph": item.get("ph"),
                "particulate_cod": item.get("particulate_cod"),
                "soluble_cod": item.get("soluble_cod"),
                "atualizado_em": item.get("updated_at"),
            }
        )
    render_frame(substrate_rows)
    selected_substrate = st.selectbox("Substrato para excluir", options=[str(item.get("name")) for item in custom_substrates])
    if st.button("Excluir substrato selecionado", width="stretch"):
        delete_custom_substrate(selected_substrate)
        _queue_flash(f"Substrato `{selected_substrate}` excluido.")
        st.rerun()
else:
    st.caption("Nenhum substrato personalizado foi salvo ainda.")

st.subheader("Simulacoes recentes")
recent_simulations = list_recent_simulations(limit=12)
if recent_simulations:
    render_frame(recent_simulations)
else:
    st.caption("As simulacoes mais recentes aparecerao aqui apos as primeiras execucoes com sucesso.")
if st.button("Limpar historico de simulacoes", width="stretch"):
    clear_saved_items("recent_simulations")
    st.rerun()
