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
    delete_simulation_preset,
    get_preferences,
    list_simulation_presets,
    record_recent_simulation,
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
        options=["preset", "codigestion", "manual"],
        horizontal=True,
        format_func=lambda value: {"preset": "Preset", "codigestion": "Co-digestão", "manual": "Manual"}[value],
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
}

_active_extensions: list[str] = []
if backend_choice == "full":
    try:
        _available_ext = list_registered_extensions()
    except Exception:
        _available_ext = list(_EXTENSION_DESCRIPTIONS)
    _ext_labels = {k: _EXTENSION_DESCRIPTIONS.get(k, k) for k in _available_ext}
    _active_extensions = st.multiselect(
        "Extensões do modelo full ADM1",
        options=list(_ext_labels),
        format_func=lambda v: _ext_labels.get(v, v),
        default=st.session_state.get("sim_full_extensions", []),
        key="sim_full_extensions",
        help="Selecione módulos opcionais a ativar no backend full. Cada extensão adiciona estados e processos ao modelo.",
    )


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
else:
    base_feed, base_operating = get_manual_defaults()
    preset_link = None

source_signature = f"{substrate_mode_label}:{preset_id or 'manual'}"
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
        st.markdown(f"- Nota tecnica: {preset_link}")
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
    else:
        st.markdown("- Modo manual ativo.")
        st.caption("Os campos de alimentacao abaixo controlam diretamente a composicao simplificada usada pelo backend local.")

with config_col:
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
            if reactor_type == "batch":
                st.number_input(
                    "Duração do ensaio [dias]",
                    min_value=1.0,
                    value=float(st.session_state.get("duration_days", 45.0)),
                    step=1.0,
                    key="duration_days",
                    help="Para batelada, este campo define a duração total do ensaio BMP.",
                )
                # HRT hidden for batch — use a fixed placeholder value
                st.number_input(
                    "HRT [dias] (não usado em batelada)",
                    min_value=0.5,
                    value=float(st.session_state.get("hrt_active", 20.0)),
                    step=0.5,
                    key="hrt_active",
                    disabled=True,
                )
            else:
                st.number_input(
                    "HRT [dias]",
                    min_value=0.5,
                    value=float(st.session_state.get("hrt_active", base_operating.hrt_days)),
                    step=0.5,
                    key="hrt_active",
                )
                st.number_input(
                    "Duracao da simulacao [dias]",
                    min_value=1.0,
                    value=float(st.session_state.get("duration_days", 45.0)),
                    step=1.0,
                    key="duration_days",
                )
        with right:
            if substrate_mode_label == "manual":
                st.text_input("Nome da alimentacao", value=st.session_state.get("manual_feed_name", base_feed.name), key="manual_feed_name")
                st.number_input("Particulate COD [kgCOD/m3]", min_value=0.0, value=float(st.session_state.get("manual_particulate_cod", base_feed.particulate_cod)), step=0.1, key="manual_particulate_cod")
                st.number_input("Soluble COD [kgCOD/m3]", min_value=0.0, value=float(st.session_state.get("manual_soluble_cod", base_feed.soluble_cod)), step=0.1, key="manual_soluble_cod")
                st.number_input("Acetate [kgCOD/m3]", min_value=0.0, value=float(st.session_state.get("manual_acetate", base_feed.acetate)), step=0.05, key="manual_acetate")
                st.number_input("Propionate [kgCOD/m3]", min_value=0.0, value=float(st.session_state.get("manual_propionate", base_feed.propionate)), step=0.05, key="manual_propionate")
                st.number_input("Hydrogen [kgCOD/m3]", min_value=0.0, value=float(st.session_state.get("manual_hydrogen", base_feed.hydrogen)), step=0.001, format="%.4f", key="manual_hydrogen")
                st.number_input("Inorganic nitrogen [kgN/m3]", min_value=0.0, value=float(st.session_state.get("manual_inorganic_nitrogen", base_feed.inorganic_nitrogen)), step=0.05, key="manual_inorganic_nitrogen")
                st.number_input("Alkalinity [kmol/m3 eq.]", min_value=0.1, value=float(st.session_state.get("manual_alkalinity", base_feed.alkalinity)), step=0.05, key="manual_alkalinity")
                st.number_input("Influent pH", min_value=5.0, max_value=8.5, value=float(st.session_state.get("manual_feed_ph", base_feed.ph)), step=0.05, key="manual_feed_ph")
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
                tp_vol_frac = st.number_input("Fração vol. fase 1", min_value=0.10, max_value=0.60, value=float(vc_current.get("phase1_volume_fraction", 0.30)), step=0.05, key="vc_phase1_volume_fraction")
                tp_hrt_frac = st.number_input("Fração HRT fase 1", min_value=0.05, max_value=0.50, value=float(vc_current.get("phase1_hrt_fraction", 0.20)), step=0.05, key="vc_phase1_hrt_fraction")
            with vc_col2:
                tp_ph1 = st.number_input("pH setpoint fase 1 (acidogênica)", min_value=4.5, max_value=6.5, value=float(vc_current.get("phase1_ph_setpoint", 5.5)), step=0.1, key="vc_phase1_ph_setpoint")
                tp_ph2 = st.number_input("pH setpoint fase 2 (metanogênica)", min_value=6.5, max_value=8.0, value=float(vc_current.get("phase2_ph_setpoint", 7.2)), step=0.1, key="vc_phase2_ph_setpoint")

        elif reactor_type == "tpad":
            st.markdown("---")
            st.markdown("**Configuração da Variante — TPAD**")
            vc_current = st.session_state.get("variant_config") or {}
            vc_col1, vc_col2 = st.columns(2)
            with vc_col1:
                tpad_thermo_t = st.number_input("Temperatura termofílica [°C]", min_value=45.0, max_value=65.0, value=float(vc_current.get("thermo_temperature_c", 55.0)), step=1.0, key="vc_thermo_temperature_c")
                tpad_thermo_hrt = st.number_input("HRT termofílico [dias]", min_value=0.5, max_value=10.0, value=float(vc_current.get("thermo_hrt_days", 3.0)), step=0.5, key="vc_thermo_hrt_days")
                tpad_thermo_vol = st.number_input("Fração vol. termofílica", min_value=0.10, max_value=0.50, value=float(vc_current.get("thermo_volume_fraction", 0.25)), step=0.05, key="vc_thermo_volume_fraction")
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
        "phase1_hrt_fraction": float(st.session_state.get("vc_phase1_hrt_fraction", 0.20)),
        "phase1_ph_setpoint": float(st.session_state.get("vc_phase1_ph_setpoint", 5.5)),
        "phase2_ph_setpoint": float(st.session_state.get("vc_phase2_ph_setpoint", 7.2)),
    }
