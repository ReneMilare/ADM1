from __future__ import annotations

from _bootstrap import ensure_project_root

ensure_project_root()

import streamlit as st
from webapp.components.status_cards import render_issue_messages, render_sidebar_panel, render_summary_cards
from webapp.components.tables import render_frame
from webapp.services.health import collect_health_snapshot
from webapp.services.scenario_service import (
    catalog_rows,
    comparison_csv_bytes,
    comparison_frame,
    fallback_rows,
    filter_results,
    filter_values,
    load_saved_results,
    scenario_option_labels,
    selected_results,
)
from webapp.state.session_state import ensure_session_state
from webapp.utils.page_config import configure_page, render_page_header

configure_page("Comparar Cenarios")
ensure_session_state()
snapshot = collect_health_snapshot()
st.session_state["recent_page"] = "comparar_cenarios"
render_sidebar_panel(snapshot, current_page="Comparar Cenarios")
render_page_header(
    eyebrow="Fase W3",
    title="Comparar Cenarios",
    description="Catálogo filtrável de cenários persistidos, comparação KPI a KPI e sobreposição das curvas principais para estudo técnico lado a lado.",
)

if snapshot["issues"]:
    render_issue_messages(snapshot)
render_summary_cards(snapshot)

results, load_errors = load_saved_results()
for error in load_errors:
    st.warning(f"Falha ao carregar cenário salvo: {error}")

if not results:
    st.info("Nenhum cenário persistido foi encontrado em `simulator/runs/`. Rode pelo menos duas simulações com a opção de persistir cenário habilitada para usar a comparação W3.")
    st.stop()

filters = filter_values(results)
filter_col1, filter_col2, filter_col3 = st.columns(3)
with filter_col1:
    selected_reactors = st.multiselect(
        "Filtrar por reator",
        options=filters["reactors"],
        default=filters["reactors"],
    )
with filter_col2:
    selected_backends = st.multiselect(
        "Filtrar por backend usado",
        options=filters["backends"],
        default=filters["backends"],
    )
with filter_col3:
    selected_substrates = st.multiselect(
        "Filtrar por substrato",
        options=filters["substrates"],
        default=filters["substrates"],
    )

search_col, fallback_col = st.columns((1.5, 0.9))
with search_col:
    search_text = st.text_input("Busca rápida", placeholder="simulation_id, reator, substrato ou backend")
with fallback_col:
    fallback_mode = st.selectbox(
        "Fallback",
        options=["all", "fallback_only", "no_fallback"],
        format_func=lambda value: {
            "all": "Todos",
            "fallback_only": "Somente com fallback",
            "no_fallback": "Somente sem fallback",
        }[value],
    )

filtered = filter_results(
    results,
    reactor_types=selected_reactors,
    backends=selected_backends,
    substrates=selected_substrates,
    fallback_mode=fallback_mode,
    search_text=search_text,
)

st.subheader("Catálogo filtrado")
st.caption("A tabela abaixo já deixa explícito quando o backend pedido não foi o backend efetivamente executado.")
render_frame(catalog_rows(filtered))

if not filtered:
    st.info("Nenhum cenário atende aos filtros atuais.")
    st.stop()

option_labels = scenario_option_labels(filtered)
default_selection = list(option_labels)[: min(3, len(option_labels))]
selected_ids = st.multiselect(
    "Cenários para comparar",
    options=list(option_labels),
    default=default_selection if len(default_selection) >= 2 else list(option_labels)[: min(2, len(option_labels))],
    format_func=lambda simulation_id: option_labels[simulation_id],
)

if len(selected_ids) < 2:
    st.info("Selecione pelo menos 2 cenários para habilitar a comparação lado a lado.")
    st.stop()

selected = selected_results(filtered, selected_ids)
selected_labels = scenario_option_labels(selected)

baseline_id = st.selectbox(
    "Cenário de referência para os deltas",
    options=[result.simulation_id for result in selected],
    format_func=lambda simulation_id: selected_labels[simulation_id],
)

comparison = comparison_frame(selected, baseline_id=baseline_id)
comparison_col1, comparison_col2, comparison_col3, comparison_col4 = st.columns(4)
comparison_col1.metric("Cenários selecionados", str(len(selected)))
comparison_col2.metric("Reatores distintos", str(len({result.reactor.reactor_type for result in selected})))
comparison_col3.metric("Backends usados", ", ".join(sorted({str(result.metadata.get('backend_used', result.simulation.backend)) for result in selected})))
comparison_col4.metric("Fallbacks detectados", str(sum(1 for result in selected if str(result.metadata.get('backend_requested', result.simulation.backend)) != str(result.metadata.get('backend_used', result.simulation.backend)))))

st.subheader("Tabela comparativa")
render_frame(comparison)
st.download_button(
    label="Baixar comparação CSV",
    data=comparison_csv_bytes(selected, baseline_id=baseline_id),
    file_name="scenario_comparison.csv",
    mime="text/csv",
    use_container_width=False,
)

fallback_info = fallback_rows(selected)
if fallback_info:
    st.subheader("Diferenças entre backend solicitado e executado")
    render_frame(fallback_info)

st.subheader("Curvas sobrepostas")
series_keys = st.multiselect(
    "Séries para sobrepor",
    options=list(SERIES_PLOT_OPTIONS),
    default=["methane_m3_day", "biogas_m3_day", "ph", "vfa_total"],
    format_func=lambda key: SERIES_PLOT_OPTIONS[key]["label"],
)
render_comparison_overlay_charts(selected, series_keys=series_keys, labels=selected_labels)
