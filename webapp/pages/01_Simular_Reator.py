from __future__ import annotations

from _bootstrap import ensure_project_root

ensure_project_root()

import streamlit as st

from webapp.components.charts import render_ammonia_charts, render_core_profile_charts, render_phase_profile_charts
from webapp.components.status_cards import (
    render_issue_messages,
    render_sidebar_panel,
    render_simulation_kpis,
    render_summary_cards,
    render_usage_guide,
    render_workflow_links,
)
from webapp.components.tables import render_frame, render_input_table, render_series_preview, render_summary_table
from webapp.services.health import collect_health_snapshot
from webapp.services.preferences_service import (
    delete_custom_substrate,
    delete_simulation_preset,
    find_custom_substrate,
    get_preferences,
    list_custom_substrates,
    list_simulation_presets,
    record_recent_simulation,
    save_custom_substrate,
    save_simulation_preset,
)
from webapp.services.simulation_service import (
    apply_user_simulation_preset,
    backend_comparison_frame,
    build_feed_and_operating,
    build_user_simulation_preset_payload,
    compare_backends_for_result,
    format_simulation_error,
    get_backend_options,
    get_reactor_options,
    resolve_requested_backend,
    run_simulation,
    series_csv_bytes,
    summary_csv_bytes,
    summary_json_bytes,
    validate_simulation_inputs,
)
from simulator.full_model.extension_registry import list_registered_extensions
from webapp.state.session_state import ensure_session_state
from webapp.utils.page_config import configure_page, render_page_header
from webapp.utils.presets import (
    CODIGESTION_PRESET_LABELS,
    get_codigestion_blend,
    get_manual_defaults,
    get_preset_bundle,
    get_substrate_options,
    preset_rows,
)

FLASH_KEY = "simular_reator_flash"
# Tipos que requerem fallback quando o backend pyadm1 é solicitado (não suportam não-CSTR)
_PYADM1_FALLBACK_TYPES = {"two_phase", "tpad", "batch", "uasb", "plug_flow"}


def _queue_flash(message: str) -> None:
    st.session_state[FLASH_KEY] = message


def _render_flash() -> None:
    message = st.session_state.pop(FLASH_KEY, None)
    if message:
        st.toast(message)


def _build_extension_state_overrides(active_extensions: list[str]) -> tuple[dict[str, float], dict[str, float]]:
    initial: dict[str, float] = {}
    influent: dict[str, float] = {}
    if "srb" in active_extensions:
        initial_pairs = {
            "S_SO4": float(st.session_state.get("srb_initial_so4", 0.01)),
            "X_SRB_ac": float(st.session_state.get("srb_initial_srb_ac", 0.10)),
            "X_SRB_h2": float(st.session_state.get("srb_initial_srb_h2", 0.05)),
            "X_SRB_pro": float(st.session_state.get("srb_initial_srb_pro", 0.05)),
            "X_SRB_bu": float(st.session_state.get("srb_initial_srb_bu", 0.05)),
        }
        influent_pairs = {
            "S_SO4": float(st.session_state.get("srb_influent_so4", 0.01)),
        }
        initial.update({name: value for name, value in initial_pairs.items() if abs(value) > 0.0})
        influent.update({name: value for name, value in influent_pairs.items() if abs(value) > 0.0})
    if "phosphorus" in active_extensions:
        s_ip = float(st.session_state.get("phos_initial_s_ip", 0.003))
        if s_ip > 0.0:
            initial["S_IP"] = s_ip
    if "iron" in active_extensions:
        s_fe2 = float(st.session_state.get("iron_initial_s_fe2", 0.0005))
        if s_fe2 > 0.0:
            initial["S_Fe2"] = s_fe2
    if "microalgae" in active_extensions:
        x_alg = float(st.session_state.get("alg_initial_x_alg", 0.5))
        if x_alg > 0.0:
            initial["X_alg"] = x_alg
        x_alg_in = float(st.session_state.get("alg_influent_x_alg", 0.5))
        if x_alg_in > 0.0:
            influent["X_alg"] = x_alg_in
    if "syngas" in active_extensions:
        x_met_co = float(st.session_state.get("syngas_initial_x_met_co", 0.05))
        s_co = float(st.session_state.get("syngas_initial_s_co", 0.01))
        s_gas_co = float(st.session_state.get("syngas_initial_s_gas_co", 0.5))
        if x_met_co > 0.0:
            initial["X_met_CO"] = x_met_co
        if s_co > 0.0:
            initial["S_CO"] = s_co
        if s_gas_co > 0.0:
            initial["S_gas_CO"] = s_gas_co
        s_co_in = float(st.session_state.get("syngas_influent_s_co", 0.0))
        if s_co_in > 0.0:
            influent["S_CO"] = s_co_in
    if "trace_elements" in active_extensions:
        s_ni = float(st.session_state.get("te_initial_s_ni", 2e-6))
        s_cob = float(st.session_state.get("te_initial_s_co", 5e-7))
        if s_ni > 0.0:
            initial["S_Ni"] = s_ni
            influent["S_Ni"] = s_ni
        if s_cob > 0.0:
            initial["S_Co"] = s_cob
            influent["S_Co"] = s_cob
    return initial, influent


def _build_extension_parameter_overrides(active_extensions: list[str]) -> dict[str, float]:
    overrides: dict[str, float] = {}
    if "phosphorus" in active_extensions:
        overrides["S_Mg"] = float(st.session_state.get("phos_param_s_mg", 0.004))
        overrides["S_Ca"] = float(st.session_state.get("phos_param_s_ca", 0.005))
    if "iron" in active_extensions:
        overrides["S_Fe3_feed"] = float(st.session_state.get("iron_param_s_fe3_feed", 0.001))
    if "trace_elements" in active_extensions:
        overrides["S_Fe2_TE_feed"] = float(st.session_state.get("te_param_s_fe2_feed", 1e-5))
    return overrides


configure_page("Simular Reator")
ensure_session_state()
snapshot = collect_health_snapshot()
st.session_state["recent_page"] = "simular_reator"
render_sidebar_panel(snapshot, current_page="Simular Reator")
render_page_header(
    eyebrow="Fase W2 + W7",
    title="Simular Reator",
    description="Fluxo principal da interface: configurar o caso, validar rapidamente os inputs, salvar presets do usuario e rodar a simulacao ADM1 sem sair da web UI.",
)
_render_flash()

if snapshot["issues"]:
    render_issue_messages(snapshot)
render_summary_cards(snapshot)
render_workflow_links(
    title="Fluxos relacionados",
    items=[
        {"path": "pages/02_Comparar_Cenarios.py", "label": "Comparar Cenarios", "caption": "Usar depois de persistir mais de um caso."},
        {"path": "pages/04_Validacao.py", "label": "Validacao", "caption": "Checar aderencia do backend antes de estudos mais sensiveis."},
        {"path": "pages/05_Consulta_Tecnica.py", "label": "Consulta Tecnica", "caption": "Consultar literatura e mapear parametros do caso."},
    ],
)
render_usage_guide(
    title="Como usar esta tela",
    summary="A tela foi refinada para primeiro uso: escolha um preset tecnico, valide o caso, rode a simulacao e, se fizer sentido, salve a configuracao como preset do usuario.",
    steps=[
        "Escolha o reator, o modo de alimentacao e o backend desejado.",
        "Revise volume, temperatura, HRT e a composicao da alimentacao.",
        "Use os avisos tecnicos abaixo para detectar casos que merecem revisao antes da corrida.",
        "Execute a simulacao e persista o cenario se quiser compara-lo em outra tela.",
    ],
    tips=[
        "Para CSTR, `auto` continua em `pyadm1`; use `full` explicitamente quando quiser rodar o ADM1 nativo do projeto.",
        "Se estiver explorando um caso recorrente, salve-o como preset do usuario para reutilizacao futura.",
    ],
)

preferences = get_preferences()
reactor_options = get_reactor_options()
backend_options = get_backend_options()
substrate_options = get_substrate_options()
# Separate single-substrate presets from co-digestion presets
single_substrate_options = {k: v for k, v in substrate_options.items() if k not in CODIGESTION_PRESET_LABELS}
codigestion_options = {k: v for k, v in substrate_options.items() if k in CODIGESTION_PRESET_LABELS}
default_preset_id = next(iter(single_substrate_options)) if single_substrate_options else None

