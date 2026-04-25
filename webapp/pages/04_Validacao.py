from __future__ import annotations

from _bootstrap import ensure_project_root

ensure_project_root()

import streamlit as st

from webapp.components.charts import render_literature_validation_charts, render_phase3_validation_charts
from webapp.components.status_cards import render_issue_messages, render_sidebar_panel, render_summary_cards
from webapp.components.tables import render_frame
from webapp.services.health import collect_health_snapshot
from webapp.services.validation_service import (
    artifact_bytes,
    get_openmodelica_status,
    literature_comparison_frame,
    load_latest_literature_bundle,
    load_latest_phase3_bundle,
    markdown_artifact_text,
    phase3_metric_frame,
    phase3_next_steps,
    phase3_runtime_frame,
    run_literature_workflow,
    run_phase3_workflow,
)
from webapp.state.session_state import ensure_session_state
from webapp.utils.page_config import configure_page, render_page_header

configure_page("Validacao")
ensure_session_state()
snapshot = collect_health_snapshot()
st.session_state["recent_page"] = "validacao"
render_sidebar_panel(snapshot, current_page="Validacao")
render_page_header(
    title="Validacao",
    description="Execucao e leitura tecnica das validacoes locais do projeto: benchmark interno, benchmark BSM2 e estado atual da toolchain OpenModelica.",
)

if snapshot["issues"]:
    render_issue_messages(snapshot)
render_summary_cards(snapshot)

if st.session_state["latest_phase3_validation"] is None:
    st.session_state["latest_phase3_validation"] = load_latest_phase3_bundle()
if st.session_state["latest_literature_validation"] is None:
    st.session_state["latest_literature_validation"] = load_latest_literature_bundle()

openmodelica_status = get_openmodelica_status()

controls_col1, controls_col2 = st.columns(2)
with controls_col1:
    st.subheader("Executar validacao da Fase 3")
    include_openmodelica = st.checkbox("Incluir checagem OpenModelica e export de cenarios", value=False)
    if st.button("Rodar validacao Fase 3", use_container_width=True):
        with st.spinner("Executando benchmark local e consolidando a validacao da Fase 3..."):
            try:
                st.session_state["latest_phase3_validation"] = run_phase3_workflow(include_openmodelica=include_openmodelica)
                st.session_state["latest_phase3_validation_error"] = None
            except Exception as exc:
                st.session_state["latest_phase3_validation_error"] = str(exc)
with controls_col2:
    st.subheader("Executar validacao contra literatura")
    if st.button("Rodar validacao BSM2", use_container_width=True):
        with st.spinner("Executando a validacao contra a literatura BSM2..."):
            try:
                st.session_state["latest_literature_validation"] = run_literature_workflow()
                st.session_state["latest_literature_validation_error"] = None
            except Exception as exc:
                st.session_state["latest_literature_validation_error"] = str(exc)

if st.session_state.get("latest_phase3_validation_error"):
    st.error(st.session_state["latest_phase3_validation_error"])
if st.session_state.get("latest_literature_validation_error"):
    st.error(st.session_state["latest_literature_validation_error"])

st.subheader("Status atual do OpenModelica")
status_col1, status_col2, status_col3 = st.columns(3)
status_col1.metric("Status", str(openmodelica_status.get("status")))
status_col2.metric("OMPython", "sim" if openmodelica_status.get("ompython_available") else "nao")
status_col3.metric("omc no PATH", "sim" if openmodelica_status.get("omc_available") else "nao")
render_frame(
    [
        {
            "status": openmodelica_status.get("status"),
            "ready": openmodelica_status.get("ready"),
            "ompython_session_ok": openmodelica_status.get("ompython_session_ok"),
            "omc_path": openmodelica_status.get("omc_path"),
            "omc_version": openmodelica_status.get("omc_version"),
            "modelica_files": len(openmodelica_status.get("modelica_files", [])),
        }
    ]
)
for note in openmodelica_status.get("notes", []):
    st.markdown(f"- {note}")

phase3_bundle = st.session_state.get("latest_phase3_validation")
literature_bundle = st.session_state.get("latest_literature_validation")

