"""Seção: Área de resultado da simulação."""
from __future__ import annotations

from typing import Any

import streamlit as st

from webapp.components.charts import render_ammonia_charts, render_core_profile_charts, render_phase_profile_charts
from webapp.components.status_cards import render_simulation_kpis
from webapp.components.tables import render_frame, render_input_table, render_series_preview, render_summary_table
from webapp.services.simulation_service import (
    backend_comparison_frame,
    compare_backends_for_result,
    series_csv_bytes,
    summary_csv_bytes,
    summary_json_bytes,
)

_EXTENSION_DESCRIPTIONS: dict[str, str] = {
    "lactate": "E6 – Lactato: intermediário na fermentação de açúcares",
    "ethanol": "E10 – Etanol: intermediário na fermentação de açúcares",
    "phenolics": "E11 – Fenólicos: degradação de compostos fenólicos",
    "lcfa_adsorption": "E5 – Adsorção de LCFA: cinética de adsorção de ácidos graxos de cadeia longa",
    "srb": "E4 – SRB: redução de sulfato (competição com metanogênese)",
    "multi_population": "E12 – Multi-população: acetoclásticos e hidrogenotróficos divididos em populações",
    "phosphorus": "E7 – Fósforo: ciclo de P inorgânico, precipitação de estruvita (MAP) e calcita",
    "iron": "E8 – Ferro: redução de Fe(III), precipitação de FeS e vivianita",
    "microalgae": "E20 – Microalgas: X_alg + hidrólise tipo Contois",
    "syngas": "E15 – Syngas: CO→H₂ e CO→acetato com inibição de CO",
    "trace_elements": "E9 – Elementos-traço: Ni/Co/Fe com sulfetos, FeCO3 e limitação por metal livre",
    "pilot_tracer": "Traçador RTD: injeção de traçador inerte para caracterização de RTD",
}

