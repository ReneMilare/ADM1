from __future__ import annotations

from _bootstrap import ensure_project_root

ensure_project_root()

import io

import pandas as pd
import streamlit as st

from webapp.components.charts import SERIES_PLOT_OPTIONS, render_comparison_overlay_charts
from webapp.components.status_cards import render_issue_messages, render_sidebar_panel, render_summary_cards
from webapp.components.tables import render_frame
from webapp.features.scenario_actions import duplicate_scenario_action, get_scenario_diff
from webapp.services.health import collect_health_snapshot
from webapp.services.scenario_service import (
    catalog_rows,
    comparison_csv_bytes,
    comparison_frame,
    fallback_rows,
    filter_results,
    filter_values,
    load_saved_results,
    reduced_is_exploratory_for_results,
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

if reduced_is_exploratory_for_results(selected):
    st.warning("Comparacoes com `reduced` ao lado de `pyadm1` ou `full` devem ser lidas apenas de forma operacional e exploratoria; nao servem como validacao matematica do backend `full`.")

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

# ─── Comparação detalhada (diff) ──────────────────────────────────────────────

st.divider()
st.subheader("Comparação detalhada (diff)")
st.caption("Escolha dois dos cenários selecionados acima para ver as diferenças campo a campo.")

selected_id_list = [r.simulation_id for r in selected]
diff_col_a, diff_col_b = st.columns(2)
with diff_col_a:
    diff_id_a = st.selectbox(
        "Cenário A",
        options=selected_id_list,
        index=0,
        format_func=lambda sid: selected_labels.get(sid, sid),
        key="diff_select_a",
    )
with diff_col_b:
    default_b_index = min(1, len(selected_id_list) - 1)
    diff_id_b = st.selectbox(
        "Cenário B",
        options=selected_id_list,
        index=default_b_index,
        format_func=lambda sid: selected_labels.get(sid, sid),
        key="diff_select_b",
    )

if diff_id_a == diff_id_b:
    st.info("Selecione dois cenários diferentes para calcular o diff.")
else:
    diff = get_scenario_diff(diff_id_a, diff_id_b)
    if diff is None:
        st.error("Não foi possível carregar um ou ambos os cenários para o diff.")
    elif not diff["has_changes"]:
        st.success("Os cenários são idênticos nos campos comparados.")
    else:
        # Inputs e operação
        if diff["inputs"] or diff["operating"]:
            st.markdown("**Inputs e operação — campos alterados**")
            table_rows = []
            for field_name, vals in diff["inputs"].items():
                table_rows.append({"seção": "feed", "campo": field_name, "A": vals["a"], "B": vals["b"]})
            for field_name, vals in diff["operating"].items():
                table_rows.append({"seção": "operação", "campo": field_name, "A": vals["a"], "B": vals["b"]})
            render_frame(table_rows)

        # Backend
        if diff["backend"]:
            bd = diff["backend"]
            req_changed = bd["requested"]["a"] != bd["requested"]["b"]
            used_changed = bd["used"]["a"] != bd["used"]["b"]
            backend_lines = []
            if req_changed:
                backend_lines.append(f"Backend solicitado: **{bd['requested']['a']}** → **{bd['requested']['b']}**")
            if used_changed:
                backend_lines.append(f"Backend executado: **{bd['used']['a']}** → **{bd['used']['b']}**")
            fallback_a = bd["requested"]["a"] != bd["used"]["a"]
            fallback_b = bd["requested"]["b"] != bd["used"]["b"]
            msg = "  \n".join(backend_lines)
            if fallback_a or fallback_b:
                st.warning(f"Mudança de backend envolve fallback:  \n{msg}")
            else:
                st.info(f"Mudança de backend:  \n{msg}")

        # Extensões
        ext = diff["extensions"]
        if ext["added"] or ext["removed"]:
            ext_col1, ext_col2 = st.columns(2)
            with ext_col1:
                if ext["added"]:
                    st.markdown("**Extensões adicionadas em B:**")
                    for e in ext["added"]:
                        st.markdown(f"- `{e}`")
            with ext_col2:
                if ext["removed"]:
                    st.markdown("**Extensões removidas de B:**")
                    for e in ext["removed"]:
                        st.markdown(f"- `{e}`")

        # KPIs
        if diff["kpis"]:
            st.markdown("**KPIs**")
            _KPI_LABELS = {
                "methane_final_m3_day": ("Metano final", "m³/d", True),
                "biogas_final_m3_day": ("Biogás final", "m³/d", True),
                "ph_final": ("pH final", "", None),
                "vfa_final": ("VFA final", "kgCOD/m³", False),
                "effluent_cod_final": ("COD efluente final", "kgCOD/m³", False),
                "stability_index": ("Índice de estabilidade", "", True),
            }
            kpi_cols = st.columns(min(len(diff["kpis"]), 3))
            for col_idx, (kpi_name, kpi_vals) in enumerate(diff["kpis"].items()):
                label, unit, higher_is_better = _KPI_LABELS.get(kpi_name, (kpi_name, "", None))
                val_a = kpi_vals["a"]
                val_b = kpi_vals["b"]
                if "delta_pct" in kpi_vals:
                    delta_val = kpi_vals["delta_pct"]
                    delta_str = f"{delta_val:+.2f}%" if delta_val is not None else ""
                    delta_color = "normal"
                    if higher_is_better is not None and delta_val is not None:
                        improved = (delta_val > 0) == higher_is_better
                        delta_color = "normal" if improved else "inverse"
                elif "delta_abs" in kpi_vals:
                    delta_val = kpi_vals["delta_abs"]
                    delta_str = f"{delta_val:+.4f}" if delta_val is not None else ""
                    delta_color = "normal"
                else:
                    delta_str = ""
                    delta_color = "normal"
                unit_str = f" {unit}" if unit else ""
                with kpi_cols[col_idx % len(kpi_cols)]:
                    st.metric(
                        label=f"{label}{unit_str}",
                        value=f"{val_b:.3f}",
                        delta=delta_str,
                        delta_color=delta_color,
                        help=f"A={val_a:.4f}  B={val_b:.4f}",
                    )

        # Warnings
        warn_a = diff["warnings"]["a"]
        warn_b = diff["warnings"]["b"]
        if warn_a or warn_b:
            st.markdown("**Warnings**")
            wcol1, wcol2 = st.columns(2)
            with wcol1:
                st.markdown(f"**A** (`{diff_id_a}`)")
                if warn_a:
                    for w in warn_a:
                        st.warning(w)
                else:
                    st.caption("Sem warnings.")
            with wcol2:
                st.markdown(f"**B** (`{diff_id_b}`)")
                if warn_b:
                    for w in warn_b:
                        st.warning(w)
                else:
                    st.caption("Sem warnings.")

    # Exportar diff como CSV (mesmo sem mudanças, sempre disponível)
    if diff is not None:
        csv_rows = []
        if diff["inputs"]:
            for fld, vals in diff["inputs"].items():
                csv_rows.append({"secao": "feed", "campo": fld, "valor_A": vals["a"], "valor_B": vals["b"], "delta": None})
        if diff["operating"]:
            for fld, vals in diff["operating"].items():
                csv_rows.append({"secao": "operacao", "campo": fld, "valor_A": vals["a"], "valor_B": vals["b"], "delta": None})
        if diff["backend"]:
            bd = diff["backend"]
            csv_rows.append({"secao": "backend", "campo": "requested", "valor_A": bd["requested"]["a"], "valor_B": bd["requested"]["b"], "delta": None})
            csv_rows.append({"secao": "backend", "campo": "used", "valor_A": bd["used"]["a"], "valor_B": bd["used"]["b"], "delta": None})
        for e in diff["extensions"]["added"]:
            csv_rows.append({"secao": "extensoes", "campo": "adicionada_em_B", "valor_A": None, "valor_B": e, "delta": None})
        for e in diff["extensions"]["removed"]:
            csv_rows.append({"secao": "extensoes", "campo": "removida_de_B", "valor_A": e, "valor_B": None, "delta": None})
        for kpi_name, kpi_vals in diff["kpis"].items():
            delta = kpi_vals.get("delta_pct") if "delta_pct" in kpi_vals else kpi_vals.get("delta_abs")
            csv_rows.append({"secao": "kpi", "campo": kpi_name, "valor_A": kpi_vals["a"], "valor_B": kpi_vals["b"], "delta": delta})
        buf = io.StringIO()
        pd.DataFrame(csv_rows or [{"secao": "sem_mudancas", "campo": "", "valor_A": "", "valor_B": "", "delta": ""}]).to_csv(buf, index=False)
        st.download_button(
            label="Exportar diff como CSV",
            data=buf.getvalue().encode("utf-8"),
            file_name=f"diff_{diff_id_a}_vs_{diff_id_b}.csv",
            mime="text/csv",
        )

        # ── Relatório técnico do cenário A ─────────────────────────────────────

        st.divider()
        st.markdown("**Relatório técnico — Cenário A**")
        _result_a = next((r for r in selected if r.simulation_id == diff_id_a), None)
        if _result_a is not None:
            from webapp.features.report_actions import export_report, generate_report, render_markdown
            _rep_payload = generate_report(
                _result_a,
                scenario_id=diff_id_a,
                baseline_id=diff_id_b,
            )
            _rep_md = render_markdown(_rep_payload)
            _rep_date = _rep_payload.generated_at[:10]
            _rep_filename = f"Relatorio_Sim_{diff_id_a}_{_rep_date}.md"

            _rcol1, _rcol2 = st.columns(2)
            with _rcol1:
                if st.button(
                    "📄 Salvar relatório do cenário A",
                    key=f"rep_report_a_{diff_id_a}",
                    use_container_width=True,
                ):
                    _rpath, _rerr = export_report(_rep_payload)
                    if _rpath:
                        st.success(f"Relatório salvo em `{_rpath}`.")
                    else:
                        st.error(f"Falha ao exportar relatório: {_rerr}")
            with _rcol2:
                st.download_button(
                    label="⬇ Baixar relatório do cenário A",
                    data=_rep_md.encode("utf-8"),
                    file_name=_rep_filename,
                    mime="text/markdown",
                    use_container_width=True,
                    key=f"rep_dl_a_{diff_id_a}",
                )

# ─── Duplicar cenários ─────────────────────────────────────────────────────────

st.divider()
st.subheader("Duplicar cenário")
dup_col1, dup_col2 = st.columns(2)
with dup_col1:
    if st.button(f"Duplicar cenário A ({diff_id_a})", use_container_width=True):
        new_id, dup_err = duplicate_scenario_action(diff_id_a)
        if new_id:
            st.success(f"Cenário duplicado com sucesso. Novo ID: `{new_id}`")
        else:
            st.error(dup_err or "Falha ao duplicar o cenário A.")
with dup_col2:
    if diff_id_a != diff_id_b:
        if st.button(f"Duplicar cenário B ({diff_id_b})", use_container_width=True):
            new_id, dup_err = duplicate_scenario_action(diff_id_b)
            if new_id:
                st.success(f"Cenário duplicado com sucesso. Novo ID: `{new_id}`")
            else:
                st.error(dup_err or "Falha ao duplicar o cenário B.")
