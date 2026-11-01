from __future__ import annotations

from _bootstrap import ensure_project_root

ensure_project_root()

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from simulator.digital_twin.demo import OUTPUT_COLUMNS
from simulator.digital_twin.scenarios import HIDDEN_TRUTH
from webapp.components.status_cards import render_sidebar_panel
from webapp.services.digital_twin_service import run_scenario
from webapp.services.health import collect_health_snapshot
from webapp.state.session_state import ensure_session_state
from webapp.utils.page_config import configure_page, render_page_header

configure_page("Gêmeo Digital")
ensure_session_state()
render_sidebar_panel(collect_health_snapshot(), current_page="Gêmeo Digital")
render_page_header(title="Gêmeo Digital", description="Compare uma planta sintética, suas medições e um gêmeo digital.")

SCENARIOS = {"overload_recovery": "Sobrecarga e recuperação", "steady_noisy": "Operação estável com ruído", "cold_snap_ammonia": "Queda de temperatura e amônia"}
ESTIMATORS = {"open_loop": "Malha aberta", "ukf": "UKF experimental"}
LABELS = dict(zip(OUTPUT_COLUMNS, ("Biogás seco [Nm³/d]", "Metano [fração seca]", "pH", "AGV [kg DQO/m³]", "Alcalinidade total [kmol carga/m³]", "NH4+-N [kg N/m³]")))

@st.cache_data(show_spinner=False)
def cached_run(name: str, influent: str, seed: int, duration: float, estimator: str) -> dict:
    return run_scenario(name, influent, seed, duration, estimator)

scenario = st.selectbox("Cenário", list(SCENARIOS), format_func=SCENARIOS.get)
influent = st.selectbox("Afluente do gêmeo", ["observed", "oracle"], format_func=lambda value: {"observed": "Observado", "oracle": "Oráculo"}[value])
st.caption("Observado: usa vazão e temperatura medidas e DQO semanal. Oráculo: usa o afluente verdadeiro da planta sintética.")
estimator = st.selectbox("Estimador", list(ESTIMATORS), format_func=ESTIMATORS.get)
st.caption("Malha aberta simula sem assimilar medições; o UKF experimental atualiza estados e parâmetros e leva cerca de 4–5 min para 120 dias.")
cols = st.columns(2)
duration = cols[0].number_input("Duração (dias)", min_value=1, max_value=3650, value=120)
seed = cols[1].number_input("Semente", min_value=0, max_value=2**32 - 1, value=0)
if st.button("Rodar cenário", type="primary"):
    with st.spinner("Executando planta e gêmeo..."):
        try:
            st.session_state["digital_twin_result"] = cached_run(scenario, influent, int(seed), float(duration), estimator)
        except Exception:
            st.error("Não foi possível executar o cenário. Verifique os parâmetros e tente novamente.")
result = st.session_state.get("digital_twin_result")
if result:
    st.subheader("Resultados")
    st.caption(f"Cenário: {SCENARIOS[result['scenario']]} · afluente: {result['influent']} · estimador: {ESTIMATORS[result['estimator']]}")
    for column in OUTPUT_COLUMNS:
        fig = go.Figure()
        for key, label, color, mode in (("plant", "Planta", "#999999", "lines"), ("twin", "Gêmeo", "#1f77b4", "lines"), ("measurements", "Medições", "#d62728", "markers")):
            frame = result["series"][key]
            fig.add_trace(go.Scatter(x=frame["time_days"], y=frame[column], name=label, mode=mode, line={"color": color}, marker={"color": color}))
        fig.update_layout(title=LABELS[column], xaxis_title="Tempo [dias]", yaxis_title=LABELS[column], margin=dict(l=10, r=10, t=50, b=10))
        st.plotly_chart(fig, width="stretch")
    if "parameters" in result["series"]:
        st.subheader("Parâmetros estimados")
        st.caption("A banda mostra ±2σ na escala logarítmica; o fator N verdadeiro nominal é 1.")
        history = result["series"]["parameters"]
        for name, label, truth in (("k_m_ac", "k_m_ac [d⁻¹]", HIDDEN_TRUTH["k_m_ac"]), ("nitrogen_factor", "Fator N do afluente", 1.0)):
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=history["time_days"], y=history[name + "_lower_2sigma"], mode="lines", line=dict(width=0), showlegend=False))
            fig.add_trace(go.Scatter(x=history["time_days"], y=history[name + "_upper_2sigma"], mode="lines", line=dict(width=0), fill="tonexty", fillcolor="rgba(31,119,180,0.2)", name="±2σ em log"))
            fig.add_trace(go.Scatter(x=history["time_days"], y=history[name], mode="lines", name="Estimativa", line=dict(color="#1f77b4")))
            fig.add_hline(y=truth, line_dash="dash", annotation_text="Valor verdadeiro")
            fig.update_layout(title=label, xaxis_title="Tempo [dias]", yaxis_title=label, margin=dict(l=10, r=10, t=50, b=10))
            st.plotly_chart(fig, width="stretch")
    st.subheader("Métricas de acompanhamento")
    st.caption("Erros do gêmeo em relação às medições, alinhadas por dia; viés = gêmeo − medição.")
    metrics = pd.DataFrame.from_dict(result["metrics"], orient="index").rename(index=LABELS, columns={"n": "N", "mape": "MAPE (%)", "rmse": "RMSE", "bias": "Viés"})
    st.dataframe(metrics[["N", "MAPE (%)", "RMSE", "Viés"]], width="stretch")
    st.subheader("Baixar dados")
    for key, label in (("plant", "planta"), ("twin", "gêmeo"), ("measurements", "medições")):
        st.download_button(f"Baixar {label} (CSV)", result["csv"][key], file_name=f"{key}.csv", mime="text/csv")

    if "parameters" in result["csv"]:
        st.download_button("Baixar parâmetros (CSV)", result["csv"]["parameters"], file_name="parameters.csv", mime="text/csv")