session_defaults = {
    "sim_reactor_type": preferences.get("default_reactor", "cstr"),
    "sim_substrate_mode": "preset",
    "sim_preset_id": default_preset_id,
    "sim_custom_substrate_name": None,
    "sim_backend_choice": preferences.get("default_backend", "pyadm1"),
    "ammonia_inhibition_mode": preferences.get("ammonia_inhibition_mode_default", "simple"),
    "codigestion_preset": next(iter(codigestion_options)) if codigestion_options else None,
    "variant_config": None,
    "duration_days": 45.0,
    "evaluation_points": 181,
    "solver_choice": "BDF",
    "persist_case": bool(preferences.get("persist_scenarios_by_default", True)),
    "volume_active": 3000.0,
    "temperature_active": 35.0,
    "hrt_active": 20.0,
    "srb_influent_so4": 0.01,
    "srb_initial_so4": 0.01,
    "srb_initial_srb_ac": 0.10,
    "srb_initial_srb_h2": 0.05,
    "srb_initial_srb_pro": 0.05,
    "srb_initial_srb_bu": 0.05,
    "phos_initial_s_ip": 0.003,
    "phos_param_s_mg": 0.004,
    "phos_param_s_ca": 0.005,
    "iron_initial_s_fe2": 0.0005,
    "iron_param_s_fe3_feed": 0.001,
    "alg_initial_x_alg": 0.5,
    "alg_influent_x_alg": 0.5,
    "syngas_initial_x_met_co": 0.05,
    "syngas_initial_s_co": 0.01,
    "syngas_initial_s_gas_co": 0.5,
    "syngas_influent_s_co": 0.0,
    "te_initial_s_ni": 2e-6,
    "te_initial_s_co": 5e-7,
    "te_param_s_fe2_feed": 1e-5,
    "hydraulic_mode": "hrt",
    "flow_rate_active": 150.0,
}
for key, value in session_defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value

saved_presets = list_simulation_presets()
if saved_presets:
    with st.expander("Presets do usuario", expanded=False):
        preset_names = [str(item.get("name")) for item in saved_presets]
        selected_user_preset = st.selectbox("Preset salvo", options=preset_names, key="user_simulation_preset")
        preset_rows_user = []
        for item in saved_presets:
            summary = item.get("summary", {}) if isinstance(item.get("summary"), dict) else {}
            preset_rows_user.append(
                {
                    "preset": item.get("name"),
                    "reator": summary.get("reactor_type"),
                    "modo": summary.get("substrate_mode"),
                    "substrato": summary.get("preset_id") or "manual",
                    "backend": summary.get("backend_choice"),
                    "duracao_d": summary.get("duration_days"),
                    "atualizado_em": item.get("updated_at"),
                }
            )
        render_frame(preset_rows_user)
        preset_col1, preset_col2 = st.columns(2)
        with preset_col1:
            if st.button("Aplicar preset salvo", use_container_width=True):
                preset_payload = next(item.get("payload") for item in saved_presets if str(item.get("name")) == selected_user_preset)
                apply_user_simulation_preset(st.session_state, preset_payload)
                st.session_state["sim_skip_base_reset"] = True
                _queue_flash(f"Preset `{selected_user_preset}` aplicado.")
                st.rerun()
        with preset_col2:
            if st.button("Excluir preset salvo", use_container_width=True):
                delete_simulation_preset(selected_user_preset)
                _queue_flash(f"Preset `{selected_user_preset}` excluido.")
                st.rerun()

# ─── Selector row ────────────────────────────────────────────────────────────
selector_col1, selector_col2, selector_col3 = st.columns((1.05, 1.0, 0.95))
with selector_col1:
    reactor_type = st.selectbox(
        "Tipo de reator",
        options=list(reactor_options),
        format_func=lambda value: reactor_options[value],
        key="sim_reactor_type",
    )
with selector_col2:
    substrate_mode_label = st.radio(
        "Modo de alimentacao",
        options=["preset", "codigestion", "custom", "manual"],
        horizontal=True,
        format_func=lambda value: {
            "preset": "Preset nativo",
            "codigestion": "Co-digestão",
            "custom": "Personalizado",
            "manual": "Manual temporário",
        }[value],
        key="sim_substrate_mode",
    )
with selector_col3:
    backend_choice = st.selectbox(
        "Backend",
        options=list(backend_options),
        format_func=lambda value: backend_options[value],
        key="sim_backend_choice",
    )

# Show info when pyadm1 is selected for non-CSTR reactors (will fallback to reduced)
if reactor_type in _PYADM1_FALLBACK_TYPES and backend_choice == "pyadm1":
    st.warning(f"PyADM1 suporta apenas CSTR. Para o reator `{reactor_type}`, o backend será `reduced`. Use `full` para ADM1 nativo.")
elif reactor_type != "cstr" and backend_choice == "full":
    st.info(f"Backend `full` selecionado — suporta `{reactor_type}` com ADM1 nativo completo.")

# ─── Extension selector (only for full backend) ───────────────────────────────
_EXTENSION_DESCRIPTIONS = {
    "lactate": "E6 – Lactato: intermediário na fermentação de açúcares",
    "ethanol": "E10 – Etanol: intermediário na fermentação de açúcares",
    "phenolics": "E11 – Fenólicos: degradação de compostos fenólicos (ex: resíduos oleosos)",
    "lcfa_adsorption": "E5 – Adsorção de LCFA: cinética de adsorção de ácidos graxos de cadeia longa",
    "srb": "E4 – SRB: redução de sulfato (competição com metanogênese)",
    "multi_population": "E12 – Multi-população: acetoclásticos e hidrogenotróficos divididos em populações oligótrofa e copiótrofa",
    "phosphorus": "E7 – Fósforo: ciclo de P inorgânico, precipitação de estruvita (MAP) e calcita",
    "iron": "E8 – Ferro: redução de Fe(III), precipitação de FeS e vivianita (requer E4 + E7)",
    "microalgae": "E20 – Microalgas: digestão de biomassa algal com recalcitrância de parede celular (Mairet 2011)",
    "syngas": "E15 – Syngas: biometanação de CO via reação WGS enzimática e X_met_CO (Lecker 2017)",
    "trace_elements": "E9 – Elementos-traço: Ni e Co como micronutrientes; limitação de metanogênese (Thanh 2016)",
    "pilot_tracer": "Traçador RTD: injeção de traçador inerte para caracterização de distribuição de tempo de residência",
}

_active_extensions: list[str] = []
if backend_choice == "full":
    try:
        _available_ext = list_registered_extensions()
    except Exception:
        _available_ext = list(_EXTENSION_DESCRIPTIONS)
    _ext_labels = {k: _EXTENSION_DESCRIPTIONS.get(k, k) for k in _available_ext}
    _sorted_ext_keys = sorted(_ext_labels, key=lambda k: _ext_labels[k].split("–")[-1].strip().lower())
    _active_extensions = st.multiselect(
        "Extensões do modelo full ADM1",
        options=_sorted_ext_keys,
        format_func=lambda v: _ext_labels.get(v, v),
        default=st.session_state.get("sim_full_extensions", []),
        key="sim_full_extensions",
        help="Selecione módulos opcionais a ativar no backend full. Cada extensão adiciona estados e processos ao modelo.",
    )
    if "srb" in _active_extensions:
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

    if "phosphorus" in _active_extensions:
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

    if "iron" in _active_extensions:
        _iron_missing = [e for e in ("srb", "phosphorus") if e not in _active_extensions]
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

    if "multi_population" in _active_extensions:
        st.info(
            "**E12 – Multi-população**: nenhuma configuração extra necessária. "
            "Os acetoclásticos e hidrogenotróficos são divididos automaticamente em populações "
            "oligótrofa (baixo K_S) e copiótrofa (alto k_m). Os parâmetros cinéticos padrão "
            "seguem Ramirez et al. (2009)."
        )

    if "microalgae" in _active_extensions:
        with st.expander("Configuração da extensão Microalgas (E20)", expanded=True):
            st.caption(
                "X_alg é a biomassa algal composta que desintegra com recalcitrância de parede celular. "
                "Use f_wall_alg < 1 para espécies resistentes. Defaults: Chlorella vulgaris (Mairet 2011)."
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
                    help="Concentração inicial de algas no digestor. Típico: 0.5–5 kgCOD/m³.",
                )
            with _alg_col2:
                st.number_input(
                    "Biomassa algal afluente X_alg [kgCOD/m³]",
                    min_value=0.0,
                    value=float(st.session_state.get("alg_influent_x_alg", 0.5)),
                    step=0.1,
                    format="%.3f",
                    key="alg_influent_x_alg",
                    help="X_alg no afluente. Corresponde à carga de algas alimentada ao digestor.",
                )

    if "syngas" in _active_extensions:
        with st.expander("Configuração da extensão Syngas (E15)", expanded=True):
            st.caption(
                "X_met_CO é a biomassa carboxidotrófica que converte CO em H₂ via WGS enzimática. "
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
                    help="CO dissolvido no afluente líquido (ex: pré-saturação). Deixe 0 para alimentação só via gás.",
                )

    if "trace_elements" in _active_extensions:
        _te_conflict = "iron" in _active_extensions
        if _te_conflict:
            st.error(
                "⚠️ **Elementos-traço (E9)** não pode ser combinado com **Ferro (E8)** nesta versão. "
                "Remova uma das extensões antes de simular."
            )
        with st.expander("Configuração da extensão Elementos-Traço (E9)", expanded=True):
            st.caption(
                "Ni e Co são micronutrientes essenciais para metanogênese. "
                "Abaixo de K_TE (~0.5 µmol/L Ni, ~0.1 µmol/L Co) os metanogênicos são inibidos. "
                "S_Fe2_TE_feed é o Fe(II) fixo no afluente (parâmetro operacional)."
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
                    help="Típico: 1–5 µmol/L = 1e-6 – 5e-6 kmolNi/m³. Abaixo de K_TE_Ni (5e-7) → inibição.",
                )
                st.number_input(
                    "Co dissolvido inicial S_Co [kmolCo/m³]",
                    min_value=0.0,
                    value=float(st.session_state.get("te_initial_s_co", 5e-7)),
                    step=1e-8,
                    format="%.2e",
                    key="te_initial_s_co",
                    help="Típico: 0.1–2 µmol/L = 1e-7 – 2e-6 kmolCo/m³. Abaixo de K_TE_Co (1e-7) → inibição.",
                )
            with _te_col2:
                st.number_input(
                    "Fe(II) afluente S_Fe2_TE_feed [kmolFe/m³]",
                    min_value=0.0,
                    value=float(st.session_state.get("te_param_s_fe2_feed", 1e-5)),
                    step=1e-6,
                    format="%.2e",
                    key="te_param_s_fe2_feed",
                    help="Fe(II) como parâmetro fixo de limitação (não estado dinâmico). ≈ 1e-5 kmol/m³ ≈ 0.56 mg Fe/L.",
                )

