"""Adaptadores entre session_state e SimulationDraft.

100% independente de Streamlit: recebe e retorna dicts simples.
Nenhum import de `streamlit` neste módulo.
"""

from __future__ import annotations

from typing import Any

from webapp.contracts import SimulationDraft

# ─── defaults de extensão ────────────────────────────────────────────────────

_EXT_STATE_DEFAULTS: dict[str, float] = {
    "srb_initial_so4": 0.01,
    "srb_initial_srb_ac": 0.10,
    "srb_initial_srb_h2": 0.05,
    "srb_initial_srb_pro": 0.05,
    "srb_initial_srb_bu": 0.05,
    "phos_initial_s_ip": 0.003,
    "iron_initial_s_fe2": 0.0005,
    "alg_initial_x_alg": 0.5,
    "syngas_initial_x_met_co": 0.05,
    "syngas_initial_s_co": 0.01,
    "syngas_initial_s_gas_co": 0.5,
    "te_initial_s_ni": 2e-6,
    "te_initial_s_co": 5e-7,
    "te_initial_s_fe2_te": 1e-5,
}

_EXT_INFLUENT_DEFAULTS: dict[str, float] = {
    "srb_influent_so4": 0.01,
    "alg_influent_x_alg": 0.5,
    "syngas_influent_s_co": 0.0,
    "te_param_s_fe2_feed": 1e-5,
}

_EXT_PARAM_DEFAULTS: dict[str, float] = {
    "phos_param_s_mg": 0.004,
    "phos_param_s_ca": 0.005,
    "iron_param_s_fe3_feed": 0.001,
    "alg_param_f_wall_alg": 0.70,
    "alg_param_f_hyd_alg": 1.0,
    "syngas_param_k_i_co": 1.4e-3,
    "syngas_param_k_i_co_h2": 5.0e-3,
    "syngas_param_f_co_to_h2": 0.65,
    "te_param_s_fe2_feed": 1e-5,
    "te_param_s_dom": 0.0,
    "te_param_k_c_ni": 27.54,
    "te_param_k_c_co": 23.99,
}

_FEED_PARAM_DEFAULTS: dict[str, float] = {
    "particulate_cod": 8.0,
    "soluble_cod": 4.0,
    "acetate": 0.5,
    "propionate": 0.2,
    "hydrogen": 0.001,
    "inorganic_nitrogen": 1.0,
    "alkalinity": 4.0,
    "sic_kmol_m3": 0.0,
    "ph": 7.0,
}


# ─── session_state → SimulationDraft ─────────────────────────────────────────

def session_state_to_draft(state: dict[str, Any]) -> SimulationDraft:
    """Converte o dict do st.session_state para SimulationDraft.

    Args:
        state: dict-like do session_state (pode ser st.session_state ou dict).

    Returns:
        SimulationDraft populado com os valores do estado atual.
    """
    feed_params: dict[str, float] = {
        key: float(state.get(f"manual_{key}", _FEED_PARAM_DEFAULTS[key]))
        for key in _FEED_PARAM_DEFAULTS
    }
    # "ph" está em manual_feed_ph, não manual_ph
    feed_params["ph"] = float(state.get("manual_feed_ph", _FEED_PARAM_DEFAULTS["ph"]))

    ext_state: dict[str, float] = {
        key: float(state.get(key, default))
        for key, default in _EXT_STATE_DEFAULTS.items()
    }
    ext_influent: dict[str, float] = {
        key: float(state.get(key, default))
        for key, default in _EXT_INFLUENT_DEFAULTS.items()
    }
    ext_params: dict[str, float] = {
        key: float(state.get(key, default))
        for key, default in _EXT_PARAM_DEFAULTS.items()
    }

    substrate_mode = str(state.get("sim_substrate_mode", "preset"))

    # For co-digestion, the active preset key is "codigestion_preset", not "sim_preset_id"
    if substrate_mode == "codigestion":
        preset_id = state.get("codigestion_preset")
        codig_preset_id = state.get("codigestion_preset")
        if codig_preset_id == "__custom__":
            selected_substrates: list[str] = list(state.get("codig_custom_substrates") or [])
            n = max(len(selected_substrates), 1)
            codigestion_fractions: dict[str, float] | None = {
                sub_id: float(state.get(f"codig_frac_{sub_id}", 1.0 / n))
                for sub_id in selected_substrates
            } if selected_substrates else None
        else:
            codigestion_fractions = None
    else:
        preset_id = state.get("sim_preset_id")
        codigestion_fractions = None

    return SimulationDraft(
        reactor_type=str(state.get("sim_reactor_type", "cstr")),
        substrate_mode=substrate_mode,
        preset_id=preset_id,
        custom_substrate_name=state.get("sim_custom_substrate_name"),
        feed_name=str(state.get("manual_feed_name", "Manual feed")),
        feed_params=feed_params,
        hydraulic_mode=str(state.get("hydraulic_mode", "hrt")),
        volume_m3=float(state.get("volume_active", 3000.0)),
        temperature_c=float(state.get("temperature_active", 35.0)),
        hrt_days=float(state.get("hrt_active", 20.0)),
        flow_rate_m3_day=float(state.get("flow_rate_active", 150.0)),
        backend_requested=str(state.get("sim_backend_choice", "full")),
        extensions=list(state.get("sim_full_extensions", [])),
        extension_state_overrides=ext_state,
        extension_influent_overrides=ext_influent,
        extension_param_overrides=ext_params,
        duration_days=float(state.get("duration_days", 45.0)),
        evaluation_points=int(state.get("evaluation_points", 181)),
        solver=str(state.get("solver_choice", "BDF")),
        persist=bool(state.get("persist_case", True)),
        ammonia_inhibition_mode=str(state.get("ammonia_inhibition_mode", "simple")),
        variant_config=state.get("variant_config"),
        codigestion_fractions=codigestion_fractions,
        origin="manual",
    )


