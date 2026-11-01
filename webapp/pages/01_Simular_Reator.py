from __future__ import annotations

from _bootstrap import ensure_project_root

ensure_project_root()

import streamlit as st

from webapp.components.status_cards import (
    render_issue_messages,
    render_sidebar_panel,
    render_summary_cards,
    render_usage_guide,
    render_workflow_links,
)
from webapp.contracts import SimulationDraft, SimulationReviewSnapshot
from webapp.pages.sections.case_definition import render_case_definition
from webapp.pages.sections.draft_sidebar import render_draft_sidebar
from webapp.pages.sections.extensions_config import render_extensions_config
from webapp.pages.sections.operating_config import render_operating_config
from webapp.pages.sections.preset_panel import render_preset_panel
from webapp.pages.sections.result_area import render_result_area
from webapp.pages.sections.substrate_config import render_substrate_config
from webapp.pages.sections.technical_review import render_technical_review
from webapp.services.health import collect_health_snapshot
from webapp.services.preferences_service import (
    find_custom_substrate,
    get_preferences,
    list_simulation_presets,
    record_recent_simulation,
)
from webapp.features.simulation_actions import execute_simulation
from webapp.services.simulation_service import apply_user_simulation_preset, get_backend_options
from webapp.state.adapters import session_state_to_draft
from webapp.state.review import build_review_snapshot
from webapp.state.session_state import ensure_session_state
from webapp.utils.page_config import configure_page, render_page_header
from webapp.utils.presets import (
    CODIGESTION_PRESET_LABELS,
    get_substrate_options,
)

FLASH_KEY = "simular_reator_flash"
PENDING_MANUAL_FEED_KEY = "sim_pending_manual_feed_application"
PENDING_PRESET_KEY = "sim_pending_preset_payload"


def _queue_flash(message: str) -> None:
    st.session_state[FLASH_KEY] = message


def _render_flash() -> None:
    message = st.session_state.pop(FLASH_KEY, None)
    if message:
        st.toast(message)


def _apply_pending_manual_feed_update() -> None:
    payload = st.session_state.pop(PENDING_MANUAL_FEED_KEY, None)
    if not isinstance(payload, dict):
        return

    manual_feed_values = payload.get("manual_feed_values")
    if isinstance(manual_feed_values, dict):
        if "name" in manual_feed_values:
            st.session_state["manual_feed_name"] = str(manual_feed_values["name"])
        for key in (
            "particulate_cod",
            "soluble_cod",
            "acetate",
            "propionate",
            "hydrogen",
            "inorganic_nitrogen",
            "alkalinity",
            "sic_kmol_m3",
        ):
            if key in manual_feed_values:
                st.session_state[f"manual_{key}"] = float(manual_feed_values[key])
        if "ph" in manual_feed_values:
            st.session_state["manual_feed_ph"] = float(manual_feed_values["ph"])

    target_substrate_mode = payload.get("substrate_mode")
    if target_substrate_mode is not None and str(st.session_state.get("sim_substrate_mode")) != str(target_substrate_mode):
        st.session_state["sim_substrate_mode"] = str(target_substrate_mode)
    if target_substrate_mode is not None:
        st.session_state["sim_substrate_mode_selector"] = str(target_substrate_mode)
    target_manual_input_mode = payload.get("manual_input_mode")
    if (
        target_manual_input_mode is not None
        and str(st.session_state.get("sim_manual_input_mode")) != str(target_manual_input_mode)
    ):
        st.session_state["sim_manual_input_mode"] = str(target_manual_input_mode)
    if target_manual_input_mode is not None:
        st.session_state["sim_manual_input_mode_selector"] = str(target_manual_input_mode)
    if payload.get("skip_base_reset"):
        st.session_state["sim_skip_base_reset"] = True
    if payload.get("flash_message"):
        _queue_flash(str(payload["flash_message"]))


def _apply_pending_preset_payload() -> None:
    payload = st.session_state.pop(PENDING_PRESET_KEY, None)
    if not isinstance(payload, dict):
        return
    apply_user_simulation_preset(st.session_state, payload)
    st.session_state["sim_substrate_mode_selector"] = str(st.session_state.get("sim_substrate_mode", "preset"))
    st.session_state["sim_manual_input_mode_selector"] = str(st.session_state.get("sim_manual_input_mode", "manual"))
    st.session_state["sim_skip_base_reset"] = True
    preset_name = payload.get("__pending_preset_name")
    if preset_name:
        _queue_flash(f"Preset `{preset_name}` aplicado.")


# --- Page setup ---

configure_page("Simular Reator")
ensure_session_state()
snapshot = collect_health_snapshot()
st.session_state["recent_page"] = "simular_reator"

preferences = get_preferences()
substrate_options = get_substrate_options()
single_substrate_options = {k: v for k, v in substrate_options.items() if k not in CODIGESTION_PRESET_LABELS}
codigestion_options = {k: v for k, v in substrate_options.items() if k in CODIGESTION_PRESET_LABELS}
default_preset_id = next(iter(single_substrate_options)) if single_substrate_options else None