# ─── E14: ASM1 → ADM1 interface (optional, outside form) ─────────────────────
with st.expander("🔄 Converter influente ASM1 → ADM1 (Interface E14 / BSM2)", expanded=False):
    st.caption(
        "Use se o afluente do digestor vem de um sistema de lodos ativados (ASM1). "
        "Converte variáveis ASM1 para influente ADM1 seguindo a interface BSM2 (Nopens et al. 2009)."
    )

    _a1_col1, _a1_col2, _a1_col3, _a1_col4 = st.columns(4)
    _a1_S_S = _a1_col1.number_input("S_S [gCOD/m³]", 0.0, 50000.0, 100.0, key="a1_S_S")
    _a1_S_I = _a1_col2.number_input("S_I [gCOD/m³]", 0.0, 20000.0, 30.0, key="a1_S_I")
    _a1_X_S = _a1_col3.number_input("X_S [gCOD/m³]", 0.0, 50000.0, 200.0, key="a1_X_S")
    _a1_X_I = _a1_col4.number_input("X_I [gCOD/m³]", 0.0, 20000.0, 50.0, key="a1_X_I")

    _a1_col5, _a1_col6, _a1_col7 = st.columns(3)
    _a1_X_BH = _a1_col5.number_input("X_BH [gCOD/m³]", 0.0, 50000.0, 300.0, key="a1_X_BH")
    _a1_X_BA = _a1_col6.number_input("X_BA [gCOD/m³]", 0.0, 10000.0, 40.0, key="a1_X_BA")
    _a1_X_P = _a1_col7.number_input("X_P [gCOD/m³]", 0.0, 20000.0, 80.0, key="a1_X_P")

    _a1_col8, _a1_col9, _a1_col10, _a1_col11, _a1_col12 = st.columns(5)
    _a1_S_ND = _a1_col8.number_input("S_ND [gN/m³]", 0.0, 500.0, 2.0, key="a1_S_ND")
    _a1_X_ND = _a1_col9.number_input("X_ND [gN/m³]", 0.0, 500.0, 4.0, key="a1_X_ND")
    _a1_S_NH = _a1_col10.number_input("S_NH [gN/m³]", 0.0, 1000.0, 20.0, key="a1_S_NH")
    _a1_S_NO = _a1_col11.number_input("S_NO [gN/m³]", 0.0, 500.0, 5.0, key="a1_S_NO")
    _a1_S_ALK = _a1_col12.number_input("S_ALK [molHCO₃⁻/m³]", 0.0, 100.0, 4.0, key="a1_S_ALK")

    _a1_preset = st.selectbox(
        "Preset de frações BSM2",
        options=["BSM2 (lodo misto municipal)", "Lodo primário", "Lodo secundário aeróbio"],
        key="a1_fractions_preset",
    )

    if st.button("▶ Calcular influente ADM1", key="a1_calculate"):
        from simulator.full_model.asm_adm1_interface import (
            ASM1State,
            asm1_to_adm1_influent,
            verify_asm1_adm1_balance,
        )
        from simulator.full_model.mappings.asm1_fractions import (
            bsm2_fractions,
            primary_sludge_fractions,
            secondary_sludge_fractions,
        )

        _preset_map = {
            "BSM2 (lodo misto municipal)": bsm2_fractions(),
            "Lodo primário": primary_sludge_fractions(),
            "Lodo secundário aeróbio": secondary_sludge_fractions(),
        }
        _fracs = _preset_map[_a1_preset]

        _asm1 = ASM1State(
            S_S=_a1_S_S, S_I=_a1_S_I, X_S=_a1_X_S, X_I=_a1_X_I,
            X_BH=_a1_X_BH, X_BA=_a1_X_BA, X_P=_a1_X_P,
            S_ND=_a1_S_ND, X_ND=_a1_X_ND, S_NH=_a1_S_NH,
            S_NO=_a1_S_NO, S_ALK=_a1_S_ALK,
        )
        _influent = asm1_to_adm1_influent(_asm1, _fracs)
        _balance = verify_asm1_adm1_balance(_asm1, _influent)

        st.session_state["asm1_adm1_influent"] = _influent
        st.session_state["asm1_adm1_balance"] = _balance

        _result_rows = [
            {"Estado ADM1": k, "Valor": f"{v:.6f}", "Unidade": "kgCOD/m³" if k.startswith(("S_su", "S_aa", "S_I", "X_")) else "kmol/m³"}
            for k, v in _influent.items()
        ]
        st.dataframe(_result_rows, use_container_width=True)

        _bc1, _bc2 = st.columns(2)
        _bc1.metric("Erro balanço COD", f"{_balance['cod_error_pct']:.3f}%")
        _bc2.metric("Erro balanço N", f"{_balance['n_error_pct']:.1f}%")

        if _balance["cod_error_pct"] > 1.0:
            st.warning("Erro de COD > 1% — verificar se as frações somam 1.0")

    if "asm1_adm1_influent" in st.session_state:
        if st.button("✅ Usar como influente desta simulação", key="a1_use_influent"):
            _inf = st.session_state["asm1_adm1_influent"]
            _pcod = (
                _inf.get("X_ch", 0.0) + _inf.get("X_pr", 0.0) + _inf.get("X_li", 0.0)
                + _inf.get("X_xc", 0.0) + _inf.get("X_I", 0.0)
            )
            _scod = _inf.get("S_su", 0.0) + _inf.get("S_aa", 0.0) + _inf.get("S_I", 0.0)
            # S_IN kmolN/m³ → kgN/m³ (×14)
            _sin_kgN = _inf.get("S_IN", 0.0) * 14.0
            # S_IC kmolC/m³ ≈ alkalinity kmol/m³ eq.
            _alk = max(_inf.get("S_IC", 0.1), 0.1)

            st.session_state["manual_feed_name"] = "Influente ASM1→ADM1 (E14)"
            st.session_state["manual_particulate_cod"] = float(_pcod)
            st.session_state["manual_soluble_cod"] = float(_scod)
            st.session_state["manual_acetate"] = 0.0
            st.session_state["manual_propionate"] = 0.0
            st.session_state["manual_hydrogen"] = 0.0
            st.session_state["manual_inorganic_nitrogen"] = float(_sin_kgN)
            st.session_state["manual_alkalinity"] = float(_alk)
            st.session_state["manual_feed_ph"] = 7.0
            st.session_state["sim_substrate_mode"] = "manual"
            st.session_state["sim_skip_base_reset"] = True
            st.success("Influente ADM1 aplicado. Modo trocado para 'Manual temporário'.")
            st.rerun()


# ─── Substrate selection ──────────────────────────────────────────────────────
preset_id = None
codigestion_blend = None
if substrate_mode_label == "preset":
    preset_id = st.selectbox(
        "Preset de substrato",
        options=list(single_substrate_options),
        format_func=lambda value: single_substrate_options[value],
        key="sim_preset_id",
    )
    base_feed, base_operating, preset_link = get_preset_bundle(preset_id)