elif reactor_type == "tpad":
    variant_config = {
        "thermo_temperature_c": float(st.session_state.get("vc_thermo_temperature_c", 55.0)),
        "thermo_hrt_days": float(st.session_state.get("vc_thermo_hrt_days", 3.0)),
        "thermo_volume_fraction": float(st.session_state.get("vc_thermo_volume_fraction", 0.25)),
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

# Derive feed_nitrogen for contextual recommendation
_feed_nitrogen = float(base_feed.inorganic_nitrogen) if substrate_mode_label != "manual" else float(manual_feed_values.get("inorganic_nitrogen", 0.0) or 0.0)

ammonia_inhibition_mode = str(st.session_state.get("ammonia_inhibition_mode", "simple"))

validation = validate_simulation_inputs(
    reactor_type=reactor_type,
    substrate_mode=substrate_mode_label,
    manual_feed_values=manual_feed_values,
    operating_values={
        "volume_m3": st.session_state.get("volume_active", base_operating.volume_m3),
        "temperature_c": st.session_state.get("temperature_active", base_operating.temperature_c),
        "hrt_days": st.session_state.get("hrt_active", base_operating.hrt_days),
    },
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
                operating_values={
                    "volume_m3": st.session_state.get("volume_active", base_operating.volume_m3),
                    "temperature_c": st.session_state.get("temperature_active", base_operating.temperature_c),
                    "hrt_days": st.session_state.get("hrt_active", base_operating.hrt_days),
                },
                duration_days=float(st.session_state.get("duration_days", 45.0)),
                evaluation_points=int(st.session_state.get("evaluation_points", 181)),
                solver=str(st.session_state.get("solver_choice", "BDF")),
                backend=backend_choice,
                persist=bool(st.session_state.get("persist_case", True)),
                ammonia_inhibition_mode=ammonia_inhibition_mode,
                variant_config=variant_config,
                blend=codigestion_blend,
                full_extensions=_active_extensions if _active_extensions else None,
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
                ("S_SO4", "Sulfato S_SO4 [kgCOD/m³]"),
                ("S_H2S", "Sulfeto H₂S S_H2S [kgCOD/m³]"),
                ("X_SRB_ac", "Biomassa SRB acetoclástica X_SRB_ac [kgCOD/m³]"),
                ("X_SRB_h2", "Biomassa SRB hidrogenotrófica X_SRB_h2 [kgCOD/m³]"),
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
        }

        import plotly.graph_objects as go

        for _ext_name in _ext_requested:
            _ext_series_defs = _EXT_SERIES.get(_ext_name, [])
            _available = [(key, label) for key, label in _ext_series_defs if result.series.get(key)]
            if not _available:
                continue
            with st.expander(f"🔬 {_EXTENSION_DESCRIPTIONS.get(_ext_name, _ext_name)}", expanded=True):
                _t = result.series.get("time_days") or list(range(len(next(iter(_available))[0])))
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
                        _cols[i % 2].plotly_chart(_fig, use_container_width=True)

        # SRB KPI metrics
        if "srb" in _ext_requested:
            _so4_s = result.series.get("S_SO4")
            _h2s_s = result.series.get("S_H2S")
            if _so4_s or _h2s_s:
                srb_cols = st.columns(2)
                if _so4_s:
                    srb_cols[0].metric("Sulfato efluente (S_SO4)", f"{_so4_s[-1]:.4f} kgCOD/m³")
                if _h2s_s:
                    srb_cols[1].metric("Sulfeto efluente (S_H2S)", f"{_h2s_s[-1]:.4f} kgCOD/m³")


    render_series_preview(result)
else:
    st.info("Configure o caso e clique em `Executar simulacao` para gerar os primeiros resultados na interface.")