st.subheader("Benchmark interno e validacao da Fase 3")
if phase3_bundle and phase3_bundle.get("report"):
    phase3_report = phase3_bundle["report"]
    benchmark = phase3_report["benchmark"]
    conclusion = phase3_report["conclusion"]
    phase3_metrics = st.columns(4)
    phase3_metrics[0].metric("OpenModelica executado", "sim" if conclusion.get("openmodelica_executed") else "nao")
    phase3_metrics[1].metric("pyadm1 padrao global", "sim" if conclusion.get("promote_pyadm1_as_global_default") else "nao")
    phase3_metrics[2].metric("NRMSE metano", f"{benchmark['series_metrics']['methane_m3_day']['mean_nrmse_pct']:.2f}%")
    phase3_metrics[3].metric("Delta metano final", f"{benchmark['summary_metrics']['methane_final_m3_day']['mean_rel_delta_pct_vs_pyadm1']:.2f}%")

    st.markdown(f"**Racional atual:** {conclusion.get('rationale')}")
    render_phase3_validation_charts(phase3_report)

    details_col1, details_col2 = st.columns(2)
    with details_col1:
        st.markdown("**Runtime por backend**")
        render_frame(phase3_runtime_frame(phase3_report))
    with details_col2:
        st.markdown("**Métricas do benchmark**")
        render_frame(phase3_metric_frame(phase3_report))

    st.markdown("**Próximos passos sugeridos pelo runner**")
    for item in phase3_next_steps(phase3_report):
        st.markdown(f"- {item}")

    artifact_col1, artifact_col2 = st.columns(2)
    with artifact_col1:
        json_bytes = artifact_bytes(phase3_bundle.get("json_path"))
        if json_bytes is not None:
            st.download_button(
                label="Baixar phase3_validation.json",
                data=json_bytes,
                file_name=Path(str(phase3_bundle['json_path'])).name,
                mime="application/json",
            )
    with artifact_col2:
        md_bytes = artifact_bytes(phase3_bundle.get("markdown_path"))
        if md_bytes is not None:
            st.download_button(
                label="Baixar phase3_validation.md",
                data=md_bytes,
                file_name=Path(str(phase3_bundle['markdown_path'])).name,
                mime="text/markdown",
            )

    markdown_preview = markdown_artifact_text(phase3_bundle.get("markdown_path"))
    if markdown_preview:
        with st.expander("Preview do markdown da Fase 3", expanded=False):
            st.code(markdown_preview[:6000], language="markdown")
else:
    st.info("Nenhum relatório válido da Fase 3 está carregado ainda.")

st.subheader("Validacao contra literatura BSM2")
st.warning("Nesta página, `pyadm1` é a referência técnica para CSTR. O `reduced` aparece apenas como fallback e comparação de desvio.")
if literature_bundle and literature_bundle.get("report"):
    literature_report = literature_bundle["report"]
    conclusion = literature_report["conclusion"]
    literature_metrics = st.columns(4)
    literature_metrics[0].metric("pyadm1 validado", "sim" if conclusion.get("pyadm1_matches_bsm2_reference") else "nao")
    literature_metrics[1].metric("reduced validado", "sim" if conclusion.get("reduced_matches_bsm2_reference") else "nao")
    literature_metrics[2].metric("Erro max pyadm1", f"{conclusion.get('pyadm1_max_rel_delta_pct'):.6f}%")
    literature_metrics[3].metric("Erro max reduced", f"{conclusion.get('reduced_max_rel_delta_pct'):.6f}%")

    st.markdown(f"**Conclusão:** {conclusion.get('summary')}")
    render_literature_validation_charts(literature_report)

    lit_col1, lit_col2 = st.columns(2)
    with lit_col1:
        st.markdown("**pyadm1 vs referência**")
        render_frame(literature_comparison_frame(literature_report, backend="pyadm1"))
    with lit_col2:
        st.markdown("**reduced vs referência**")
        render_frame(literature_comparison_frame(literature_report, backend="reduced"))

    artifact_col1, artifact_col2 = st.columns(2)
    with artifact_col1:
        json_bytes = artifact_bytes(literature_bundle.get("json_path"))
        if json_bytes is not None:
            st.download_button(
                label="Baixar literature_validation.json",
                data=json_bytes,
                file_name=Path(str(literature_bundle['json_path'])).name,
                mime="application/json",
            )
    with artifact_col2:
        md_bytes = artifact_bytes(literature_bundle.get("markdown_path"))
        if md_bytes is not None:
            st.download_button(
                label="Baixar literature_validation.md",
                data=md_bytes,
                file_name=Path(str(literature_bundle['markdown_path'])).name,
                mime="text/markdown",
            )
    markdown_preview = markdown_artifact_text(literature_bundle.get("markdown_path"))
    if markdown_preview:
        with st.expander("Preview do markdown da literatura", expanded=False):
            st.code(markdown_preview[:6000], language="markdown")
else:
    st.info("Nenhum relatório válido da literatura está carregado ainda.")