elif substrate_mode_label == "codigestion":
    _CUSTOM_KEY = "__custom__"
    all_codig_options = {**codigestion_options, _CUSTOM_KEY: "Personalizado (escolher substratos e frações)"}
    codig_preset_id = st.selectbox(
        "Preset de co-digestão",
        options=list(all_codig_options),
        format_func=lambda value: all_codig_options[value],
        key="codigestion_preset",
    )

    if codig_preset_id == _CUSTOM_KEY:
        # ── Custom blend builder ───────────────────────────────────────────────
        preset_id = None
        selected_substrates = st.multiselect(
            "Substratos a combinar",
            options=list(single_substrate_options),
            default=list(single_substrate_options)[:2],
            format_func=lambda v: single_substrate_options[v],
            key="codig_custom_substrates",
        )
        if len(selected_substrates) < 2:
            st.warning("Selecione pelo menos 2 substratos para a co-digestão.")
            codigestion_blend = None
            base_feed, base_operating = get_manual_defaults()
            preset_link = None
        else:
            frac_cols = st.columns(len(selected_substrates))
            raw_fractions: dict[str, float] = {}
            for i, sub_id in enumerate(selected_substrates):
                default_frac = round(1.0 / len(selected_substrates), 2)
                raw_fractions[sub_id] = frac_cols[i].number_input(
                    single_substrate_options[sub_id],
                    min_value=0.01,
                    max_value=0.99,
                    value=float(st.session_state.get(f"codig_frac_{sub_id}", default_frac)),
                    step=0.05,
                    format="%.2f",
                    key=f"codig_frac_{sub_id}",
                )
            total_frac = sum(raw_fractions.values())
            st.caption(f"Soma das frações: **{total_frac:.2f}** (deve ser 1,00)")
            if abs(total_frac - 1.0) > 0.005:
                st.error(f"⚠️ As frações somam {total_frac:.2f} — ajuste para que somem 1,00.")
                codigestion_blend = None
                base_feed, base_operating = get_manual_defaults()
                preset_link = None
            else:
                from simulator.core.models import CoDigestionBlend as _CDB, SubstrateFraction as _SF
                _components = []
                for sub_id, frac in raw_fractions.items():
                    sub_feed, sub_op, _ = get_preset_bundle(sub_id)
                    _components.append(_SF(feed=sub_feed, volume_fraction=round(frac / total_frac, 6)))
                _blend_name = " + ".join(
                    f"{single_substrate_options[s][:12]} {raw_fractions[s]:.0%}"
                    for s in selected_substrates
                )
                codigestion_blend = _CDB(name=_blend_name, components=_components)
                base_feed = codigestion_blend.blend()
                _dominant = max(raw_fractions, key=lambda k: raw_fractions[k])
                _, base_operating, _ = get_preset_bundle(_dominant)
                preset_link = None
                cn = codigestion_blend.cn_ratio()
                st.caption(
                    f"Blended feed: {base_feed.name} | "
                    f"Frações: {', '.join(f'{c.feed.name} {c.volume_fraction:.0%}' for c in codigestion_blend.components)} | "
                    f"C/N estimado: {cn:.1f}"
                )
                st.info("💡 Co-digestão ativa: recomenda-se o modo `fan` de inibição por amônia.")
    else:
        # ── Preset blend ───────────────────────────────────────────────────────
        preset_id = codig_preset_id
        codigestion_blend = get_codigestion_blend(codig_preset_id) if codig_preset_id else None
        if codigestion_blend is not None:
            base_feed = codigestion_blend.blend()
            from simulator.design_pipeline import CODIGESTION_PRESETS
            _cpdata = CODIGESTION_PRESETS.get(codig_preset_id, {})
            base_operating = _cpdata.get("operating", None)
            if base_operating is None:
                _, base_operating = get_manual_defaults()
            preset_link = str(_cpdata.get("note_link", codigestion_options.get(codig_preset_id, "")))
            cn = codigestion_blend.cn_ratio()
            st.caption(
                f"Componentes: {', '.join(c.feed.name for c in codigestion_blend.components)} | "
                f"Frações: {', '.join(f'{c.volume_fraction:.0%}' for c in codigestion_blend.components)} | "
                f"C/N estimado: {cn:.1f}"
            )
            st.info("💡 Co-digestão ativa: recomenda-se o modo `fan` de inibição por amônia para resultados mais realistas.")
        else:
            base_feed, base_operating = get_manual_defaults()
            preset_link = None
elif substrate_mode_label == "custom":
    # ── Substrato personalizado salvo pelo usuário ─────────────────────────────
    saved_substrates = list_custom_substrates()
    if not saved_substrates:
        st.warning("Nenhum substrato personalizado salvo. Use o painel 'Gerenciar substratos personalizados' abaixo para criar um.")
        base_feed, base_operating = get_manual_defaults()
        preset_id = None
        preset_link = None
    else:
        custom_substrate_options = {str(item["name"]): str(item["name"]) for item in saved_substrates}
        # Mantém seleção anterior se ainda válida
        _prev_custom = st.session_state.get("sim_custom_substrate_name")
        _custom_default = _prev_custom if _prev_custom in custom_substrate_options else next(iter(custom_substrate_options))
        selected_custom_name = st.selectbox(
            "Substrato personalizado",
            options=list(custom_substrate_options),
            format_func=lambda v: custom_substrate_options[v],
            index=list(custom_substrate_options).index(_custom_default) if _custom_default in custom_substrate_options else 0,
            key="sim_custom_substrate_name",
        )
        _custom_data = find_custom_substrate(selected_custom_name) or {}
        base_feed, base_operating = get_manual_defaults()
        # Carrega valores do substrato personalizado no feed base
        base_feed = base_feed.model_copy(
            update={
                "name": str(_custom_data.get("name", selected_custom_name)),
                "particulate_cod": float(_custom_data.get("particulate_cod", base_feed.particulate_cod)),
                "soluble_cod": float(_custom_data.get("soluble_cod", base_feed.soluble_cod)),
                "acetate": float(_custom_data.get("acetate", base_feed.acetate)),
                "propionate": float(_custom_data.get("propionate", base_feed.propionate)),
                "hydrogen": float(_custom_data.get("hydrogen", base_feed.hydrogen)),
                "inorganic_nitrogen": float(_custom_data.get("inorganic_nitrogen", base_feed.inorganic_nitrogen)),
                "alkalinity": float(_custom_data.get("alkalinity", base_feed.alkalinity)),
                "ph": float(_custom_data.get("ph", base_feed.ph)),
            }
        )
        preset_id = None
        preset_link = None
        st.caption(
            f"Substrato: **{selected_custom_name}** | "
            f"COD particulate: {_custom_data.get('particulate_cod', 0):.2f} | "
            f"COD soluble: {_custom_data.get('soluble_cod', 0):.2f} | "
            f"pH: {_custom_data.get('ph', 0):.2f} | "
            f"Atualizado: {_custom_data.get('updated_at', 'N/A')}"
        )
else:
    base_feed, base_operating = get_manual_defaults()
    preset_link = None

source_signature = f"{substrate_mode_label}:{preset_id or st.session_state.get('sim_custom_substrate_name') or 'manual'}"
skip_base_reset = bool(st.session_state.pop("sim_skip_base_reset", False))
if st.session_state.get("sim_base_signature") != source_signature and not skip_base_reset:
    st.session_state["volume_active"] = float(base_operating.volume_m3)
    st.session_state["temperature_active"] = float(base_operating.temperature_c)
    st.session_state["hrt_active"] = float(base_operating.hrt_days)
    if substrate_mode_label == "manual":
        st.session_state["manual_feed_name"] = base_feed.name
        st.session_state["manual_particulate_cod"] = float(base_feed.particulate_cod)
        st.session_state["manual_soluble_cod"] = float(base_feed.soluble_cod)
        st.session_state["manual_acetate"] = float(base_feed.acetate)
        st.session_state["manual_propionate"] = float(base_feed.propionate)
        st.session_state["manual_hydrogen"] = float(base_feed.hydrogen)
        st.session_state["manual_inorganic_nitrogen"] = float(base_feed.inorganic_nitrogen)
        st.session_state["manual_alkalinity"] = float(base_feed.alkalinity)
        st.session_state["manual_feed_ph"] = float(base_feed.ph)
    st.session_state["sim_base_signature"] = source_signature

predicted_backend, backend_note = resolve_requested_backend(reactor_type, backend_choice)
if backend_note:
    if predicted_backend != backend_choice:
        st.warning(backend_note)
    else:
        st.info(backend_note)

# ─── Main configuration ───────────────────────────────────────────────────────
st.subheader("Configuracao do caso")
config_col, context_col = st.columns((1.35, 0.95))
with context_col:
    st.markdown("### Contexto do substrato")
    if substrate_mode_label == "preset":
        st.markdown(f"- Preset: `{single_substrate_options.get(preset_id, preset_id)}`")
        _note_label = preset_link.removeprefix("[[").removesuffix("]]") if preset_link else ""
        st.markdown(f"- Nota tecnica: `{_note_label}`")
        render_frame(
            [
                {"parametro": "Feed", "valor": base_feed.name},
                {"parametro": "Particulate COD", "valor": f"{base_feed.particulate_cod:.3f} kgCOD/m3"},
                {"parametro": "Soluble COD", "valor": f"{base_feed.soluble_cod:.3f} kgCOD/m3"},
                {"parametro": "Acetate", "valor": f"{base_feed.acetate:.3f} kgCOD/m3"},
                {"parametro": "Propionate", "valor": f"{base_feed.propionate:.3f} kgCOD/m3"},
                {"parametro": "Influent pH", "valor": f"{base_feed.ph:.2f}"},
            ]
        )
    elif substrate_mode_label == "codigestion":
        st.markdown("- Modo co-digestão ativo.")
        if codigestion_blend:
            st.caption("Composição blended exibida acima. Frações validadas pelo modelo.")
    elif substrate_mode_label == "custom":
        st.markdown("- Substrato personalizado ativo.")
        st.caption("Substrato salvo pelo usuário. Edite no painel 'Gerenciar substratos personalizados' abaixo.")
    else:
        st.markdown("- Modo manual ativo.")
        st.caption("Os campos de alimentacao abaixo controlam diretamente a composicao simplificada usada pelo backend local.")

