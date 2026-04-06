"""Seção: Configuração de extensões do modelo full ADM1."""
from __future__ import annotations

import streamlit as st

_EXTENSION_DESCRIPTIONS: dict[str, str] = {
    "lactate": "E6 – Lactato: intermediário na fermentação de açúcares",
    "ethanol": "E10 – Etanol: intermediário na fermentação de açúcares",
    "phenolics": "E11 – Fenólicos: degradação de compostos fenólicos (ex: resíduos oleosos)",
    "lcfa_adsorption": "E5 – Adsorção de LCFA: cinética de adsorção de ácidos graxos de cadeia longa",
    "srb": "E4 – SRB: redução de sulfato (competição com metanogênese)",
    "multi_population": "E12 – Multi-população: acetoclásticos e hidrogenotróficos divididos em populações oligótrofa e copiótrofa",
    "phosphorus": "E7 – Fósforo: ciclo de P inorgânico, precipitação de estruvita (MAP) e calcita",
    "iron": "E8 – Ferro: redução de Fe(III), precipitação de FeS e vivianita (requer E4 + E7)",
    "microalgae": "E20 – Microalgas: X_alg + hidrólise tipo Contois conforme Mairet et al. (2011)",
    "syngas": "E15 – Syngas: CO→H₂ e CO→acetato com inibição de CO conforme Sun et al. (2021)",
    "trace_elements": "E9 – Elementos-traço: Ni/Co/Fe com sulfetos, FeCO3 e limitação por metal livre",
    "pilot_tracer": "Traçador RTD: injeção de traçador inerte para caracterização de distribuição de tempo de residência",
}


def render_extensions_config() -> None:
    """Renderiza o seletor e configuração de extensões do backend full."""
    backend_choice = str(st.session_state.get("sim_backend_choice", "pyadm1"))
    ui_mode = str(st.session_state.get("sim_ui_mode", "operador"))
    active_extensions: list[str] = list(st.session_state.get("sim_full_extensions", []))

    # Só mostrar se backend == "full" OU se já houver extensões ativas
    if backend_choice != "full" and not active_extensions:
        return

    if backend_choice == "full":
        try:
            from simulator.full_model.extension_registry import list_registered_extensions
            _available_ext = list_registered_extensions()
        except Exception:
            _available_ext = list(_EXTENSION_DESCRIPTIONS)

        _ext_labels = {k: _EXTENSION_DESCRIPTIONS.get(k, k) for k in _available_ext}
        _sorted_ext_keys = sorted(_ext_labels, key=lambda k: _ext_labels[k].split("–")[-1].strip().lower())
        active_extensions = st.multiselect(
            "Extensões do modelo full ADM1",
            options=_sorted_ext_keys,
            format_func=lambda v: _ext_labels.get(v, v),
            default=st.session_state.get("sim_full_extensions", []),
            key="sim_full_extensions",
            help="Módulos opcionais a ativar no backend full. Cada extensão adiciona estados e processos.",
        )

    # ── Configuração por extensão ─────────────────────────────────────────────
    if "srb" in active_extensions:
        _render_srb_config(ui_mode)

    if "phosphorus" in active_extensions:
        _render_phosphorus_config(ui_mode)

    if "iron" in active_extensions:
        _render_iron_config(active_extensions, ui_mode)

    if "multi_population" in active_extensions:
        st.info(
            "**E12 – Multi-população**: nenhuma configuração extra necessária. "
            "Os acetoclásticos e hidrogenotróficos são divididos automaticamente em populações "
            "oligótrofa (baixo K_S) e copiótrofa (alto k_m). "
            "Parâmetros cinéticos seguem Ramirez et al. (2009)."
        )

    if "microalgae" in active_extensions:
        _render_microalgae_config(ui_mode)

    if "syngas" in active_extensions:
        _render_syngas_config(ui_mode)

    if "trace_elements" in active_extensions:
        _render_trace_elements_config(active_extensions, ui_mode)


