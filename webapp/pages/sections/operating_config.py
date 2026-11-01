"""Seção: Configuração operacional — volume, temperatura, HRT/vazão, parâmetros avançados."""
from __future__ import annotations

import streamlit as st


def render_operating_config() -> None:
    """Renderiza formulário de condições operacionais e configuração de variantes de reator."""
    reactor_type = str(st.session_state.get("sim_reactor_type", "cstr"))
    ui_mode = str(st.session_state.get("sim_ui_mode", "operador"))

    # Modo hidráulico fora do form para rerun imediato
    if reactor_type != "batch":
        st.radio(
            "Definir por",
            options=["hrt", "flow_rate"],
            horizontal=True,
            format_func=lambda v: {"hrt": "HRT (dias)", "flow_rate": "Vazão Q (m³/dia)"}[v],
            key="hydraulic_mode",
            help="HRT: informe o tempo de retenção hidráulico diretamente. Vazão: HRT = V/Q derivado.",
        )

    left, right = st.columns(2)
    with left:
        st.number_input(
            "Volume do reator [m³]",
            min_value=10.0,
            value=float(st.session_state.get("volume_active", 3000.0)),
            step=50.0,
            key="volume_active",
        )
        st.number_input(
            "Temperatura [°C]",
            min_value=15.0,
            max_value=60.0,
            value=float(st.session_state.get("temperature_active", 35.0)),
            step=0.5,
            key="temperature_active",
        )

        if reactor_type == "batch":
            st.number_input(
                "Duração do ensaio [dias]",
                min_value=1.0,
                value=float(st.session_state.get("duration_days", 45.0)),
                step=1.0,
                key="duration_days",
                help="Para batelada, define a duração total do ensaio BMP.",
            )
            st.number_input(
                "HRT [dias] (N/A em batelada)",
                min_value=0.5,
                value=float(st.session_state.get("hrt_active", 20.0)),
                step=0.5,
                key="hrt_active",
                disabled=True,
                help="Batelada não usa HRT nem vazão contínua.",
            )
            st.caption("Modo hidráulico: **N/A** — batelada não tem fluxo contínuo.")
        else:
            hydraulic_mode = str(st.session_state.get("hydraulic_mode", "hrt"))
            if hydraulic_mode == "hrt":
                st.number_input(
                    "HRT [dias]",
                    min_value=0.5,
                    value=float(st.session_state.get("hrt_active", 20.0)),
                    step=0.5,
                    key="hrt_active",
                    help="Tempo de retenção hidráulico. Vazão Q = V / HRT calculada automaticamente.",
                )
                _v_preview = float(st.session_state.get("volume_active", 3000.0))
                _hrt_preview = float(st.session_state.get("hrt_active", 20.0))
                if _hrt_preview > 0:
                    st.caption(f"Vazão efetiva: **Q = {_v_preview / _hrt_preview:.1f} m³/dia**")
            else:
                _v_form = float(st.session_state.get("volume_active", 3000.0))
                _hrt_ref = float(st.session_state.get("hrt_active", 20.0))
                _q_default = float(st.session_state.get("flow_rate_active", _v_form / max(_hrt_ref, 0.1)))
                st.number_input(
                    "Vazão Q [m³/dia]",
                    min_value=0.1,
                    value=_q_default,
                    step=10.0,
                    key="flow_rate_active",
                    help="Vazão afluente contínua. HRT = V / Q derivado automaticamente.",
                )
                _q_actual = float(st.session_state.get("flow_rate_active", _q_default))
                _hrt_derived = _v_form / max(_q_actual, 0.01)
                st.session_state["hrt_active"] = _hrt_derived
                st.caption(
                    f"HRT efetivo: **{_hrt_derived:.2f} dias** "
                    f"(V = {_v_form:.0f} m³, Q = {_q_actual:.1f} m³/dia)"
                )

            st.number_input(
                "Duração da simulação [dias]",
                min_value=1.0,
                value=float(st.session_state.get("duration_days", 45.0)),
                step=1.0,
                key="duration_days",
            )

    with right:
        st.markdown("### Resumo do substrato")
        substrate_mode = str(st.session_state.get("sim_substrate_mode", "preset"))
        preset_id = st.session_state.get("sim_preset_id")
        custom_name = st.session_state.get("sim_custom_substrate_name")
        if substrate_mode == "preset":
            st.caption(f"Modo: Preset nativo — `{preset_id or '—'}`")
        elif substrate_mode == "codigestion":
            st.caption("Modo: Co-digestão ativa")
        elif substrate_mode == "custom":
            st.caption(f"Modo: Personalizado — `{custom_name or '—'}`")
        else:
            st.caption("Modo: Manual temporário")
        st.caption(
            f"Volume: {st.session_state.get('volume_active', 3000.0):.0f} m³ | "
            f"T: {st.session_state.get('temperature_active', 35.0):.1f}°C | "
            f"HRT: {st.session_state.get('hrt_active', 20.0):.1f} d"
        )

    # ── Variant config ──────────────────────────────────────────────────────────
    variant_config = _render_variant_config(reactor_type)
    st.session_state["variant_config"] = variant_config

    # ── Opções avançadas (modo especialista) ─────────────────────────────────────
    if ui_mode == "especialista":
        with st.expander("Opções avançadas", expanded=False):
            adv_col1, adv_col2, adv_col3 = st.columns(3)
            with adv_col1:
                st.number_input(
                    "Pontos de avaliação",
                    min_value=21,
                    max_value=601,
                    value=int(st.session_state.get("evaluation_points", 181)),
                    step=10,
                    key="evaluation_points",
                )
            with adv_col2:
                _solver_opts = ["BDF", "Radau"]
                _solver_idx = _solver_opts.index(str(st.session_state.get("solver_choice", "BDF")))
                st.selectbox(
                    "Solver",
                    options=_solver_opts,
                    index=_solver_idx,
                    key="solver_choice",
                )
            with adv_col3:
                st.checkbox(
                    "Salvar cenário em simulator/runs",
                    value=bool(st.session_state.get("persist_case", True)),
                    key="persist_case",
                )

        with st.expander(
            "Parâmetros Cinéticos Avançados",
            expanded=(st.session_state.get("ammonia_inhibition_mode") == "fan"),
        ):
            st.selectbox(
                "Correção cinética pela temperatura (modelo full)",
                options=["off", "siegrist2002"],
                format_func=lambda v: {"off": "Desligada", "siegrist2002": "Siegrist et al. (2002)"}[v],
                key="temperature_kinetics",
                help="Não aplicada por PyADM1 ou pelo modelo reduzido. Mudanças bruscas mesófila–termófila não são previstas pelo modelo.",
            )
            st.selectbox(
                "Modo de Inibição por Amônia",
                options=["simple", "fan"],
                format_func=lambda v: {
                    "simple": "simple — TAN com threshold (padrão, retrocompatível)",
                    "fan": "fan — Amônia livre com equilíbrio pH/temperatura (Anthonisen, 1976)",
                }[v],
                index=["simple", "fan"].index(
                    str(st.session_state.get("ammonia_inhibition_mode", "simple"))
                ),
                key="ammonia_inhibition_mode",
            )