with config_col:
    # Seletor do modo hidráulico fora do form — widgets dentro do form não disparam
    # rerun ao serem clicados, então o radio precisa ficar aqui para trocar o campo
    # imediatamente ao ser selecionado.
    if reactor_type != "batch":
        st.radio(
            "Definir por",
            options=["hrt", "flow_rate"],
            horizontal=True,
            format_func=lambda v: {"hrt": "HRT (dias)", "flow_rate": "Vazão Q (m³/dia)"}[v],
            key="hydraulic_mode",
            help="HRT: informe diretamente o tempo de retenção hidráulico. Vazão: informe Q e HRT = V/Q é derivado.",
        )
    with st.form("simulation_form"):
        left, right = st.columns(2)
        with left:
            st.number_input(
                "Volume do reator [m3]",
                min_value=10.0,
                value=float(st.session_state.get("volume_active", base_operating.volume_m3)),
                step=50.0,
                key="volume_active",
            )
            st.number_input(
                "Temperatura [C]",
                min_value=15.0,
                max_value=60.0,
                value=float(st.session_state.get("temperature_active", base_operating.temperature_c)),
                step=0.5,
                key="temperature_active",
            )

            # ── Seletor do modo hidráulico ────────────────────────────────────
            if reactor_type == "batch":
                st.number_input(
                    "Duração do ensaio [dias]",
                    min_value=1.0,
                    value=float(st.session_state.get("duration_days", 45.0)),
                    step=1.0,
                    key="duration_days",
                    help="Para batelada, este campo define a duração total do ensaio BMP.",
                )
                # Para batelada: Q e HRT não se aplicam — desabilitados com valor fixo
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
                if st.session_state.get("hydraulic_mode", "hrt") == "hrt":
                    st.number_input(
                        "HRT [dias]",
                        min_value=0.5,
                        value=float(st.session_state.get("hrt_active", base_operating.hrt_days)),
                        step=0.5,
                        key="hrt_active",
                        help="Tempo de retenção hidráulico. A vazão Q = V / HRT é calculada automaticamente.",
                    )
                    # Mostra Q calculado como informação
                    _v_preview = float(st.session_state.get("volume_active", base_operating.volume_m3))
                    _hrt_preview = float(st.session_state.get("hrt_active", base_operating.hrt_days))
                    if _hrt_preview > 0:
                        st.caption(f"Vazão efetiva: **Q = {_v_preview / _hrt_preview:.1f} m³/dia**")
                else:
                    # Modo vazão: mostra Q e calcula HRT
                    _v_form = float(st.session_state.get("volume_active", base_operating.volume_m3))
                    _q_default = float(st.session_state.get("flow_rate_active", _v_form / max(float(st.session_state.get("hrt_active", base_operating.hrt_days)), 0.1)))
                    st.number_input(
                        "Vazão Q [m³/dia]",
                        min_value=0.1,
                        value=_q_default,
                        step=10.0,
                        key="flow_rate_active",
                        help="Vazão afluente contínua. HRT = V / Q é derivado automaticamente.",
                    )
                    # Salva HRT derivado para manter consistência da sessão
                    _q_actual = float(st.session_state.get("flow_rate_active", _q_default))
                    _hrt_derived = _v_form / max(_q_actual, 0.01)
                    st.session_state["hrt_active"] = _hrt_derived
                    st.caption(f"HRT efetivo: **{_hrt_derived:.2f} dias** (V = {_v_form:.0f} m³, Q = {_q_actual:.1f} m³/dia)")

                st.number_input(
                    "Duracao da simulacao [dias]",
                    min_value=1.0,
                    value=float(st.session_state.get("duration_days", 45.0)),
                    step=1.0,
                    key="duration_days",
                )
        with right:
            if substrate_mode_label in ("manual",):
                st.text_input("Nome da alimentacao", value=st.session_state.get("manual_feed_name", base_feed.name), key="manual_feed_name")
                st.number_input("Particulate COD [kgCOD/m3]", min_value=0.0, value=float(st.session_state.get("manual_particulate_cod", base_feed.particulate_cod)), step=0.1, key="manual_particulate_cod")
                st.number_input("Soluble COD [kgCOD/m3]", min_value=0.0, value=float(st.session_state.get("manual_soluble_cod", base_feed.soluble_cod)), step=0.1, key="manual_soluble_cod")
                st.number_input("Acetate [kgCOD/m3]", min_value=0.0, value=float(st.session_state.get("manual_acetate", base_feed.acetate)), step=0.05, key="manual_acetate")
                st.number_input("Propionate [kgCOD/m3]", min_value=0.0, value=float(st.session_state.get("manual_propionate", base_feed.propionate)), step=0.05, key="manual_propionate")
                st.number_input("Hydrogen [kgCOD/m3]", min_value=0.0, value=float(st.session_state.get("manual_hydrogen", base_feed.hydrogen)), step=0.001, format="%.4f", key="manual_hydrogen")
                st.number_input("Inorganic nitrogen [kgN/m3]", min_value=0.0, value=float(st.session_state.get("manual_inorganic_nitrogen", base_feed.inorganic_nitrogen)), step=0.05, key="manual_inorganic_nitrogen")
                st.number_input("Alkalinity [kmol/m3 eq.]", min_value=0.1, value=float(st.session_state.get("manual_alkalinity", base_feed.alkalinity)), step=0.05, key="manual_alkalinity")
                st.number_input("Influent pH", min_value=5.0, max_value=8.5, value=float(st.session_state.get("manual_feed_ph", base_feed.ph)), step=0.05, key="manual_feed_ph")
            elif substrate_mode_label == "custom":
                st.markdown("**Substrato personalizado carregado**")
                st.caption("Os valores abaixo são do substrato personalizado selecionado. Para editar, use o painel 'Gerenciar substratos personalizados'.")
                render_frame([
                    {"parametro": "Feed", "valor": base_feed.name},
                    {"parametro": "Particulate COD", "valor": f"{base_feed.particulate_cod:.3f} kgCOD/m3"},
                    {"parametro": "Soluble COD", "valor": f"{base_feed.soluble_cod:.3f} kgCOD/m3"},
                    {"parametro": "Acetate", "valor": f"{base_feed.acetate:.3f} kgCOD/m3"},
                    {"parametro": "Propionate", "valor": f"{base_feed.propionate:.3f} kgCOD/m3"},
                    {"parametro": "Influent pH", "valor": f"{base_feed.ph:.2f}"},
                    {"parametro": "Inorganic N", "valor": f"{base_feed.inorganic_nitrogen:.3f} kgN/m3"},
                    {"parametro": "Alkalinity", "valor": f"{base_feed.alkalinity:.3f} kmol/m3"},
                ])
            else:
                st.markdown("**Preset carregado**")
                st.caption("Nesta versao, o preset define a composicao da alimentacao. Use o modo manual para ajustar a composicao campo a campo.")
                render_frame(preset_rows())

        # ─── Variant config section ───────────────────────────────────────────
        if reactor_type == "uasb" and backend_choice == "full":
            st.markdown("---")
            st.markdown("**Configuração do UASB — Retenção de Biomassa**")
            vc_current = st.session_state.get("variant_config") or {}
            st.number_input(
                "Fator de arraste de biomassa (washout_factor)",
                min_value=0.05, max_value=1.0,
                value=float(vc_current.get("biomass_washout_factor", 0.35)),
                step=0.05, format="%.2f",
                key="vc_biomass_washout_factor",
                help="Fração da taxa de diluição aplicada aos estados sólidos (biomassa). "
                     "UASB típico: 0.35 (SRT ≈ 2.9×HRT). Valor 1.0 = CSTR sem retenção.",
            )

        elif reactor_type == "plug_flow" and backend_choice == "full":
            st.markdown("---")
            st.markdown("**Configuração do Plug-Flow — Tanques em Série**")
            vc_current = st.session_state.get("variant_config") or {}
            st.slider(
                "Número de segmentos (N)",
                min_value=2, max_value=20,
                value=int(vc_current.get("segments", 6)),
                step=1,
                key="vc_segments",
                help="Número de CSTRs em série para aproximar o escoamento pistão. "
                     "N=2 é o mínimo; N≥8 converge bem para plug-flow real. "
                     "Aumenta o custo computacional em N×.",
            )

        elif reactor_type == "two_phase":
            st.markdown("---")
            st.markdown("**Configuração da Variante — Duas Fases (AD)**")
            vc_current = st.session_state.get("variant_config") or {}
            vc_col1, vc_col2 = st.columns(2)
            with vc_col1:
                tp_vol_frac = st.number_input("Fração vol. fase 1 (= fração HRT)", min_value=0.10, max_value=0.60, value=float(vc_current.get("phase1_volume_fraction", 0.30)), step=0.05, key="vc_phase1_volume_fraction")
            with vc_col2:
                tp_ph1 = st.number_input("pH setpoint fase 1 (acidogênica, modelo reduzido)", min_value=4.5, max_value=6.5, value=float(vc_current.get("phase1_ph_setpoint", 5.5)), step=0.1, key="vc_phase1_ph_setpoint")
                tp_ph2 = st.number_input("pH setpoint fase 2 (metanogênica, modelo reduzido)", min_value=6.5, max_value=8.0, value=float(vc_current.get("phase2_ph_setpoint", 7.2)), step=0.1, key="vc_phase2_ph_setpoint")

        elif reactor_type == "tpad":
            st.markdown("---")
            st.markdown("**Configuração da Variante — TPAD**")
            vc_current = st.session_state.get("variant_config") or {}
            vc_col1, vc_col2 = st.columns(2)
            with vc_col1:
                tpad_thermo_t = st.number_input("Temperatura termofílica [°C]", min_value=45.0, max_value=65.0, value=float(vc_current.get("thermo_temperature_c", 55.0)), step=1.0, key="vc_thermo_temperature_c")
                tpad_thermo_hrt = st.number_input("HRT termofílico [dias]", min_value=0.5, max_value=10.0, value=float(vc_current.get("thermo_hrt_days", 3.0)), step=0.5, key="vc_thermo_hrt_days")
            with vc_col2:
                tpad_meso_t = st.number_input("Temperatura mesofílica [°C]", min_value=25.0, max_value=42.0, value=float(vc_current.get("meso_temperature_c", 35.0)), step=1.0, key="vc_meso_temperature_c")
                tpad_meso_hrt = st.number_input("HRT mesofílico [dias]", min_value=5.0, max_value=40.0, value=float(vc_current.get("meso_hrt_days", 15.0)), step=1.0, key="vc_meso_hrt_days")

        elif reactor_type == "batch":
            st.markdown("---")
            st.markdown("**Configuração da Variante — Batelada (BMP)**")
            vc_current = st.session_state.get("variant_config") or {}
            batch_inoc = st.number_input("Fração de inóculo", min_value=0.05, max_value=0.80, value=float(vc_current.get("inoculum_fraction", 0.30)), step=0.05, key="vc_inoculum_fraction")

        # ─── Advanced options ─────────────────────────────────────────────────
        with st.expander("Opcoes avancadas", expanded=False):
            adv_col1, adv_col2, adv_col3 = st.columns(3)
            with adv_col1:
                st.number_input("Pontos de avaliacao", min_value=21, max_value=601, value=int(st.session_state.get("evaluation_points", 181)), step=10, key="evaluation_points")
            with adv_col2:
                st.selectbox("Solver", options=["BDF", "Radau"], index=["BDF", "Radau"].index(str(st.session_state.get("solver_choice", "BDF"))), key="solver_choice")
            with adv_col3:
                st.checkbox("Salvar cenario em simulator/runs", value=bool(st.session_state.get("persist_case", preferences.get("persist_scenarios_by_default", True))), key="persist_case")

        # ─── Ammonia inhibition mode ──────────────────────────────────────────
        with st.expander("Parametros Cineticos Avancados", expanded=st.session_state.get("ammonia_inhibition_mode") == "fan"):
            st.selectbox(
                "Modo de Inibição por Amônia",
                options=["simple", "fan"],
                format_func=lambda v: {
                    "simple": "simple — TAN com threshold (padrão, retrocompatível)",
                    "fan": "fan — Amônia livre com equilíbrio pH/temperatura (Anthonisen, 1976)",
                }[v],
                index=["simple", "fan"].index(str(st.session_state.get("ammonia_inhibition_mode", "simple"))),
                key="ammonia_inhibition_mode",
            )

        submitted = st.form_submit_button("Executar simulacao")