# ─── SimulationDraft → session_state ─────────────────────────────────────────

def draft_to_session_state(draft: SimulationDraft) -> dict[str, Any]:
    """Converte um SimulationDraft de volta para o formato de chaves do session_state.

    Útil para restaurar o estado da UI ao carregar um preset ou cenário.
    """
    fp = draft.feed_params
    es = draft.extension_state_overrides
    ei = draft.extension_influent_overrides
    ep = draft.extension_param_overrides

    state: dict[str, Any] = {
        # Seletores principais
        "sim_reactor_type": draft.reactor_type,
        "sim_substrate_mode": draft.substrate_mode,
        "sim_preset_id": draft.preset_id,
        "sim_custom_substrate_name": draft.custom_substrate_name,
        "sim_backend_choice": draft.backend_requested,
        "sim_full_extensions": list(draft.extensions),
        # Operação
        "hydraulic_mode": draft.hydraulic_mode,
        "volume_active": draft.volume_m3,
        "temperature_active": draft.temperature_c,
        "hrt_active": draft.hrt_days,
        "flow_rate_active": draft.flow_rate_m3_day,
        # Simulação
        "duration_days": draft.duration_days,
        "evaluation_points": draft.evaluation_points,
        "solver_choice": draft.solver,
        "persist_case": draft.persist,
        # Inibição e variante
        "ammonia_inhibition_mode": draft.ammonia_inhibition_mode,
        "variant_config": draft.variant_config,
        # Feed manual
        "manual_feed_name": draft.feed_name or "Manual feed",
        "manual_particulate_cod": fp.get("particulate_cod", _FEED_PARAM_DEFAULTS["particulate_cod"]),
        "manual_soluble_cod": fp.get("soluble_cod", _FEED_PARAM_DEFAULTS["soluble_cod"]),
        "manual_acetate": fp.get("acetate", _FEED_PARAM_DEFAULTS["acetate"]),
        "manual_propionate": fp.get("propionate", _FEED_PARAM_DEFAULTS["propionate"]),
        "manual_hydrogen": fp.get("hydrogen", _FEED_PARAM_DEFAULTS["hydrogen"]),
        "manual_inorganic_nitrogen": fp.get("inorganic_nitrogen", _FEED_PARAM_DEFAULTS["inorganic_nitrogen"]),
        "manual_alkalinity": fp.get("alkalinity", _FEED_PARAM_DEFAULTS["alkalinity"]),
        "manual_sic_kmol_m3": fp.get("sic_kmol_m3", _FEED_PARAM_DEFAULTS["sic_kmol_m3"]),
        "manual_feed_ph": fp.get("ph", _FEED_PARAM_DEFAULTS["ph"]),
        # Extensão: estado inicial
        **{key: es.get(key, default) for key, default in _EXT_STATE_DEFAULTS.items()},
        # Extensão: influente
        **{key: ei.get(key, default) for key, default in _EXT_INFLUENT_DEFAULTS.items()},
        # Extensão: parâmetros
        **{key: ep.get(key, default) for key, default in _EXT_PARAM_DEFAULTS.items()},
    }
    # Restore co-digestion UI state
    if draft.substrate_mode == "codigestion":
        state["codigestion_preset"] = draft.preset_id
        if draft.preset_id == "__custom__" and draft.codigestion_fractions:
            state["codig_custom_substrates"] = list(draft.codigestion_fractions.keys())
            for sub_id, frac in draft.codigestion_fractions.items():
                state[f"codig_frac_{sub_id}"] = frac
    return state


# ─── preset_payload → SimulationDraft ────────────────────────────────────────