_EXT_SERIES: dict[str, list[tuple[str, str]]] = {
    "srb": [
        ("S_SO4", "Sulfato S_SO4 [kmol/m³]"),
        ("S_H2S", "Sulfeto dissolvido S_H2S [kmolS/m³]"),
        ("S_gas_H2S", "H₂S no biogás S_gas_H2S [kmolS/m³]"),
        ("X_SRB_ac", "Biomassa SRB acetoclástica X_SRB_ac [kgCOD/m³]"),
        ("X_SRB_h2", "Biomassa SRB hidrogenotrófica X_SRB_h2 [kgCOD/m³]"),
        ("X_SRB_pro", "Biomassa SRB propionotrófica X_SRB_pro [kgCOD/m³]"),
        ("X_SRB_bu", "Biomassa SRB butirotrófica X_SRB_bu [kgCOD/m³]"),
    ],
    "lcfa_adsorption": [
        ("X_LCFA_ads", "LCFA adsorvido X_LCFA_ads [kgCOD/m³]"),
    ],
    "lactate": [
        ("S_lac", "Lactato S_lac [kgCOD/m³]"),
        ("X_lac", "Biomassa lactato X_lac [kgCOD/m³]"),
    ],
    "ethanol": [
        ("S_et", "Etanol S_et [kgCOD/m³]"),
        ("X_et", "Biomassa etanol X_et [kgCOD/m³]"),
    ],
    "phenolics": [
        ("S_phen", "Fenólicos S_phen [kgCOD/m³]"),
        ("X_phen", "Biomassa fenólicos X_phen [kgCOD/m³]"),
    ],
    "phosphorus": [
        ("S_IP", "Fósforo inorgânico S_IP [kmolP/m³]"),
        ("X_MAP", "Estruvita precipitada X_MAP [kmolP/m³]"),
        ("X_CaCO3", "Calcita precipitada X_CaCO3 [kmolC/m³]"),
        ("IP_MAP", "Índice de saturação estruvita IP_MAP [-]"),
        ("IP_CaCO3", "Índice de saturação calcita IP_CaCO3 [-]"),
    ],
    "iron": [
        ("S_Fe2", "Ferro(II) dissolvido S_Fe2 [kmolFe/m³]"),
        ("X_FeS", "FeS precipitado X_FeS [kmolFe/m³]"),
        ("X_VIV", "Vivianita precipitada X_VIV [kmolFe/m³]"),
        ("IP_FeS", "Índice de saturação FeS IP_FeS [-]"),
        ("IP_VIV", "Índice de saturação vivianita IP_VIV [-]"),
    ],
    "multi_population": [
        ("total_X_ac", "Biomassa acetoclástica total [kgCOD/m³]"),
        ("total_X_h2", "Biomassa hidrogenotrófica total [kgCOD/m³]"),
        ("fraction_oligotrophic_ac", "Fração oligótrofa ac [-]"),
        ("fraction_oligotrophic_h2", "Fração oligótrofa h2 [-]"),
        ("X_ac_1", "X_ac_1 oligótrofa [kgCOD/m³]"),
        ("X_ac_2", "X_ac_2 copiótrofa [kgCOD/m³]"),
        ("X_h2_1", "X_h2_1 oligótrofa [kgCOD/m³]"),
        ("X_h2_2", "X_h2_2 copiótrofa [kgCOD/m³]"),
    ],
    "pilot_tracer": [
        ("pilot_tracer_inventory", "Inventário do traçador [kgCOD/m³]"),
        ("pilot_tracer_fraction_remaining", "Fração remanescente [-]"),
    ],
    "microalgae": [
        ("X_alg", "Biomassa algal X_alg [kgCOD/m³]"),
        ("X_alg_conversion", "Conversão de X_alg [-]"),
        ("k_dis_alg_effective", "Taxa de desintegração efetiva k_dis_alg_eff [d⁻¹]"),
        ("hydrolysis_modifier_ch", "Modificador Contois carboidratos [-]"),
        ("hydrolysis_modifier_pr", "Modificador Contois proteínas [-]"),
        ("hydrolysis_modifier_li", "Modificador Contois lipídios [-]"),
        ("S_IN", "N inorgânico S_IN [kmolN/m³]"),
    ],
    "syngas": [
        ("S_CO", "CO dissolvido S_CO [kgCOD/m³]"),
        ("S_gas_CO", "CO no biogás S_gas_CO [kgCOD/m³]"),
        ("X_met_CO", "Biomassa carbóxidotrófica X_met_CO [kgCOD/m³]"),
        ("p_gas_CO_bar", "Pressão parcial CO [bar]"),
        ("CO_conversion", "Conversão de CO [-]"),
        ("p_gas_CH4_bar", "Pressão parcial CH4 [bar]"),
    ],
    "trace_elements": [
        ("S_Ni", "Ni dissolvido total S_Ni [kmolNi/m³]"),
        ("S_Ni_free", "Ni livre [kmolNi/m³]"),
        ("S_Co", "Co dissolvido total S_Co [kmolCo/m³]"),
        ("S_Co_free", "Co livre [kmolCo/m³]"),
        ("S_Fe2_te", "Fe(II) dissolvido S_Fe2_te [kmolFe/m³]"),
        ("X_NiS", "NiS precipitado X_NiS [kmolNi/m³]"),
        ("X_CoS", "CoS precipitado X_CoS [kmolCo/m³]"),
        ("X_FeS_te", "FeS precipitado X_FeS_te [kmolFe/m³]"),
        ("X_FeCO3", "FeCO3 precipitado X_FeCO3 [kmolFe/m³]"),
        ("Ni_complexation_fraction", "Fração complexada de Ni [-]"),
        ("Co_complexation_fraction", "Fração complexada de Co [-]"),
        ("Ni_bioavailability", "Bioavailability de Ni [-]"),
        ("Co_bioavailability", "Bioavailability de Co [-]"),
        ("Fe_bioavailability", "Bioavailability de Fe [-]"),
        ("TE_limitation_X_ac", "Limitação TE em X_ac [-]"),
        ("TE_limitation_X_h2", "Limitação TE em X_h2 [-]"),
        ("IP_NiS", "Índice de saturação NiS [-]"),
        ("IP_CoS", "Índice de saturação CoS [-]"),
        ("IP_FeS", "Índice de saturação FeS [-]"),
        ("IP_FeCO3", "Índice de saturação FeCO3 [-]"),
    ],
}