session_defaults = {
    "sim_reactor_type": preferences.get("default_reactor", "cstr"),
    "sim_substrate_mode": "preset",
    "sim_substrate_mode_selector": "preset",
    "sim_manual_input_mode": "manual",
    "sim_manual_input_mode_selector": "manual",
    "sim_preset_id": default_preset_id,
    "sim_custom_substrate_name": None,
    "sim_backend_choice": preferences.get("default_backend", "full"),
    "sim_ui_mode": "operador",
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
    "alg_param_f_wall_alg": 0.70,
    "alg_param_f_hyd_alg": 1.0,
    "syngas_initial_x_met_co": 0.05,
    "syngas_initial_s_co": 0.01,
    "syngas_initial_s_gas_co": 0.5,
    "syngas_influent_s_co": 0.0,
    "te_initial_s_ni": 2e-6,
    "te_initial_s_co": 5e-7,
    "te_initial_s_fe2_te": 1e-5,
    "te_param_s_fe2_feed": 1e-5,
    "te_param_s_dom": 0.0,
    "te_param_k_c_ni": 27.54,
    "te_param_k_c_co": 23.99,
    "hydraulic_mode": "hrt",
    "flow_rate_active": 150.0,
    "manual_sic_kmol_m3": 0.0,
}
for key, value in session_defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value

_apply_pending_preset_payload()
_apply_pending_manual_feed_update()

# --- Draft e review ---

draft: SimulationDraft = session_state_to_draft(dict(st.session_state))
review: SimulationReviewSnapshot = build_review_snapshot(draft)

# --- Sidebar ---

with st.sidebar:
    render_sidebar_panel(snapshot, current_page="Simular Reator")
    render_draft_sidebar(draft, review)

# --- Header e status ---

render_page_header(
    title="Simular Reator",
    description=(
        "Fluxo principal: configurar o caso, validar os inputs, salvar presets "
        "e rodar a simulação ADM1 sem sair da web UI."
    ),
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
    ],
)
render_usage_guide(
    title="Como usar esta tela",
    summary="Escolha um preset tecnico, valide o caso, rode a simulação e, se fizer sentido, salve a configuracao como preset do usuario.",
    steps=[
        "Escolha o reator, o modo de alimentacao e o backend na aba 📋 Definir Caso.",
        "Revise volume, temperatura e HRT na aba ⚙️ Operação.",
        "Use as extensoes opcionais na aba 🔬 Avançado (backend full apenas).",
        "Verifique a revisao tecnica antes de executar.",
        "Execute e persista o cenario se quiser compara-lo em outra tela.",
    ],
    tips=[
        "Para CSTR, 'auto' continua em pyadm1; use 'full' explicitamente para o backend nativo.",
        "No modo Operador, campos avancados ficam ocultos para reduzir carga cognitiva.",
        "Se estiver explorando um caso recorrente, salve-o como preset do usuario.",
    ],
)

# --- Painel de presets ---

render_preset_panel()

# --- Jornada principal em tabs ---

tab1, tab2, tab3 = st.tabs(["📋 Definir Caso", "⚙️ Operação", "🔬 Avançado"])

with tab1:
    render_case_definition()
    st.caption("Modelo reduzido: exploratório, use para tendências, não para dimensionamento.")
    st.divider()
    render_substrate_config()

with tab2:
    render_operating_config()

with tab3:
    render_extensions_config()

# --- Revisao tecnica ---

st.divider()

draft = session_state_to_draft(dict(st.session_state))
review = build_review_snapshot(draft)

can_run = render_technical_review(review)

# --- Botao de execucao ---

if can_run:
    if st.button("Executar simulação", type="primary", width="stretch"):
        backend_options = get_backend_options()
        _backend_label = backend_options.get(review.backend_predicted, review.backend_predicted.upper())
        with st.spinner(f"Executando a simulação ADM1 com {_backend_label}..."):
            result, error = execute_simulation(draft)
        if error:
            st.session_state["latest_simulation"] = None
            st.session_state["latest_error"] = error
        else:
            st.session_state["latest_simulation"] = result
            st.session_state["latest_error"] = None
            record_recent_simulation(result)
        st.rerun()

if st.session_state.get("latest_error"):
    st.error(st.session_state["latest_error"])

# --- Resultado ---

latest_simulation = st.session_state.get("latest_simulation")
if latest_simulation:
    st.divider()
    st.subheader("Resultado da simulação")
    if latest_simulation.metadata.get("backend_used", latest_simulation.simulation.backend) == "reduced":
        st.info("Modelo reduzido: exploratório, use para tendências, não para dimensionamento.")
    render_result_area(
        latest_simulation,
        show_advanced=(st.session_state.get("sim_ui_mode") == "especialista"),
    )
else:
    st.info("Configure o caso e clique em Executar simulação para gerar os primeiros resultados.")