def _render_srb_config(ui_mode: str) -> None:
    with st.expander("Configuração mínima da extensão SRB", expanded=True):
        st.caption(
            "A redução de sulfato só reage se houver sulfato e biomassa SRB no modelo. "
            "Sem esses estados, os perfis SRB ficam zerados."
        )
        _srb_col1, _srb_col2 = st.columns(2)
        with _srb_col1:
            st.number_input(
                "Sulfato afluente S_SO4 [kmol/m³]",
                min_value=0.0,
                value=float(st.session_state.get("srb_influent_so4", 0.01)),
                step=0.001,
                format="%.4f",
                key="srb_influent_so4",
            )
            st.number_input(
                "Sulfato inicial S_SO4 [kmol/m³]",
                min_value=0.0,
                value=float(st.session_state.get("srb_initial_so4", 0.01)),
                step=0.001,
                format="%.4f",
                key="srb_initial_so4",
            )
            st.number_input(
                "Biomassa inicial X_SRB_ac [kgCOD/m³]",
                min_value=0.0,
                value=float(st.session_state.get("srb_initial_srb_ac", 0.10)),
                step=0.01,
                format="%.4f",
                key="srb_initial_srb_ac",
            )
        with _srb_col2:
            st.number_input(
                "Biomassa inicial X_SRB_h2 [kgCOD/m³]",
                min_value=0.0,
                value=float(st.session_state.get("srb_initial_srb_h2", 0.05)),
                step=0.01,
                format="%.4f",
                key="srb_initial_srb_h2",
            )
            st.number_input(
                "Biomassa inicial X_SRB_pro [kgCOD/m³]",
                min_value=0.0,
                value=float(st.session_state.get("srb_initial_srb_pro", 0.05)),
                step=0.01,
                format="%.4f",
                key="srb_initial_srb_pro",
            )
            st.number_input(
                "Biomassa inicial X_SRB_bu [kgCOD/m³]",
                min_value=0.0,
                value=float(st.session_state.get("srb_initial_srb_bu", 0.05)),
                step=0.01,
                format="%.4f",
                key="srb_initial_srb_bu",
            )


def _render_phosphorus_config(ui_mode: str) -> None:
    with st.expander("Configuração da extensão Fósforo (E7)", expanded=True):
        st.caption(
            "S_Mg e S_Ca são concentrações operacionais fixas (parâmetros de entrada). "
            "S_IP é o fósforo inorgânico inicial no reator."
        )
        _phos_col1, _phos_col2 = st.columns(2)
        with _phos_col1:
            st.number_input(
                "Mg²⁺ operacional S_Mg [kmol/m³]",
                min_value=0.0,
                value=float(st.session_state.get("phos_param_s_mg", 0.004)),
                step=0.001,
                format="%.4f",
                key="phos_param_s_mg",
                help="≈ 0.004 kmol/m³ ≈ 97 mg Mg/L, típico de digestor municipal",
            )
            st.number_input(
                "Ca²⁺ operacional S_Ca [kmol/m³]",
                min_value=0.0,
                value=float(st.session_state.get("phos_param_s_ca", 0.005)),
                step=0.001,
                format="%.4f",
                key="phos_param_s_ca",
                help="≈ 0.005 kmol/m³ ≈ 200 mg Ca/L",
            )
        with _phos_col2:
            st.number_input(
                "Fósforo inorgânico inicial S_IP [kmol/m³]",
                min_value=0.0,
                value=float(st.session_state.get("phos_initial_s_ip", 0.003)),
                step=0.001,
                format="%.4f",
                key="phos_initial_s_ip",
                help="≈ 0.003 kmol/m³ ≈ 93 mg P/L, faixa típica de digestor",
            )


def _render_iron_config(active_extensions: list[str], ui_mode: str) -> None:
    _iron_missing = [e for e in ("srb", "phosphorus") if e not in active_extensions]
    if _iron_missing:
        st.error(
            f"⚠️ A extensão **Ferro (E8)** requer também: **{', '.join(_iron_missing)}**. "
            "Adicione as extensões faltantes ou a simulação falhará."
        )
    with st.expander("Configuração da extensão Ferro (E8)", expanded=True):
        st.caption(
            "S_Fe3_feed é a concentração de Fe(III) no afluente (dose típica de coagulante). "
            "S_Fe2 é o Fe(II) dissolvido inicial no reator."
        )
        _iron_col1, _iron_col2 = st.columns(2)
        with _iron_col1:
            st.number_input(
                "Fe(III) afluente S_Fe3_feed [kmol/m³]",
                min_value=0.0,
                value=float(st.session_state.get("iron_param_s_fe3_feed", 0.001)),
                step=0.0001,
                format="%.4f",
                key="iron_param_s_fe3_feed",
                help="≈ 0.001 kmol/m³ ≈ 56 mg Fe/L",
            )
        with _iron_col2:
            st.number_input(
                "Fe(II) dissolvido inicial S_Fe2 [kmol/m³]",
                min_value=0.0,
                value=float(st.session_state.get("iron_initial_s_fe2", 0.0005)),
                step=0.0001,
                format="%.4f",
                key="iron_initial_s_fe2",
                help="≈ 0.0005 kmol/m³ ≈ 28 mg Fe/L",
            )


