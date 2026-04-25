from __future__ import annotations

from _bootstrap import ensure_project_root

ensure_project_root()

import streamlit as st

from simulator.design_pipeline import GOAL_WEIGHTS
from webapp.components.charts import render_design_score_charts
from webapp.components.status_cards import render_issue_messages, render_sidebar_panel, render_summary_cards
from webapp.components.tables import render_frame
from webapp.services.design_service import (
    candidate_frame,
    component_score_frame,
    design_json_bytes,
    get_backend_strategies,
    get_goal_description,
    get_goal_options,
    get_reactor_options,
    goal_weight_rows,
    interpretation_rows,
    run_design_study,
)
from webapp.services.health import collect_health_snapshot
from webapp.state.session_state import ensure_session_state
from webapp.utils.page_config import configure_page, render_page_header
from webapp.utils.presets import get_preset_bundle, get_substrate_options, preset_rows

configure_page("Design de Reator")
ensure_session_state()
snapshot = collect_health_snapshot()
st.session_state["recent_page"] = "design_de_reator"
render_sidebar_panel(snapshot, current_page="Design de Reator")
render_page_header(
    title="Design de Reator",
    description="Pipeline de design assistido ligado ao backend real: comparar candidatos, interpretar os scores e gerar uma recomendacao legivel para um usuario tecnico.",
)

if snapshot["issues"]:
    render_issue_messages(snapshot)
render_summary_cards(snapshot)

substrate_options = get_substrate_options()
goal_options = get_goal_options()
backend_strategies = get_backend_strategies()
reactor_options = get_reactor_options()

selector_col1, selector_col2, selector_col3 = st.columns((1.05, 1.1, 0.95))
with selector_col1:
    substrate_id = st.selectbox(
        "Preset de substrato",
        options=list(substrate_options),
        format_func=lambda value: substrate_options[value],
        key="design_substrate_id",
    )
with selector_col2:
    design_goal = st.selectbox(
        "Objetivo de design",
        options=list(goal_options),
        format_func=lambda value: goal_options[value],
        key="design_goal",
    )
with selector_col3:
    backend_strategy = st.selectbox(
        "Estrategia de backend",
        options=list(backend_strategies),
        format_func=lambda value: backend_strategies[value],
        key="design_backend_strategy",
    )

feed, operating, note_link = get_preset_bundle(substrate_id)

st.info("Para CSTR, `auto` continua em `pyadm1`. Use `full` explicitamente quando quiser forcar o ADM1 nativo do projeto no pipeline de design.")

context_col, form_col = st.columns((0.95, 1.4))
with context_col:
    st.subheader("Contexto do estudo")
    st.markdown(f"- Substrato: `{substrate_options[substrate_id]}`")
    _note_label = note_link.removeprefix("[[").removesuffix("]]") if note_link else ""
    st.markdown(f"- Nota tecnica: `{_note_label}`")
    st.markdown(f"- Feed: `{feed.name}`")
    st.caption(get_goal_description(design_goal))
    st.dataframe(
        [
            {"parametro": "Volume padrao", "valor": f"{operating.volume_m3:.1f} m3"},
            {"parametro": "Temperatura padrao", "valor": f"{operating.temperature_c:.1f} C"},
            {"parametro": "HRT padrao", "valor": f"{operating.hrt_days:.1f} d"},
            {"parametro": "Particulate COD", "valor": f"{feed.particulate_cod:.3f} kgCOD/m3"},
            {"parametro": "Soluble COD", "valor": f"{feed.soluble_cod:.3f} kgCOD/m3"},
            {"parametro": "Influent pH", "valor": f"{feed.ph:.2f}"},
        ],
        use_container_width=True,
        hide_index=True,
    )