def preset_payload_to_draft(payload: dict[str, Any]) -> SimulationDraft:
    """Converte um payload de preset salvo para SimulationDraft.

    Compatível com payloads antigos (sem schema_version) e novos (com schema_version).
    """
    from webapp.services.preferences_service import migrate_preset_payload  # local import evita circular

    payload = migrate_preset_payload(payload)

    operating = payload.get("operating") or {}
    simulation = payload.get("simulation") or {}
    manual_feed = payload.get("manual_feed_values") or {}
    ext_inputs = payload.get("full_extension_state_inputs") or {}
    ext_influent = payload.get("full_extension_influent_inputs") or {}
    ext_params = payload.get("full_extension_param_inputs") or {}

    feed_params: dict[str, float] = {
        key: float(manual_feed.get(key, _FEED_PARAM_DEFAULTS[key]))
        for key in _FEED_PARAM_DEFAULTS
    }

    ext_state: dict[str, float] = {
        key: float(ext_inputs.get(key, default))
        for key, default in _EXT_STATE_DEFAULTS.items()
    }
    ext_influent_dict: dict[str, float] = {
        key: float(ext_influent.get(key, default))
        for key, default in _EXT_INFLUENT_DEFAULTS.items()
    }
    ext_params_dict: dict[str, float] = {
        key: float(ext_params.get(key, default))
        for key, default in _EXT_PARAM_DEFAULTS.items()
    }

    hydraulic_mode = str(operating.get("hydraulic_mode", "hrt"))

    return SimulationDraft(
        reactor_type=str(payload.get("reactor_type", "cstr")),
        substrate_mode=str(payload.get("substrate_mode", "preset")),
        preset_id=payload.get("preset_id"),
        custom_substrate_name=payload.get("custom_substrate_name"),
        feed_name=str(manual_feed.get("name", "Manual feed")),
        feed_params=feed_params,
        hydraulic_mode=hydraulic_mode,
        volume_m3=float(operating.get("volume_m3", 3000.0)),
        temperature_c=float(operating.get("temperature_c", 35.0)),
        hrt_days=float(operating.get("hrt_days", 20.0)),
        flow_rate_m3_day=float(operating.get("flow_rate_m3_day", 150.0)),
        backend_requested=str(payload.get("backend_choice", "full")),
        extensions=list(payload.get("sim_full_extensions") or []),
        extension_state_overrides=ext_state,
        extension_influent_overrides=ext_influent_dict,
        extension_param_overrides=ext_params_dict,
        duration_days=float(simulation.get("duration_days", 45.0)),
        evaluation_points=int(simulation.get("evaluation_points", 181)),
        solver=str(simulation.get("solver", "BDF")),
        persist=bool(simulation.get("persist", True)),
        ammonia_inhibition_mode=str(payload.get("ammonia_inhibition_mode", "simple")),
        variant_config=payload.get("variant_config"),
        origin="preset_user",
    )


# ─── SimulationDraft → preset_payload ────────────────────────────────────────

def draft_to_preset_payload(draft: SimulationDraft) -> dict[str, Any]:
    """Converte SimulationDraft para o formato de payload do preset.

    Compatível com apply_user_simulation_preset() em simulation_service.py.
    O payload resultante inclui schema_version: "1" e todos os campos de extensão.
    """
    fp = draft.feed_params
    es = draft.extension_state_overrides
    ei = draft.extension_influent_overrides
    ep = draft.extension_param_overrides

    operating: dict[str, Any] = {
        "volume_m3": draft.volume_m3,
        "temperature_c": draft.temperature_c,
        "hrt_days": draft.hrt_days,
        "hydraulic_mode": draft.hydraulic_mode,
    }
    if draft.hydraulic_mode == "flow_rate":
        operating["flow_rate_m3_day"] = draft.flow_rate_m3_day

    return {
        "reactor_type": draft.reactor_type,
        "substrate_mode": draft.substrate_mode,
        "preset_id": draft.preset_id,
        "custom_substrate_name": draft.custom_substrate_name,
        "backend_choice": draft.backend_requested,   # compatibilidade com apply_user_simulation_preset
        "ammonia_inhibition_mode": draft.ammonia_inhibition_mode,
        "variant_config": draft.variant_config,
        "operating": operating,
        "simulation": {
            "duration_days": draft.duration_days,
            "evaluation_points": draft.evaluation_points,
            "solver": draft.solver,
            "persist": draft.persist,
        },
        "manual_feed_values": {
            "name": draft.feed_name or "Manual feed",
            **{key: fp.get(key, _FEED_PARAM_DEFAULTS[key]) for key in _FEED_PARAM_DEFAULTS},
        },
        # Compatibilidade com apply_user_simulation_preset (lê apenas chaves SRB)
        "full_extension_state_inputs": {key: es.get(key, default) for key, default in _EXT_STATE_DEFAULTS.items()},
        # Campos novos (schema v1) — para uso futuro e preset_payload_to_draft
        "full_extension_influent_inputs": {key: ei.get(key, default) for key, default in _EXT_INFLUENT_DEFAULTS.items()},
        "full_extension_param_inputs": {key: ep.get(key, default) for key, default in _EXT_PARAM_DEFAULTS.items()},
        "sim_full_extensions": list(draft.extensions),
        "schema_version": "1",
    }