def render_result_area(result: Any, *, show_advanced: bool = False) -> None:
    """Renderiza a área completa de resultado em abas organizadas."""
    tab_resumo, tab_perfis, tab_diag, tab_ext, tab_export = st.tabs(
        ["📊 Resumo", "📈 Perfis", "🔧 Diagnóstico", "🧪 Extensões", "💾 Exportar"]
    )

    with tab_resumo:
        _render_summary(result)

    with tab_perfis:
        _render_profiles(result)

    with tab_diag:
        _render_diagnostics(result, show_advanced=show_advanced)

    with tab_ext:
        _render_extensions(result)

    with tab_export:
        _render_export(result, show_advanced=show_advanced)


# ── Seção Resumo ──────────────────────────────────────────────────────────────

def _render_summary(result: Any) -> None:
    render_simulation_kpis(result)

    _res_substrate_mode = result.metadata.get("substrate_mode", "")
    _res_hydraulic_mode = result.metadata.get("hydraulic_mode", "hrt")
    _res_q = result.metadata.get("effective_flow_rate_m3_day")
    _res_hrt = result.metadata.get("effective_hrt_days")
    _res_custom_name = result.metadata.get("custom_substrate_name")

    _summary_parts: list[str] = []
    if _res_substrate_mode == "preset":
        _summary_parts.append(f"Substrato: preset nativo `{result.metadata.get('substrate_preset', '—')}`")
    elif _res_substrate_mode == "custom":
        _summary_parts.append(f"Substrato: personalizado `{_res_custom_name or '—'}`")
    elif _res_substrate_mode == "codigestion":
        _summary_parts.append("Substrato: co-digestão")
    else:
        _summary_parts.append("Substrato: manual temporário")

    if _res_hydraulic_mode == "flow_rate" and _res_q and _res_hrt:
        _summary_parts.append(
            f"Hidráulico: definido por **Vazão Q = {_res_q:.1f} m³/dia** → HRT efetivo = {_res_hrt:.2f} dias"
        )
    elif _res_hrt:
        _summary_parts.append(
            f"Hidráulico: definido por **HRT = {_res_hrt:.2f} dias**"
            + (f" → Q efetivo = {_res_q:.1f} m³/dia" if _res_q else "")
        )

    if _summary_parts:
        st.caption(" | ".join(_summary_parts))

    # Extension KPIs
    _fan_series = result.series.get("free_ammonia_kgN_m3")
    _inh_ac = result.series.get("inh_nh3_acetoclastic")
    _cn = result.summary.cn_ratio if result.summary.cn_ratio is not None else result.metadata.get("cn_ratio")
    _blend_name = result.metadata.get("blend_name")

    if _fan_series or _cn or _blend_name:
        ext_cols = st.columns(4)
        col_idx = 0
        if _fan_series:
            ext_cols[col_idx].metric("Amônia livre final (FAN)", f"{_fan_series[-1]:.4f} kgN/m³")
            col_idx += 1
        if _inh_ac:
            ext_cols[col_idx].metric("Inibição acetoclástica", f"{_inh_ac[-1]:.1%}")
            col_idx += 1
        if _cn is not None:
            ext_cols[col_idx].metric("Razão C/N", f"{float(_cn):.1f}")
            col_idx += 1
        if _blend_name:
            _comps = result.metadata.get("blend_components", [])
            ext_cols[col_idx % 4].metric("Blend", str(_blend_name), delta=", ".join(str(c) for c in _comps) or None)

    st.divider()
    table_col1, table_col2 = st.columns((1.0, 1.1))
    with table_col1:
        render_summary_table(result)
    with table_col2:
        render_input_table(result)