def _render_microalgae_config(ui_mode: str) -> None:
    with st.expander("Configuração da extensão Microalgas (E20)", expanded=True):
        st.caption(
            "A E20 usa X_alg como biomassa composta de alimentação e modifica rho_2/rho_3/rho_4 "
            "com o termo tipo Contois do artigo-base. k_hyd_ch/pr/li e K_S_ch/pr/li ficam nos defaults "
            "de Mairet et al. (2011); f_hyd_alg agora é apenas um multiplicador adicional de calibração."
        )
        _alg_col1, _alg_col2 = st.columns(2)
        with _alg_col1:
            st.number_input(
                "Biomassa algal inicial X_alg [kgCOD/m³]",
                min_value=0.0,
                value=float(st.session_state.get("alg_initial_x_alg", 0.5)),
                step=0.1,
                format="%.3f",
                key="alg_initial_x_alg",
                help="Concentração inicial de algas no digestor. Típico: 0.5-5 kgCOD/m³.",
            )
            st.number_input(
                "Fator de recalcitrância de parede f_wall_alg [-]",
                min_value=0.1,
                max_value=1.0,
                value=float(st.session_state.get("alg_param_f_wall_alg", 0.7)),
                step=0.05,
                format="%.2f",
                key="alg_param_f_wall_alg",
                help="Multiplica k_dis_alg. 0.7 = resistência moderada; 0.9+ = biomassa mais acessível.",
            )
        with _alg_col2:
            st.number_input(
                "Biomassa algal afluente X_alg [kgCOD/m³]",
                min_value=0.0,
                value=float(st.session_state.get("alg_influent_x_alg", 0.5)),
                step=0.1,
                format="%.3f",
                key="alg_influent_x_alg",
                help="X_alg no afluente. Corresponde à carga de microalgas alimentada ao digestor.",
            )
            st.number_input(
                "Multiplicador adicional f_hyd_alg [-]",
                min_value=0.1,
                max_value=2.0,
                value=float(st.session_state.get("alg_param_f_hyd_alg", 1.0)),
                step=0.05,
                format="%.2f",
                key="alg_param_f_hyd_alg",
                help="1.0 preserva a forma tipo Contois do paper-base; use apenas para recalibração local.",
            )


def _render_syngas_config(ui_mode: str) -> None:
    with st.expander("Configuração da extensão Syngas (E15)", expanded=True):
        st.caption(
            "X_met_CO converte CO em H₂ (WGS) e/ou acetato (homoacetogênese) conforme f_co_to_h2. "
            "S_CO é o CO dissolvido; S_gas_CO é o CO no headspace. "
            "Sem inóculo X_met_CO, o CO não é consumido."
        )
        _syn_col1, _syn_col2 = st.columns(2)
        with _syn_col1:
            st.number_input(
                "Inóculo X_met_CO inicial [kgCOD/m³]",
                min_value=0.0,
                value=float(st.session_state.get("syngas_initial_x_met_co", 0.05)),
                step=0.01,
                format="%.4f",
                key="syngas_initial_x_met_co",
                help="Biomassa carboxidotrófica inicial. Mín. recomendado: 0.05 kgCOD/m³.",
            )
            st.number_input(
                "CO dissolvido inicial S_CO [kgCOD/m³]",
                min_value=0.0,
                value=float(st.session_state.get("syngas_initial_s_co", 0.01)),
                step=0.001,
                format="%.4f",
                key="syngas_initial_s_co",
                help="≈ 0.01 kgCOD/m³ ≈ 17 mg CO/L",
            )
            st.number_input(
                "Fração CO→H₂ f_co_to_h2 [-]",
                min_value=0.0,
                max_value=1.0,
                value=float(st.session_state.get("syngas_param_f_co_to_h2", 0.65)),
                step=0.05,
                format="%.2f",
                key="syngas_param_f_co_to_h2",
                help="Fração do CO consumido pela rota WGS (→ H₂). Complemento vai para homoacetogênese.",
            )
        with _syn_col2:
            st.number_input(
                "CO no headspace S_gas_CO [kgCOD/m³]",
                min_value=0.0,
                value=float(st.session_state.get("syngas_initial_s_gas_co", 0.5)),
                step=0.05,
                format="%.3f",
                key="syngas_initial_s_gas_co",
                help="Concentração inicial de CO na fase gasosa. Típico biogás de syngas: 0.5–2 kgCOD/m³.",
            )
            st.number_input(
                "CO afluente S_CO [kgCOD/m³]",
                min_value=0.0,
                value=float(st.session_state.get("syngas_influent_s_co", 0.0)),
                step=0.001,
                format="%.4f",
                key="syngas_influent_s_co",
                help="CO dissolvido no afluente líquido (ex: pré-saturação). 0 para alimentação só via gás.",
            )