# ─── Collect variant_config after form ───────────────────────────────────────
variant_config: dict | None = None
if reactor_type == "uasb" and backend_choice == "full":
    variant_config = {
        "biomass_washout_factor": float(st.session_state.get("vc_biomass_washout_factor", 0.35)),
    }
elif reactor_type == "plug_flow" and backend_choice == "full":
    variant_config = {
        "segments": int(st.session_state.get("vc_segments", 6)),
    }
elif reactor_type == "two_phase":
    variant_config = {
        "phase1_volume_fraction": float(st.session_state.get("vc_phase1_volume_fraction", 0.30)),
        "phase1_ph_setpoint": float(st.session_state.get("vc_phase1_ph_setpoint", 5.5)),
        "phase2_ph_setpoint": float(st.session_state.get("vc_phase2_ph_setpoint", 7.2)),
    }
elif reactor_type == "tpad":
    variant_config = {
        "thermo_temperature_c": float(st.session_state.get("vc_thermo_temperature_c", 55.0)),
        "thermo_hrt_days": float(st.session_state.get("vc_thermo_hrt_days", 3.0)),
        "meso_temperature_c": float(st.session_state.get("vc_meso_temperature_c", 35.0)),
        "meso_hrt_days": float(st.session_state.get("vc_meso_hrt_days", 15.0)),
    }
elif reactor_type == "batch":
    variant_config = {
        "inoculum_fraction": float(st.session_state.get("vc_inoculum_fraction", 0.30)),
    }
st.session_state["variant_config"] = variant_config

manual_feed_values = {}
if substrate_mode_label == "manual":
    manual_feed_values = {
        "name": st.session_state.get("manual_feed_name", base_feed.name),
        "particulate_cod": st.session_state.get("manual_particulate_cod", base_feed.particulate_cod),
        "soluble_cod": st.session_state.get("manual_soluble_cod", base_feed.soluble_cod),
        "acetate": st.session_state.get("manual_acetate", base_feed.acetate),
        "propionate": st.session_state.get("manual_propionate", base_feed.propionate),
        "hydrogen": st.session_state.get("manual_hydrogen", base_feed.hydrogen),
        "inorganic_nitrogen": st.session_state.get("manual_inorganic_nitrogen", base_feed.inorganic_nitrogen),
        "alkalinity": st.session_state.get("manual_alkalinity", base_feed.alkalinity),
        "ph": st.session_state.get("manual_feed_ph", base_feed.ph),
    }

# Substrato personalizado: valores já estão em base_feed (carregado acima)
custom_substrate_values_active: dict | None = None
if substrate_mode_label == "custom":
    _cs_name = st.session_state.get("sim_custom_substrate_name")
    _cs_data = find_custom_substrate(_cs_name) if _cs_name else None
    if _cs_data:
        custom_substrate_values_active = {k: _cs_data[k] for k in ("name", "particulate_cod", "soluble_cod", "acetate", "propionate", "hydrogen", "inorganic_nitrogen", "alkalinity", "ph") if k in _cs_data}

# Modo hidráulico: monta operating_values com Q ou HRT conforme selecionado
hydraulic_mode = str(st.session_state.get("hydraulic_mode", "hrt")) if reactor_type != "batch" else "hrt"
_vol = float(st.session_state.get("volume_active", base_operating.volume_m3))
_temp = float(st.session_state.get("temperature_active", base_operating.temperature_c))
_hrt = float(st.session_state.get("hrt_active", base_operating.hrt_days))
_operating_values: dict = {
    "volume_m3": _vol,
    "temperature_c": _temp,
    "hrt_days": _hrt,
}
if hydraulic_mode == "flow_rate" and reactor_type != "batch":
    _q = float(st.session_state.get("flow_rate_active", _vol / max(_hrt, 0.1)))
    _operating_values["flow_rate_m3_day"] = _q
    # HRT efetivo derivado de V/Q para exibição no resumo
    _hrt_effective = _vol / max(_q, 0.01)
    _q_effective = _q
else:
    _hrt_effective = _hrt
    _q_effective = _vol / max(_hrt, 0.01)

# Derive feed_nitrogen for contextual recommendation
_feed_nitrogen = float(base_feed.inorganic_nitrogen) if substrate_mode_label != "manual" else float(manual_feed_values.get("inorganic_nitrogen", 0.0) or 0.0)

ammonia_inhibition_mode = str(st.session_state.get("ammonia_inhibition_mode", "simple"))
_full_initial_state_overrides, _full_influent_state_overrides = _build_extension_state_overrides(_active_extensions)
_full_extension_parameter_overrides = _build_extension_parameter_overrides(_active_extensions)

