from __future__ import annotations

from _bootstrap import ensure_project_root

ensure_project_root()

import streamlit as st

from webapp.components.status_cards import (
    render_artifact_table,
    render_dependency_table,
    render_issue_messages,
    render_path_table,
    render_service_table,
    render_sidebar_panel,
    render_summary_cards,
    render_usage_guide,
    render_workflow_links,
)
from webapp.components.tables import render_frame
from webapp.services.health import collect_health_snapshot
from webapp.services.preferences_service import (
    get_preferences,
    list_favorite_queries,
    list_recent_queries,
    list_recent_simulations,
    list_simulation_presets,
)
from webapp.services.scenario_service import list_recent_artifacts
from webapp.state.session_state import ensure_session_state
from webapp.utils.page_config import configure_page, render_page_header

configure_page("ADM1 Workbench")
ensure_session_state()
snapshot = collect_health_snapshot()
st.session_state["recent_page"] = "home"
preferences = get_preferences()
render_sidebar_panel(snapshot, current_page="Visao geral")
render_page_header(
    eyebrow="Fases W1 a W7",
    title="ADM1 Workbench",
    description="Interface local para simulacao, comparacao de cenarios, design assistido, validacao tecnica, consulta documental e operacao recorrente por presets, historico e configuracoes do usuario.",
)

if snapshot["issues"]:
    render_issue_messages(snapshot)
else:
    st.success("O shell web carregou sem bloqueios detectados no backend local.")

render_summary_cards(snapshot)
render_workflow_links(
    title="Abrir um fluxo agora",
    items=[
        {"path": "pages/01_Simular_Reator.py", "label": "Simular Reator", "caption": "Rodar um caso novo ou aplicar preset salvo."},
        {"path": "pages/02_Comparar_Cenarios.py", "label": "Comparar Cenarios", "caption": "Comparar casos persistidos lado a lado."},
        {"path": "pages/03_Design_de_Reator.py", "label": "Design de Reator", "caption": "Escolher o reator mais adequado ao objetivo."},
        {"path": "pages/04_Validacao.py", "label": "Validacao", "caption": "Checar benchmark interno e literatura."},
        {"path": "pages/05_Consulta_Tecnica.py", "label": "Consulta Tecnica", "caption": "Buscar trechos do acervo ADM1 com citacao."},
        {"path": "pages/06_Configuracoes.py", "label": "Configuracoes", "caption": "Gerenciar preferencias, presets e historico."},
    ],
)

if bool(preferences.get("show_home_onboarding", True)):
    render_usage_guide(
        title="Onboarding rapido",
        summary="A interface agora fecha o ciclo principal de uso para um engenheiro quimico sem depender do terminal na rotina diaria.",
        steps=[
            "Comece em `Simular Reator` para montar ou reaplicar um caso.",
            "Use `Comparar Cenarios` quando houver pelo menos dois cenarios persistidos.",
            "Consulte `Validacao` antes de tratar um numero como referencia tecnica externa.",
            "Passe por `Consulta Tecnica` para relacionar literatura, fonte/pagina e parametros do modelo.",
            "Ajuste defaults e limpe historicos em `Configuracoes` quando quiser estabilizar o uso recorrente.",
        ],
        tips=[
            "Graficos Plotly agora ficam com barra de ferramentas visivel para export em PNG.",
            "Presets do usuario e historicos ficam em `webapp/user_data/workbench_state.json`.",
        ],
    )

recent_simulations = list_recent_simulations(limit=6)
recent_queries = list_recent_queries(limit=6)
favorite_queries = list_favorite_queries()[:6]
saved_presets = list_simulation_presets()[:6]

left, right = st.columns((1.35, 1.0))
with left:
    st.subheader("O que esta pronto agora")
    st.markdown("- Simulacao completa com persistencia de cenarios e presets do usuario.")
    st.markdown("- Comparacao de cenarios com deltas e sobreposicao de curvas.")
    st.markdown("- Design assistido com ranking, interpretacao e export do estudo.")
    st.markdown("- Validacao tecnica com benchmark interno, benchmark BSM2 e artefatos baixaveis.")
    st.markdown("- Consulta ao RAG local com citacao por fonte/pagina, expansao de contexto e favoritos.")
with right:
    st.subheader("Camada W7")
    st.markdown("- Onboarding curto embutido na interface.")
    st.markdown("- Navegacao direta entre fluxos pelo sidebar e pela home.")
    st.markdown("- Configuracoes persistentes de backend, reator e busca tecnica.")
    st.markdown("- Historico recente e gestao local de presets/favoritos.")

activity_col1, activity_col2 = st.columns(2)
with activity_col1:
    st.subheader("Atividade recente")
    if recent_simulations:
        render_frame(recent_simulations)
    else:
        st.caption("As simulacoes mais recentes aparecerao aqui depois da primeira execucao com sucesso.")
with activity_col2:
    st.subheader("Consultas e favoritos")
    if recent_queries or favorite_queries:
        if favorite_queries:
            st.markdown("**Favoritas**")
            render_frame(favorite_queries)
        if recent_queries:
            st.markdown("**Recentes**")
            render_frame(recent_queries)
    else:
        st.caption("As consultas tecnicas recentes e favoritas aparecerao aqui depois do uso da tela `Consulta Tecnica`.")

st.subheader("Cenários recentes")
recent_artifacts = list_recent_artifacts(limit=5)
if recent_artifacts:
    render_frame(recent_artifacts)
    if len(recent_artifacts) >= 2:
        _id_a = recent_artifacts[0]["simulation_id"]
        _id_b = recent_artifacts[1]["simulation_id"]
        st.caption(f"Dois mais recentes: `{_id_a}` e `{_id_b}`")
        if hasattr(st, "page_link"):
            try:
                st.page_link("pages/02_Comparar_Cenarios.py", label="Comparar os 2 mais recentes →")
            except Exception:
                st.markdown("Acesse **Comparar Cenarios** para comparar os cenários acima.")
        else:
            st.markdown("Acesse **Comparar Cenarios** para comparar os cenários acima.")
else:
    st.caption("Os cenários persistidos mais recentes aparecerão aqui após a primeira simulação com persistência habilitada.")

st.subheader("Presets do usuario")
if saved_presets:
    preset_rows = []
    for item in saved_presets:
        summary = item.get("summary", {}) if isinstance(item.get("summary"), dict) else {}
        preset_rows.append(
            {
                "preset": item.get("name"),
                "reator": summary.get("reactor_type"),
                "modo": summary.get("substrate_mode"),
                "substrato": summary.get("preset_id") or "manual",
                "backend": summary.get("backend_choice"),
                "atualizado_em": item.get("updated_at"),
            }
        )
    render_frame(preset_rows)
else:
    st.caption("Salve configuracoes a partir da tela `Simular Reator` para reutilizar estudos recorrentes.")

st.subheader("Dependencias")
render_dependency_table(snapshot)

st.subheader("Servicos do backend")
render_service_table(snapshot)

st.subheader("Pastas e artefatos")
render_path_table(snapshot)
render_artifact_table(snapshot)

st.subheader("Como abrir a interface")
st.code("streamlit run webapp/app.py", language="bash")
st.caption("Se o pacote `streamlit` ainda nao estiver instalado, rode `pip install -r requirements.txt` no ambiente virtual do projeto.")