# ── Seção Perfis ──────────────────────────────────────────────────────────────

def _render_profiles(result: Any) -> None:
    st.caption("Use a barra de ferramentas dos gráficos para exportar PNG, aplicar zoom ou inspecionar pontos.")
    render_core_profile_charts(result)

    if result.metadata.get("ammonia_inhibition_mode") == "fan":
        render_ammonia_charts(result)

    if result.reactor.reactor_type in ("two_phase", "tpad"):
        render_phase_profile_charts(result)

    render_series_preview(result)


# ── Seção Diagnóstico ─────────────────────────────────────────────────────────

def _render_diagnostics(result: Any, *, show_advanced: bool = False) -> None:
    _backend_used = str(result.metadata.get("backend_used", result.simulation.backend))
    _backend_requested = str(result.metadata.get("backend_requested", result.simulation.backend))
    _fallback_reason = result.metadata.get("fallback_reason")

    if _backend_used != _backend_requested:
        st.warning(
            f"Backend solicitado: `{_backend_requested}` — backend efetivo: `{_backend_used}`. "
            f"Motivo do fallback: {_fallback_reason or 'N/A'}"
        )
    else:
        st.info(f"Backend: `{_backend_used}`")

    if _backend_used == "full":
        _n_state = result.metadata.get("full_model_state_count")
        _n_dyn = result.metadata.get("full_model_dynamic_state_count")
        _n_alg = result.metadata.get("full_model_algebraic_state_count")
        _n_pseudo = result.metadata.get("full_model_pseudo_state_count")
        _n_seg = result.metadata.get("full_model_segment_count", result.metadata.get("segment_count", 1))
        _ode_dim = result.metadata.get("full_model_effective_ode_dimension")
        _exts = result.metadata.get("full_model_active_extensions", [])
        _runtime = result.metadata.get("full_model_runtime_seconds")
        _method = result.metadata.get("full_model_solver_method")
        _rtol = result.metadata.get("full_model_solver_rtol")
        _atol = result.metadata.get("full_model_solver_atol")
        _n_pts = result.metadata.get("full_model_time_grid_points")
        _nfev = result.metadata.get("full_model_solver_nfev")
        _njev = result.metadata.get("full_model_solver_njev")
        _nlu = result.metadata.get("full_model_solver_nlu")
        _ph_conv = result.metadata.get("full_model_ph_converged")
        _ph_iter = result.metadata.get("full_model_ph_iterations_max")

        if any(v is not None for v in [_n_state, _n_dyn, _ode_dim, _runtime]):
            _diag_cols = st.columns(4)
            if _n_state is not None:
                _diag_cols[0].metric("Estados totais", str(_n_state), help="Dimensão do vetor de estado interno.")
            if _n_dyn is not None:
                _diag_cols[1].metric("Estados dinâmicos (EDO)", str(_n_dyn), help="Estados integrados via EDO.")
            if _ode_dim is not None:
                _diag_cols[2].metric(
                    "Dimensão efetiva EDO", str(_ode_dim), help=f"n_din × n_seg = {_n_dyn} × {_n_seg}"
                )
            if _runtime is not None:
                _diag_cols[3].metric("Tempo de execução", f"{_runtime:.3f} s", help="Tempo total de integração.")

        if show_advanced:
            with st.expander("Diagnóstico técnico do solver full", expanded=False):
                st.markdown(
                    "O backend `full` integra numericamente as EDOs do ADM1 completo usando "
                    "`scipy.integrate.solve_ivp`. Os **estados dinâmicos** são integrados diretamente; "
                    "os **estados algébricos** (equilíbrio ácido-base) são resolvidos implicitamente a cada "
                    "passo de tempo via iteração de Newton."
                )
                _tech_rows = []
                for campo, valor, desc in [
                    ("Estados totais", _n_state, "Dimensão do vetor de estado completo"),
                    ("Estados dinâmicos (EDO)", _n_dyn, "Integrados via solve_ivp"),
                    ("Estados algébricos", _n_alg, "Equilíbrio ácido-base por iteração de Newton"),
                    ("Pseudo-estados", _n_pseudo, "Variáveis derivadas (pH, fluxo de gás)"),
                    ("Segmentos", _n_seg, "CSTRs em série (1 = CSTR/batch/UASB)"),
                    ("Dimensão efetiva EDO", _ode_dim, f"n_dyn × n_seg = {_n_dyn} × {_n_seg}"),
                ]:
                    if valor is not None:
                        _tech_rows.append({"campo": campo, "valor": str(valor), "descricao": desc})
                if _exts:
                    _tech_rows.append({"campo": "Extensões ativas", "valor": ", ".join(_exts), "descricao": "Módulos opcionais ativados"})
                for campo, valor, desc in [
                    ("Método solver", _method, "Integrador scipy (BDF recomendado para sistemas stiff)"),
                    ("rtol", f"{_rtol:.2e}" if _rtol is not None else None, "Critério de convergência relativo"),
                    ("atol", f"{_atol:.2e}" if _atol is not None else None, "Critério de convergência absoluto"),
                    ("Pontos de grade temporal", _n_pts, "Número de pontos de saída (t_eval)"),
                    ("nfev", _nfev, "Avaliações de função"),
                    ("njev", _njev, "Avaliações do Jacobiano"),
                    ("nlu", _nlu, "Decomposições LU"),
                    ("pH convergiu", "Sim" if _ph_conv else ("Não" if _ph_conv is not None else None), "Todos os passos de pH convergiram"),
                    ("Iterações máx. pH", _ph_iter, "Máximo de iterações usadas no solver de pH"),
                    ("Tempo de execução (s)", f"{_runtime:.4f}" if _runtime is not None else None, "Tempo total de integração numérica"),
                ]:
                    if valor is not None:
                        _tech_rows.append({"campo": campo, "valor": str(valor), "descricao": desc})
                if _tech_rows:
                    render_frame(_tech_rows)

    # Comparação de backends (CSTR apenas)
    if result.reactor.reactor_type == "cstr":
        st.divider()
        st.subheader("Comparação de backends neste caso")
        st.caption("Executa o mesmo CSTR com `pyadm1` e `full` para explicitar paridade, fallback e deltas dos KPIs.")
        compare_key = f"backend_compare_{result.simulation_id}"
        if st.button("Comparar `pyadm1` vs `full`", key=compare_key, use_container_width=False):
            with st.spinner("Comparando `pyadm1` e `full` para o mesmo caso CSTR..."):
                report = compare_backends_for_result(result, backends=("pyadm1", "full"))
            st.session_state["latest_backend_comparison"] = {
                "simulation_id": result.simulation_id,
                "report": report,
            }
        comparison_state = st.session_state.get("latest_backend_comparison")
        if (
            isinstance(comparison_state, dict)
            and comparison_state.get("simulation_id") == result.simulation_id
        ):
            comparison_report = comparison_state.get("report")
            if isinstance(comparison_report, dict):
                if comparison_report.get("note"):
                    st.warning(str(comparison_report["note"]))
                render_frame(backend_comparison_frame(comparison_report))