def _render_variant_config(reactor_type: str) -> dict | None:
    """Renderiza os controles de variante específica de reator e retorna o variant_config."""
    vc_current = st.session_state.get("variant_config") or {}

    if reactor_type == "uasb" and st.session_state.get("sim_backend_choice") == "full":
        st.divider()
        st.markdown("**Configuração do UASB — Retenção de Biomassa**")
        st.number_input(
            "Fator de arraste de biomassa (washout_factor)",
            min_value=0.05,
            max_value=1.0,
            value=float(vc_current.get("biomass_washout_factor", 0.35)),
            step=0.05,
            format="%.2f",
            key="vc_biomass_washout_factor",
            help="Fração da taxa de diluição aplicada aos sólidos (biomassa). "
                 "UASB típico: 0.35 (SRT ≈ 2.9×HRT). Valor 1.0 = CSTR sem retenção.",
        )
        return {"biomass_washout_factor": float(st.session_state.get("vc_biomass_washout_factor", 0.35))}

    if reactor_type == "plug_flow" and st.session_state.get("sim_backend_choice") == "full":
        st.divider()
        st.markdown("**Configuração do Plug-Flow — Tanques em Série**")
        st.slider(
            "Número de segmentos (N)",
            min_value=2,
            max_value=20,
            value=int(vc_current.get("segments", 6)),
            step=1,
            key="vc_segments",
            help="CSTRs em série para aproximar escoamento pistão. N=2 mínimo; N≥8 converge bem.",
        )
        return {"segments": int(st.session_state.get("vc_segments", 6))}

    if reactor_type == "two_phase":
        st.divider()
        st.markdown("**Configuração da Variante — Duas Fases (AD)**")
        vc_col1, vc_col2 = st.columns(2)
        with vc_col1:
            st.number_input(
                "Fração vol. fase 1 (= fração HRT)",
                min_value=0.10,
                max_value=0.60,
                value=float(vc_current.get("phase1_volume_fraction", 0.30)),
                step=0.05,
                key="vc_phase1_volume_fraction",
            )
        with vc_col2:
            st.number_input(
                "pH setpoint fase 1 (acidogênica)",
                min_value=4.5,
                max_value=6.5,
                value=float(vc_current.get("phase1_ph_setpoint", 5.5)),
                step=0.1,
                key="vc_phase1_ph_setpoint",
            )
            st.number_input(
                "pH setpoint fase 2 (metanogênica)",
                min_value=6.5,
                max_value=8.0,
                value=float(vc_current.get("phase2_ph_setpoint", 7.2)),
                step=0.1,
                key="vc_phase2_ph_setpoint",
            )
        return {
            "phase1_volume_fraction": float(st.session_state.get("vc_phase1_volume_fraction", 0.30)),
            "phase1_ph_setpoint": float(st.session_state.get("vc_phase1_ph_setpoint", 5.5)),
            "phase2_ph_setpoint": float(st.session_state.get("vc_phase2_ph_setpoint", 7.2)),
        }

    if reactor_type == "tpad":
        st.divider()
        st.markdown("**Configuração da Variante — TPAD**")
        vc_col1, vc_col2 = st.columns(2)
        with vc_col1:
            st.number_input(
                "Temperatura termofílica [°C]",
                min_value=45.0,
                max_value=65.0,
                value=float(vc_current.get("thermo_temperature_c", 55.0)),
                step=1.0,
                key="vc_thermo_temperature_c",
            )
            st.number_input(
                "HRT termofílico [dias]",
                min_value=0.5,
                max_value=10.0,
                value=float(vc_current.get("thermo_hrt_days", 3.0)),
                step=0.5,
                key="vc_thermo_hrt_days",
            )
        with vc_col2:
            st.number_input(
                "Temperatura mesofílica [°C]",
                min_value=25.0,
                max_value=42.0,
                value=float(vc_current.get("meso_temperature_c", 35.0)),
                step=1.0,
                key="vc_meso_temperature_c",
            )
            st.number_input(
                "HRT mesofílico [dias]",
                min_value=5.0,
                max_value=40.0,
                value=float(vc_current.get("meso_hrt_days", 15.0)),
                step=1.0,
                key="vc_meso_hrt_days",
            )
        return {
            "thermo_temperature_c": float(st.session_state.get("vc_thermo_temperature_c", 55.0)),
            "thermo_hrt_days": float(st.session_state.get("vc_thermo_hrt_days", 3.0)),
            "meso_temperature_c": float(st.session_state.get("vc_meso_temperature_c", 35.0)),
            "meso_hrt_days": float(st.session_state.get("vc_meso_hrt_days", 15.0)),
        }

    if reactor_type == "batch":
        st.divider()
        st.markdown("**Configuração da Variante — Batelada (BMP)**")
        st.number_input(
            "Fração de inóculo",
            min_value=0.05,
            max_value=0.80,
            value=float(vc_current.get("inoculum_fraction", 0.30)),
            step=0.05,
            key="vc_inoculum_fraction",
        )
        return {"inoculum_fraction": float(st.session_state.get("vc_inoculum_fraction", 0.30))}

    return None