validation = validate_simulation_inputs(
    reactor_type=reactor_type,
    substrate_mode=substrate_mode_label,
    manual_feed_values=manual_feed_values,
    operating_values=_operating_values,
    duration_days=float(st.session_state.get("duration_days", 45.0)),
    evaluation_points=int(st.session_state.get("evaluation_points", 181)),
    solver=str(st.session_state.get("solver_choice", "BDF")),
    backend=backend_choice,
    variant_config=variant_config,
    ammonia_inhibition_mode=ammonia_inhibition_mode,
    feed_nitrogen=_feed_nitrogen,
)

with st.expander("Checklist tecnico do caso", expanded=False):
    if validation["errors"]:
        st.markdown("**Bloqueios antes da corrida**")
        for item in validation["errors"]:
            st.markdown(f"- {item}")
    else:
        st.markdown("Nenhum bloqueio estrutural foi detectado pela validacao rapida da interface.")
    if validation["warnings"]:
        st.markdown("**Avisos para interpretacao**")
        for item in validation["warnings"]:
            st.markdown(f"- {item}")

with st.expander("Salvar preset do usuario", expanded=False):
    st.caption("Salve a configuracao atual para reutilizar o mesmo caso sem reconfigurar a tela manualmente.")
    preset_name = st.text_input("Nome do preset", key="save_user_preset_name")
    if st.button("Salvar configuracao atual", use_container_width=True):
        try:
            payload = build_user_simulation_preset_payload(st.session_state)
            save_simulation_preset(preset_name, payload)
            _queue_flash("Preset do usuario salvo com sucesso.")
            st.rerun()
        except Exception as exc:
            st.error(format_simulation_error(exc))

# ─── Gerenciar substratos personalizados ─────────────────────────────────────
with st.expander("Gerenciar substratos personalizados", expanded=False):
    st.caption(
        "Crie substratos personalizados reutilizáveis separados dos presets nativos. "
        "Cada substrato salvo pode ser selecionado no modo 'Personalizado' acima."
    )
    _saved_custom_list = list_custom_substrates()

    if _saved_custom_list:
        st.markdown("**Substratos salvos**")
        render_frame([
            {
                "nome": item.get("name"),
                "COD_part": f"{item.get('particulate_cod', 0):.2f}",
                "COD_sol": f"{item.get('soluble_cod', 0):.2f}",
                "pH": f"{item.get('ph', 0):.2f}",
                "atualizado": item.get("updated_at", ""),
            }
            for item in _saved_custom_list
        ])
        _del_name = st.selectbox(
            "Substrato para excluir",
            options=[item["name"] for item in _saved_custom_list],
            key="custom_substrate_to_delete",
        )
        if st.button("Excluir substrato selecionado", use_container_width=True):
            delete_custom_substrate(_del_name)
            _queue_flash(f"Substrato '{_del_name}' excluido.")
            st.rerun()
    else:
        st.info("Nenhum substrato personalizado salvo ainda.")

    st.markdown("---")
    st.markdown("**Criar ou atualizar substrato personalizado**")
    _cs_col1, _cs_col2 = st.columns(2)
    with _cs_col1:
        _new_cs_name = st.text_input("Nome do substrato", key="new_custom_substrate_name", placeholder="Ex: Lodo Misto Tratado")
        _new_cs_pcod = st.number_input("Particulate COD [kgCOD/m3]", min_value=0.0, value=8.0, step=0.5, key="new_cs_pcod")
        _new_cs_scod = st.number_input("Soluble COD [kgCOD/m3]", min_value=0.0, value=3.0, step=0.5, key="new_cs_scod")
        _new_cs_ac = st.number_input("Acetate [kgCOD/m3]", min_value=0.0, value=0.5, step=0.05, key="new_cs_ac")
        _new_cs_pro = st.number_input("Propionate [kgCOD/m3]", min_value=0.0, value=0.2, step=0.05, key="new_cs_pro")
    with _cs_col2:
        _new_cs_h2 = st.number_input("Hydrogen [kgCOD/m3]", min_value=0.0, value=0.001, step=0.001, format="%.4f", key="new_cs_h2")
        _new_cs_nin = st.number_input("Inorganic nitrogen [kgN/m3]", min_value=0.0, value=1.0, step=0.05, key="new_cs_nin")
        _new_cs_alk = st.number_input("Alkalinity [kmol/m3 eq.]", min_value=0.01, value=4.0, step=0.1, key="new_cs_alk")
        _new_cs_ph = st.number_input("pH", min_value=5.0, max_value=8.5, value=7.0, step=0.05, key="new_cs_ph")

    if st.button("Salvar substrato personalizado", use_container_width=True):
        try:
            if not _new_cs_name or not _new_cs_name.strip():
                st.error("Informe um nome para o substrato personalizado.")
            else:
                save_custom_substrate(
                    _new_cs_name,
                    {
                        "particulate_cod": _new_cs_pcod,
                        "soluble_cod": _new_cs_scod,
                        "acetate": _new_cs_ac,
                        "propionate": _new_cs_pro,
                        "hydrogen": _new_cs_h2,
                        "inorganic_nitrogen": _new_cs_nin,
                        "alkalinity": _new_cs_alk,
                        "ph": _new_cs_ph,
                    },
                )
                _queue_flash(f"Substrato personalizado '{_new_cs_name}' salvo.")
                st.rerun()
        except Exception as exc:
            st.error(str(exc))

if submitted:
    try:
        if validation["errors"]:
            raise ValueError("Corrija os bloqueios do checklist tecnico antes de executar a simulacao.")
        loading_backend = backend_options.get(predicted_backend, predicted_backend.upper())
        loading_message = f"Executando a simulacao ADM1 com {loading_backend} e consolidando os perfis temporais..."
        st.session_state["latest_error"] = None
        with st.spinner(loading_message):
            result = run_simulation(
                reactor_type=reactor_type,
                substrate_mode=substrate_mode_label,
                preset_id=preset_id,
                manual_feed_values=manual_feed_values,
                operating_values=_operating_values,
                duration_days=float(st.session_state.get("duration_days", 45.0)),
                evaluation_points=int(st.session_state.get("evaluation_points", 181)),
                solver=str(st.session_state.get("solver_choice", "BDF")),
                backend=backend_choice,
                persist=bool(st.session_state.get("persist_case", True)),
                ammonia_inhibition_mode=ammonia_inhibition_mode,
                variant_config=variant_config,
                blend=codigestion_blend,
                full_extensions=_active_extensions if _active_extensions else None,
                full_initial_state_overrides=_full_initial_state_overrides,
                full_influent_state_overrides=_full_influent_state_overrides,
                full_extension_parameter_overrides=_full_extension_parameter_overrides if _full_extension_parameter_overrides else None,
                custom_substrate_values=custom_substrate_values_active,
                hydraulic_mode=hydraulic_mode,
            )
        st.session_state["latest_simulation"] = result
        st.session_state["latest_error"] = None
        record_recent_simulation(result)
    except Exception as exc:
        st.session_state["latest_simulation"] = None
        st.session_state["latest_error"] = format_simulation_error(exc)

if st.session_state.get("latest_error"):
    st.error(st.session_state["latest_error"])