# ── Seção Extensões ───────────────────────────────────────────────────────────

def _render_extensions(result: Any) -> None:
    _ext_requested = result.metadata.get("full_extensions_requested") or []
    if not _ext_requested:
        st.info("Nenhuma extensão foi ativada nesta simulação.")
        return

    import plotly.graph_objects as go

    st.caption("Perfis temporais dos estados adicionados pelas extensões ativas.")
    for _ext_name in _ext_requested:
        _ext_series_defs = _EXT_SERIES.get(_ext_name, [])
        _available = [(key, label) for key, label in _ext_series_defs if key in result.series]
        if not _available:
            continue
        with st.expander(f"🔬 {_EXTENSION_DESCRIPTIONS.get(_ext_name, _ext_name)}", expanded=True):
            _t = result.time_days
            _cols = st.columns(min(len(_available), 2))
            for i, (skey, slabel) in enumerate(_available):
                _vals = result.series.get(skey, [])
                if _vals:
                    _fig = go.Figure()
                    _fig.add_trace(go.Scatter(x=_t, y=_vals, mode="lines", name=slabel))
                    _fig.update_layout(
                        xaxis_title="Tempo [dias]",
                        yaxis_title=slabel,
                        height=280,
                        margin={"t": 30, "b": 30, "l": 10, "r": 10},
                    )
                    _max_abs = max((abs(v) for v in _vals if v is not None), default=0.0)
                    if _max_abs > 0 and (_max_abs < 1e-3 or _max_abs > 1e4):
                        _fig.update_yaxes(exponentformat="power")
                        _fig.update_traces(hovertemplate="%{x:.2f}d<br>%{y:.3e}<extra></extra>")
                    _cols[i % 2].plotly_chart(_fig, use_container_width=True)

    # Extension KPI metrics
    _render_extension_kpis(result, _ext_requested)