with form_col:
    with st.form("design_pipeline_form"):
        reactor_candidates = st.multiselect(
            "Candidatos a comparar",
            options=list(reactor_options),
            default=list(reactor_options),
            format_func=lambda value: reactor_options[value],
        )
        left, right = st.columns(2)
        with left:
            volume_m3 = st.number_input("Volume [m3]", min_value=10.0, value=float(operating.volume_m3), step=50.0)
            temperature_c = st.number_input("Temperatura [C]", min_value=15.0, max_value=60.0, value=float(operating.temperature_c), step=0.5)
            hrt_days = st.number_input("HRT [dias]", min_value=0.5, value=float(operating.hrt_days), step=0.5)
        with right:
            duration_days = st.number_input("Duracao do estudo [dias]", min_value=5.0, value=45.0, step=1.0)
            evaluation_points = st.number_input("Pontos de avaliacao", min_value=31, max_value=401, value=181, step=10)
            persist_note = st.checkbox("Salvar Markdown do estudo em artefatos locais", value=False)
            note_title = st.text_input("Titulo do relatorio", value="") if persist_note else ""
        submitted = st.form_submit_button("Rodar design assistido")

if submitted:
    try:
        if not reactor_candidates:
            raise ValueError("Selecione pelo menos um reator candidato para o estudo.")
        with st.spinner("Rodando o estudo comparativo e consolidando os candidatos..."):
            report = run_design_study(
                substrate=substrate_id,
                design_goal=design_goal,
                backend=backend_strategy,
                reactor_candidates=reactor_candidates,
                volume_m3=float(volume_m3),
                temperature_c=float(temperature_c),
                hrt_days=float(hrt_days),
                duration_days=float(duration_days),
                evaluation_points=int(evaluation_points),
                persist_note=bool(persist_note),
                note_title=note_title,
            )
        st.toast("Estudo de design concluido.")
        st.session_state["latest_design"] = report
        st.session_state["latest_design_error"] = None
    except Exception as exc:
        st.session_state["latest_design"] = None
        st.session_state["latest_design_error"] = str(exc)

if st.session_state.get("latest_design_error"):
    st.error(st.session_state["latest_design_error"])

report = st.session_state.get("latest_design")
if report is not None:
    recommended_reactor = report["recommended_reactor"]
    recommended_backend = report["recommended_backend"]
    recommendation_reason = report["recommendation_reason"]
    note_path = report.get("note_path")
    candidates = report["candidates"]

    st.subheader("Recomendacao")
    metrics = st.columns(4)
    metrics[0].metric("Reator recomendado", recommended_reactor.upper())
    metrics[1].metric("Backend recomendado", str(recommended_backend))
    metrics[2].metric("Candidatos comparados", str(len(candidates)))
    metrics[3].metric("Objetivo", goal_options[report["design_goal"]])

    st.markdown(f"**Recomendacao principal:** `{recommended_reactor}` com backend `{recommended_backend}`.")
    st.markdown(f"**Justificativa:** {recommendation_reason}")
    if note_path:
        st.info(f"Relatorio Markdown salvo em `{note_path}`")

    fallback_candidates = [candidate for candidate in candidates if str(candidate.get('backend_requested')) != str(candidate.get('backend_used'))]
    if fallback_candidates:
        st.warning("Alguns candidatos rodaram com fallback de backend. Isso esta explicito na tabela comparativa abaixo.")
    if report.get("backend_policy_note"):
        st.warning(str(report["backend_policy_note"]))

    st.subheader("Leitura do objetivo")
    st.caption(get_goal_description(report["design_goal"]))
    weight_frame = render_frame(
        [
            {
                "goal": report["design_goal"],
                **{component: value for component, value in GOAL_WEIGHTS[report["design_goal"]].items()},
            }
        ]
    )

    st.subheader("Ranking e componentes do score")
    render_design_score_charts(report)

    st.subheader("Tabela comparativa dos candidatos")
    render_frame(candidate_frame(report))

    st.subheader("Interpretacao dos candidatos")
    render_frame(interpretation_rows(report))

    st.subheader("Componentes do score")
    render_frame(component_score_frame(report))

    st.download_button(
        label="Baixar estudo em JSON",
        data=design_json_bytes(report),
        file_name="design_study.json",
        mime="application/json",
        use_container_width=False,
    )
else:
    st.subheader("Referencias disponiveis")
    left, right = st.columns(2)
    with left:
        st.markdown("**Presets de substrato**")
        render_frame(preset_rows())
    with right:
        st.markdown("**Objetivos de design**")
        render_frame(goal_weight_rows())
    st.info("Configure o estudo e clique em `Rodar design assistido` para comparar `cstr`, `uasb` e `plug_flow` com o pipeline do projeto.")