result = st.session_state.get("latest_simulation")
if result is not None:
    st.subheader("Resultado da simulacao")
    render_simulation_kpis(result)

    # ── Resumo de origem e modo hidráulico ────────────────────────────────────
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
    if _res_hydraulic_mode == "flow_rate":
        _summary_parts.append(f"Hidráulico: definido por **Vazão Q = {_res_q:.1f} m³/dia** → HRT efetivo = {_res_hrt:.2f} dias")
    else:
        _summary_parts.append(f"Hidráulico: definido por **HRT = {_res_hrt:.2f} dias** → Q efetivo = {_res_q:.1f} m³/dia")
    st.caption(" | ".join(_summary_parts))

    # Conditional extension KPIs
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

    # ── Diagnóstico técnico do solver full (Plano 2) ──────────────────────────
    _backend_used = str(result.metadata.get("backend_used", result.simulation.backend))
    _backend_requested = str(result.metadata.get("backend_requested", result.simulation.backend))
    _fallback_reason = result.metadata.get("fallback_reason")

    # Sinalização clara de backend solicitado vs utilizado
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

        # Cards resumidos com métricas principais
        if any(v is not None for v in [_n_state, _n_dyn, _ode_dim, _runtime]):
            _diag_cols = st.columns(4)
            if _n_state is not None:
                _diag_cols[0].metric("Estados totais", str(_n_state), help="Dimensão total do vetor de estado interno do modelo.")
            if _n_dyn is not None:
                _diag_cols[1].metric("Estados dinâmicos (EDO)", str(_n_dyn), help="Estados integrados como equações diferenciais ordinárias.")
            if _ode_dim is not None:
                _diag_cols[2].metric("Dimensão efetiva EDO", str(_ode_dim), help=f"n_dinâmico × n_segmentos = {_n_dyn} × {_n_seg}")
            if _runtime is not None:
                _diag_cols[3].metric("Tempo de execução", f"{_runtime:.3f} s", help="Tempo total de integração do solver.")

        # Expander com diagnóstico técnico detalhado
        with st.expander("Diagnostico tecnico do solver full", expanded=False):
            st.markdown(
                "O backend `full` integra numericamente as EDOs do ADM1 completo usando `scipy.integrate.solve_ivp`. "
                "Os **estados dinâmicos** são integrados diretamente; os **estados algébricos** (equilíbrio ácido-base) "
                "são resolvidos implicitamente a cada passo de tempo via iteração de Newton. "
                "Os **pseudo-estados** são variáveis derivadas (fluxos de gás, pH) calculadas analiticamente do estado dinâmico."
            )
            _tech_rows = []
            if _n_state is not None:
                _tech_rows.append({"campo": "Estados totais", "valor": str(_n_state), "descricao": "Dimensão do vetor de estado completo"})
            if _n_dyn is not None:
                _tech_rows.append({"campo": "Estados dinâmicos (EDO)", "valor": str(_n_dyn), "descricao": "Integrados via solve_ivp"})
            if _n_alg is not None:
                _tech_rows.append({"campo": "Estados algébricos", "valor": str(_n_alg), "descricao": "Equilíbrio ácido-base por iteração de Newton"})
            if _n_pseudo is not None:
                _tech_rows.append({"campo": "Pseudo-estados", "valor": str(_n_pseudo), "descricao": "Variáveis derivadas (pH, fluxo de gás)"})
            if _n_seg is not None:
                _tech_rows.append({"campo": "Segmentos", "valor": str(_n_seg), "descricao": "CSTRs em série (1 = CSTR/batch/UASB)"})
            if _ode_dim is not None:
                _tech_rows.append({"campo": "Dimensão efetiva EDO", "valor": str(_ode_dim), "descricao": f"n_dyn × n_seg = {_n_dyn} × {_n_seg}"})
            if _exts:
                _tech_rows.append({"campo": "Extensões ativas", "valor": ", ".join(_exts), "descricao": "Módulos opcionais ativados"})
            if _method:
                _tech_rows.append({"campo": "Método solver", "valor": str(_method), "descricao": "Integrador scipy (BDF recomendado para sistemas stiff)"})
            if _rtol is not None:
                _tech_rows.append({"campo": "Tolerância relativa (rtol)", "valor": f"{_rtol:.2e}", "descricao": "Critério de convergência relativo"})
            if _atol is not None:
                _tech_rows.append({"campo": "Tolerância absoluta (atol)", "valor": f"{_atol:.2e}", "descricao": "Critério de convergência absoluto"})
            if _n_pts is not None:
                _tech_rows.append({"campo": "Pontos de grade temporal", "valor": str(_n_pts), "descricao": "Número de pontos de saída (t_eval)"})
            if _nfev:
                _tech_rows.append({"campo": "Avaliações de função (nfev)", "valor": str(_nfev), "descricao": "Total de chamadas ao RHS"})
            if _njev:
                _tech_rows.append({"campo": "Avaliações do Jacobiano (njev)", "valor": str(_njev), "descricao": "Chamadas de Jacobiano do solver"})
            if _nlu:
                _tech_rows.append({"campo": "Decomposições LU (nlu)", "valor": str(_nlu), "descricao": "Fatorações LU do método implícito"})
            if _ph_conv is not None:
                _tech_rows.append({"campo": "pH convergiu", "valor": "Sim" if _ph_conv else "Nao", "descricao": "Todos os passos de pH convergiram"})
            if _ph_iter is not None:
                _tech_rows.append({"campo": "Iterações máx. pH", "valor": str(_ph_iter), "descricao": "Máximo de iterações usadas no solver de pH"})
            if _runtime is not None:
                _tech_rows.append({"campo": "Tempo de execução (s)", "valor": f"{_runtime:.4f}", "descricao": "Tempo total de integração numérica"})
            if _tech_rows:
                render_frame(_tech_rows)

    if result.reactor.reactor_type == "cstr":
        st.subheader("Comparacao de backends neste caso")
        st.caption("Executa o mesmo CSTR com `pyadm1` e `full` para explicitar paridade, fallback e deltas dos KPIs principais.")
        compare_key = f"backend_compare_{result.simulation_id}"
        if st.button("Comparar `pyadm1` vs `full`", key=compare_key, use_container_width=False):
            with st.spinner("Comparando `pyadm1` e `full` para o mesmo caso CSTR..."):
                report = compare_backends_for_result(result, backends=("pyadm1", "full"))
            st.session_state["latest_backend_comparison"] = {
                "simulation_id": result.simulation_id,
                "report": report,
            }
        comparison_state = st.session_state.get("latest_backend_comparison")
        if isinstance(comparison_state, dict) and comparison_state.get("simulation_id") == result.simulation_id:
            comparison_report = comparison_state.get("report")
            if isinstance(comparison_report, dict):
                if comparison_report.get("note"):
                    st.warning(str(comparison_report["note"]))
                render_frame(backend_comparison_frame(comparison_report))

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

    st.subheader("KPIs e snapshot de entrada")
    table_col1, table_col2 = st.columns((1.0, 1.1))
    with table_col1:
        render_summary_table(result)
    with table_col2:
        render_input_table(result)

    st.subheader("Perfis principais")
    st.caption("Use a barra de ferramentas dos graficos para exportar PNG, aplicar zoom ou inspecionar pontos especificos.")
    render_core_profile_charts(result)

    # Conditional diagnostic charts
    if result.metadata.get("ammonia_inhibition_mode") == "fan":
        render_ammonia_charts(result)

    if result.reactor.reactor_type in ("two_phase", "tpad"):
        render_phase_profile_charts(result)

    # ─── Extension-specific profiles ─────────────────────────────────────────
    _ext_requested = result.metadata.get("full_extensions_requested") or []
    if _ext_requested:
        st.subheader("Perfis de extensões do modelo")
        st.caption("Perfis temporais dos estados adicionados pelas extensões ativas nesta simulação.")

        # Map each extension to the series keys it contributes
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
        }

        import plotly.graph_objects as go

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

        # SRB KPI metrics
        if "srb" in _ext_requested:
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
                max((abs(float(value)) for value in series), default=0.0) <= 1e-12
                for series in _srb_signal_series
            )
            if _srb_all_zero:
                st.warning(
                    "A extensão SRB foi ativada, mas sulfato e biomassa SRB ficaram zerados nesta corrida. "
                    "Revise os campos de sulfato afluente e biomassa inicial da SRB."
                )

        # Phosphorus (E7) KPI metrics
        if "phosphorus" in _ext_requested:
            _sip = result.series.get("S_IP")
            _xmap = result.series.get("X_MAP")
            _ip_map = result.series.get("IP_MAP")
            if _sip or _xmap:
                p_cols = st.columns(2)
                if _sip:
                    _sip_mgP = _sip[-1] * 30_970.0  # kmolP/m³ → mgP/L
                    p_cols[0].metric("P efluente (S_IP)", f"{_sip_mgP:.1f} mgP/L")
                if _xmap:
                    _xmap_mgP = _xmap[-1] * 30_970.0
                    p_cols[1].metric("P recuperado como estruvita (X_MAP)", f"{_xmap_mgP:.1f} mgP/L")
            if _ip_map and max(_ip_map) < 1.0:
                st.warning(
                    "Estruvita não precipitou (IP_MAP < 1.0 durante toda a simulação). "
                    "Verifique S_Mg ou S_IP — podem estar baixos."
                )

        # Iron (E8) KPI metrics
        if "iron" in _ext_requested:
            _sfe2 = result.series.get("S_Fe2")
            _ip_fes = result.series.get("IP_FeS")
            if _sfe2:
                fe_cols = st.columns(2)
                _sfe2_mgFe = _sfe2[-1] * 55_845.0  # kmolFe/m³ → mgFe/L
                fe_cols[0].metric("Fe(II) efluente (S_Fe2)", f"{_sfe2_mgFe:.1f} mgFe/L")
            if _ip_fes and max(_ip_fes) < 1.0:
                st.warning(
                    "FeS não precipitou (IP_FeS < 1.0). "
                    "Verifique S_H2S (E4) e S_Fe3_feed."
                )

        # Multi-population (E12) KPI metrics
        if "multi_population" in _ext_requested:
            _frac_ac = result.series.get("fraction_oligotrophic_ac")
            _frac_h2 = result.series.get("fraction_oligotrophic_h2")
            if _frac_ac or _frac_h2:
                mp_cols = st.columns(2)
                if _frac_ac:
                    mp_cols[0].metric("Fração oligótrofa ac (steady-state)", f"{_frac_ac[-1]:.3f}")
                if _frac_h2:
                    mp_cols[1].metric("Fração oligótrofa h2 (steady-state)", f"{_frac_h2[-1]:.3f}")
                st.caption(
                    "Valor alto → condições favoráveis a oligótrofos "
                    "(baixo substrato, HRT longo)."
                )


    render_series_preview(result)
else:
    st.info("Configure o caso e clique em `Executar simulacao` para gerar os primeiros resultados na interface.")