def _render_extension_kpis(result: Any, ext_requested: list[str]) -> None:
    if "srb" in ext_requested:
        _so4_s = result.series.get("S_SO4")
        _h2s_s = result.series.get("S_H2S")
        if _so4_s or _h2s_s:
            srb_cols = st.columns(2)
            if _so4_s:
                srb_cols[0].metric("Sulfato efluente (S_SO4)", f"{_so4_s[-1]:.4f} kmol/m³")
            if _h2s_s:
                srb_cols[1].metric("Sulfeto efluente (S_H2S)", f"{_h2s_s[-1]:.4f} kmolS/m³")
        _srb_signal_keys = ("S_SO4", "S_H2S", "S_gas_H2S", "X_SRB_ac", "X_SRB_h2", "X_SRB_pro", "X_SRB_bu")
        _srb_signal_series = [result.series.get(key, []) for key in _srb_signal_keys if key in result.series]
        _srb_all_zero = _srb_signal_series and all(
            max((abs(float(v)) for v in series), default=0.0) <= 1e-12
            for series in _srb_signal_series
        )
        if _srb_all_zero:
            st.warning(
                "A extensão SRB foi ativada, mas sulfato e biomassa SRB ficaram zerados nesta corrida. "
                "Revise os campos de sulfato afluente e biomassa inicial da SRB."
            )

    if "phosphorus" in ext_requested:
        _sip = result.series.get("S_IP")
        _xmap = result.series.get("X_MAP")
        _ip_map = result.series.get("IP_MAP")
        if _sip or _xmap:
            p_cols = st.columns(2)
            if _sip:
                _sip_mgP = _sip[-1] * 30_970.0
                p_cols[0].metric("P efluente (S_IP)", f"{_sip_mgP:.1f} mgP/L")
            if _xmap:
                _xmap_mgP = _xmap[-1] * 30_970.0
                p_cols[1].metric("P recuperado como estruvita (X_MAP)", f"{_xmap_mgP:.1f} mgP/L")
        if _ip_map and max(_ip_map) < 1.0:
            st.warning(
                "Estruvita não precipitou (IP_MAP < 1.0 durante toda a simulação). "
                "Verifique S_Mg ou S_IP — podem estar baixos."
            )

    if "iron" in ext_requested:
        _sfe2 = result.series.get("S_Fe2")
        _ip_fes = result.series.get("IP_FeS")
        if _sfe2:
            fe_cols = st.columns(2)
            _sfe2_mgFe = _sfe2[-1] * 55_845.0
            fe_cols[0].metric("Fe(II) efluente (S_Fe2)", f"{_sfe2_mgFe:.1f} mgFe/L")
        if _ip_fes and max(_ip_fes) < 1.0:
            st.warning("FeS não precipitou (IP_FeS < 1.0). Verifique S_H2S (E4) e S_Fe3_feed.")

    if "multi_population" in ext_requested:
        _frac_ac = result.series.get("fraction_oligotrophic_ac")
        _frac_h2 = result.series.get("fraction_oligotrophic_h2")
        if _frac_ac or _frac_h2:
            mp_cols = st.columns(2)
            if _frac_ac:
                mp_cols[0].metric("Fração oligótrofa ac (steady-state)", f"{_frac_ac[-1]:.3f}")
            if _frac_h2:
                mp_cols[1].metric("Fração oligótrofa h2 (steady-state)", f"{_frac_h2[-1]:.3f}")
            st.caption("Valor alto → condições favoráveis a oligótrofos (baixo substrato, HRT longo).")