def _render_trace_elements_config(active_extensions: list[str], ui_mode: str) -> None:
    _te_conflict = "iron" in active_extensions
    if _te_conflict:
        st.error(
            "⚠️ **Elementos-traço (E9)** não pode ser combinado com **Ferro (E8)** nesta versão. "
            "Os dois módulos têm química própria de Fe e pools precipitados distintos."
        )
    with st.expander("Configuração da extensão Elementos-Traço (E9)", expanded=True):
        st.caption(
            "Ni/Co usam limitação por metal livre e um proxy opcional de complexação orgânica (S_DOM_TE). "
            "Fe(II) é dinâmico como S_Fe2_te, pode precipitar como FeS/FeCO3 e, quando E4 está ativo, "
            "a estequiometria passa a consumir S_H2S explicitamente."
        )
        _te_col1, _te_col2 = st.columns(2)
        with _te_col1:
            st.number_input(
                "Ni dissolvido inicial S_Ni [kmolNi/m³]",
                min_value=0.0,
                value=float(st.session_state.get("te_initial_s_ni", 2e-6)),
                step=1e-7,
                format="%.2e",
                key="te_initial_s_ni",
                help="Faixa típica: 1e-6 a 5e-6 kmolNi/m³. Limitação usa a fração livre.",
            )
            st.number_input(
                "Co dissolvido inicial S_Co [kmolCo/m³]",
                min_value=0.0,
                value=float(st.session_state.get("te_initial_s_co", 5e-7)),
                step=1e-8,
                format="%.2e",
                key="te_initial_s_co",
                help="Faixa típica: 1e-7 a 2e-6 kmolCo/m³. Limitação usa a fração livre.",
            )
            st.number_input(
                "Fe(II) inicial S_Fe2_te [kmolFe/m³]",
                min_value=0.0,
                value=float(st.session_state.get("te_initial_s_fe2_te", 1e-5)),
                step=1e-6,
                format="%.2e",
                key="te_initial_s_fe2_te",
                help="Estado dinâmico de Fe(II) da E9; alimenta limitação por Fe e precipitação FeS/FeCO3.",
            )
        with _te_col2:
            st.number_input(
                "Fe(II) afluente S_Fe2_te_feed [kmolFe/m³]",
                min_value=0.0,
                value=float(st.session_state.get("te_param_s_fe2_feed", 1e-5)),
                step=1e-6,
                format="%.2e",
                key="te_param_s_fe2_feed",
                help="Referência operacional do Fe(II) no afluente; enviado ao solver.",
            )
            st.number_input(
                "Ligantes orgânicos S_DOM_TE [kgCOD/m³]",
                min_value=0.0,
                value=float(st.session_state.get("te_param_s_dom", 0.0)),
                step=0.05,
                format="%.2f",
                key="te_param_s_dom",
                help="Proxy operacional para complexação de Ni/Co com DOM; 0.0 desativa o efeito.",
            )
            st.number_input(
                "Constante proxy K_c_Ni [m³/kgCOD]",
                min_value=0.0,
                value=float(st.session_state.get("te_param_k_c_ni", 27.54)),
                step=0.1,
                format="%.2f",
                key="te_param_k_c_ni",
                help="Constante proxy ancorada em Maharaj et al. (2019), Table 1.",
            )
            st.number_input(
                "Constante proxy K_c_Co [m³/kgCOD]",
                min_value=0.0,
                value=float(st.session_state.get("te_param_k_c_co", 23.99)),
                step=0.1,
                format="%.2f",
                key="te_param_k_c_co",
                help="Constante proxy ancorada em Maharaj et al. (2019), Table 1.",
            )