# ── Seção Exportar ─────────────────────────────────────────────────────────────

def _render_export(result: Any, *, show_advanced: bool = False) -> None:
    st.subheader("Download dos resultados")
    export_col1, export_col2, export_col3 = st.columns(3)
    with export_col1:
        st.download_button(
            label="Baixar resumo JSON",
            data=summary_json_bytes(result),
            file_name=f"{result.simulation_id}_summary.json",
            mime="application/json",
            use_container_width=True,
        )
    with export_col2:
        st.download_button(
            label="Baixar resumo CSV",
            data=summary_csv_bytes(result),
            file_name=f"{result.simulation_id}_summary.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with export_col3:
        st.download_button(
            label="Baixar perfis CSV",
            data=series_csv_bytes(result),
            file_name=f"{result.simulation_id}_profiles.csv",
            mime="text/csv",
            use_container_width=True,
        )

    # ── Relatório técnico Markdown ────────────────────────────────────────────

    st.divider()
    st.subheader("Relatório técnico")

    _baseline_id: str | None = None
    if show_advanced:
        from webapp.services.scenario_service import (
            load_saved_results as _load_saved,
            scenario_option_labels as _option_labels,
        )
        _saved, _ = _load_saved()
        _others = [r for r in _saved if r.simulation_id != result.simulation_id]
        if _others:
            _labels = _option_labels(_others)
            _options: list[str | None] = [None] + [r.simulation_id for r in _others]
            _baseline_id = st.selectbox(
                "Comparar com cenário base",
                options=_options,
                format_func=lambda sid: "— (sem baseline)" if sid is None else _labels.get(sid, sid),
                key=f"report_baseline_{result.simulation_id}",
            )

    _rep_col1, _rep_col2 = st.columns(2)
    with _rep_col1:
        if st.button(
            "📄 Exportar relatório Markdown",
            key=f"export_vault_{result.simulation_id}",
            use_container_width=True,
        ):
            from webapp.features.report_actions import export_report, generate_report, render_markdown
            _payload = generate_report(result, baseline_id=_baseline_id)
            _md = render_markdown(_payload)
            _date = _payload.generated_at[:10]
            _md_filename = f"Relatorio_Sim_{result.simulation_id}_{_date}.md"
            _path, _err = export_report(_payload)
            if _path:
                st.success(f"Relatório salvo em `{_path}`.")
            else:
                st.error(f"Falha ao exportar relatório: {_err}")
    with _rep_col2:
        from webapp.features.report_actions import generate_report, render_markdown
        _payload = generate_report(result, baseline_id=_baseline_id)
        _md = render_markdown(_payload)
        _date = _payload.generated_at[:10]
        _md_filename = f"Relatorio_Sim_{result.simulation_id}_{_date}.md"
        st.download_button(
            label="⬇ Baixar relatório Markdown",
            data=_md.encode("utf-8"),
            file_name=_md_filename,
            mime="text/markdown",
            use_container_width=True,
            key=f"dl_md_{result.simulation_id}",
        )
