"""Actions de simulação — sem Streamlit, recebe/retorna contratos.

Encapsula toda a lógica de construção de payload (FeedDefinition,
blends de co-digestão, overrides de extensão) que antes residia na
função _run_simulation_from_state() da página 01_Simular_Reator.py.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from webapp.contracts import SimulationDraft, SimulationReviewSnapshot
from webapp.state.adapters import draft_to_session_state, session_state_to_draft
from webapp.state.review import build_review_snapshot

if TYPE_CHECKING:
    from simulator.core.models import SimulationResult


# ─── Helpers de extensão ──────────────────────────────────────────────────────

def _build_extension_state_and_influent(
    draft: SimulationDraft,
) -> tuple[dict[str, float], dict[str, float]]:
    """Constrói overrides de estado inicial e influente a partir do draft."""
    active = draft.extensions
    es = draft.extension_state_overrides
    ei = draft.extension_influent_overrides

    initial: dict[str, float] = {}
    influent: dict[str, float] = {}

    if "srb" in active:
        for name, key, default in [
            ("S_SO4",    "srb_initial_so4",    0.01),
            ("X_SRB_ac", "srb_initial_srb_ac", 0.10),
            ("X_SRB_h2", "srb_initial_srb_h2", 0.05),
            ("X_SRB_pro","srb_initial_srb_pro", 0.05),
            ("X_SRB_bu", "srb_initial_srb_bu",  0.05),
        ]:
            val = float(es.get(key, default))
            if abs(val) > 0.0:
                initial[name] = val
        so4_in = float(ei.get("srb_influent_so4", 0.01))
        if abs(so4_in) > 0.0:
            influent["S_SO4"] = so4_in

    if "phosphorus" in active:
        s_ip = float(es.get("phos_initial_s_ip", 0.003))
        if s_ip > 0.0:
            initial["S_IP"] = s_ip

    if "iron" in active:
        s_fe2 = float(es.get("iron_initial_s_fe2", 0.0005))
        if s_fe2 > 0.0:
            initial["S_Fe2"] = s_fe2

    if "microalgae" in active:
        x_alg = float(es.get("alg_initial_x_alg", 0.5))
        if x_alg > 0.0:
            initial["X_alg"] = x_alg
        x_alg_in = float(ei.get("alg_influent_x_alg", 0.5))
        if x_alg_in > 0.0:
            influent["X_alg"] = x_alg_in

    if "syngas" in active:
        for name, key, default in [
            ("X_met_CO", "syngas_initial_x_met_co", 0.05),
            ("S_CO",     "syngas_initial_s_co",     0.01),
            ("S_gas_CO", "syngas_initial_s_gas_co", 0.5),
        ]:
            val = float(es.get(key, default))
            if val > 0.0:
                initial[name] = val
        s_co_in = float(ei.get("syngas_influent_s_co", 0.0))
        if s_co_in > 0.0:
            influent["S_CO"] = s_co_in

    if "trace_elements" in active:
        ep = draft.extension_param_overrides
        s_ni  = float(es.get("te_initial_s_ni", 2e-6))
        s_cob = float(es.get("te_initial_s_co", 5e-7))
        s_fe2 = float(es.get("te_initial_s_fe2_te", 1e-5))
        s_fe2_feed = float(ei.get("te_param_s_fe2_feed", ep.get("te_param_s_fe2_feed", 1e-5)))
        if s_ni > 0.0:
            initial["S_Ni"] = s_ni
            influent["S_Ni"] = s_ni
        if s_cob > 0.0:
            initial["S_Co"] = s_cob
            influent["S_Co"] = s_cob
        if s_fe2 > 0.0:
            initial["S_Fe2_te"] = s_fe2
        if s_fe2_feed > 0.0:
            influent["S_Fe2_te"] = s_fe2_feed

    return initial, influent


def _build_extension_params(draft: SimulationDraft) -> dict[str, float]:
    """Constrói overrides de parâmetros de extensão a partir do draft."""
    active = draft.extensions
    ep = draft.extension_param_overrides
    overrides: dict[str, float] = {}

    if "phosphorus" in active:
        overrides["S_Mg"] = float(ep.get("phos_param_s_mg", 0.004))
        overrides["S_Ca"] = float(ep.get("phos_param_s_ca", 0.005))
    if "iron" in active:
        overrides["S_Fe3_feed"] = float(ep.get("iron_param_s_fe3_feed", 0.001))
    if "trace_elements" in active:
        overrides["S_Fe2_te_feed"] = float(ep.get("te_param_s_fe2_feed", 1e-5))
        overrides["S_DOM_TE"]      = float(ep.get("te_param_s_dom", 0.0))
        overrides["K_c_Ni"]        = float(ep.get("te_param_k_c_ni", 27.54))
        overrides["K_c_Co"]        = float(ep.get("te_param_k_c_co", 23.99))
    if "microalgae" in active:
        overrides["f_wall_alg"] = float(ep.get("alg_param_f_wall_alg", 0.7))
        overrides["f_hyd_alg"]  = float(ep.get("alg_param_f_hyd_alg", 1.0))
    if "syngas" in active:
        overrides["K_I_CO"]     = float(ep.get("syngas_param_k_i_co",    1.4e-3))
        overrides["K_I_CO_h2"]  = float(ep.get("syngas_param_k_i_co_h2", 5.0e-3))
        overrides["f_co_to_h2"] = float(ep.get("syngas_param_f_co_to_h2", 0.65))

    return overrides


def _build_codigestion_blend(draft: SimulationDraft) -> Any | None:
    """Constrói CoDigestionBlend para modos de co-digestão, ou None."""
    from webapp.utils.presets import (
        CODIGESTION_PRESET_LABELS,
        get_codigestion_blend,
        get_preset_bundle,
        get_substrate_options,
    )

    preset_id = draft.preset_id

    if preset_id and preset_id != "__custom__":
        return get_codigestion_blend(preset_id)

    # Blend personalizado: reconstrói a partir das frações armazenadas no draft
    if preset_id == "__custom__" and draft.codigestion_fractions:
        fractions = draft.codigestion_fractions
        if len(fractions) < 2:
            return None
        total_frac = sum(fractions.values())
        if abs(total_frac - 1.0) > 0.005:
            return None
        from simulator.core.models import CoDigestionBlend, SubstrateFraction
        substrate_options = get_substrate_options()
        single_opts = {k: v for k, v in substrate_options.items() if k not in CODIGESTION_PRESET_LABELS}
        components = []
        for sub_id, frac in fractions.items():
            sub_feed, _, _ = get_preset_bundle(sub_id)
            components.append(SubstrateFraction(feed=sub_feed, volume_fraction=round(frac / total_frac, 6)))
        blend_name = " + ".join(
            f"{single_opts.get(s, s)[:12]} {fractions[s]:.0%}" for s in fractions
        )
        return CoDigestionBlend(name=blend_name, components=components)

    return None


# ─── API pública ──────────────────────────────────────────────────────────────

def load_draft_from_state(state: dict) -> SimulationDraft:
    """Wrapper sobre session_state_to_draft."""
    return session_state_to_draft(state)


def review_draft(draft: SimulationDraft) -> SimulationReviewSnapshot:
    """Wrapper sobre build_review_snapshot."""
    return build_review_snapshot(draft)


def execute_simulation(
    draft: SimulationDraft,
) -> tuple[SimulationResult | None, str | None]:
    """Executa simulação a partir do draft.

    Constrói FeedDefinition, OperatingConditions, overrides de extensão e blend
    de co-digestão a partir do draft e chama run_simulation.
    Retorna (result, None) em caso de sucesso ou (None, error_message) em falha.
    NÃO depende de st.session_state.
    """
    from webapp.services.simulation_service import (
        format_simulation_error,
        run_simulation,
        validate_simulation_inputs,
    )
    from webapp.utils.presets import get_preset_bundle

    reactor_type   = draft.reactor_type
    substrate_mode = draft.substrate_mode
    backend_choice = draft.backend_requested
    preset_id      = draft.preset_id
    active_extensions = list(draft.extensions)
    ammonia_inhibition_mode = draft.ammonia_inhibition_mode
    variant_config = draft.variant_config

    hydraulic_mode = draft.hydraulic_mode if reactor_type != "batch" else "hrt"
    operating_values: dict[str, float] = {
        "volume_m3":    draft.volume_m3,
        "temperature_c": draft.temperature_c,
        "hrt_days":     draft.hrt_days,
    }
    if hydraulic_mode == "flow_rate" and reactor_type != "batch":
        operating_values["flow_rate_m3_day"] = draft.flow_rate_m3_day

    # Feed manual
    manual_feed_values: dict[str, Any] = {}
    if substrate_mode == "manual":
        fp = draft.feed_params
        manual_feed_values = {
            "name":                draft.feed_name or "Manual feed",
            "particulate_cod":     fp.get("particulate_cod",     8.0),
            "soluble_cod":         fp.get("soluble_cod",         4.0),
            "acetate":             fp.get("acetate",             0.5),
            "propionate":          fp.get("propionate",          0.2),
            "hydrogen":            fp.get("hydrogen",            0.001),
            "inorganic_nitrogen":  fp.get("inorganic_nitrogen",  1.0),
            "alkalinity":          fp.get("alkalinity",          4.0),
            "ph":                  fp.get("ph",                  7.0),
        }

    # Substrato personalizado salvo
    custom_substrate_values: dict[str, Any] | None = None
    if substrate_mode == "custom" and draft.custom_substrate_name:
        from webapp.services.preferences_service import find_custom_substrate
        cs_data = find_custom_substrate(draft.custom_substrate_name)
        if cs_data:
            custom_substrate_values = {
                k: cs_data[k]
                for k in ("name", "particulate_cod", "soluble_cod", "acetate",
                          "propionate", "hydrogen", "inorganic_nitrogen", "alkalinity", "ph")
                if k in cs_data
            }

    # Blend de co-digestão
    codigestion_blend = None
    if substrate_mode == "codigestion":
        codigestion_blend = _build_codigestion_blend(draft)

    # Overrides de extensão
    full_initial_state_overrides, full_influent_state_overrides = (
        _build_extension_state_and_influent(draft)
    )
    full_extension_parameter_overrides = _build_extension_params(draft)

    # Nitrogênio do feed para validação
    if substrate_mode == "manual":
        _feed_nitrogen = float(manual_feed_values.get("inorganic_nitrogen", 0.0) or 0.0)
    else:
        try:
            if substrate_mode == "preset" and preset_id:
                _bf, _, _ = get_preset_bundle(preset_id)
                _feed_nitrogen = float(_bf.inorganic_nitrogen)
            else:
                _feed_nitrogen = 0.0
        except Exception:
            _feed_nitrogen = 0.0

    validation = validate_simulation_inputs(
        reactor_type=reactor_type,
        substrate_mode=substrate_mode,
        manual_feed_values=manual_feed_values,
        operating_values=operating_values,
        duration_days=draft.duration_days,
        evaluation_points=draft.evaluation_points,
        solver=draft.solver,
        backend=backend_choice,
        variant_config=variant_config,
        ammonia_inhibition_mode=ammonia_inhibition_mode,
        feed_nitrogen=_feed_nitrogen,
    )
    if validation["errors"]:
        return None, "Corrija os bloqueios antes de executar: " + "; ".join(validation["errors"])

    try:
        result = run_simulation(
            reactor_type=reactor_type,
            substrate_mode=substrate_mode,
            preset_id=preset_id,
            manual_feed_values=manual_feed_values,
            operating_values=operating_values,
            duration_days=draft.duration_days,
            evaluation_points=draft.evaluation_points,
            solver=draft.solver,
            backend=backend_choice,
            persist=draft.persist,
            ammonia_inhibition_mode=ammonia_inhibition_mode,
            variant_config=variant_config,
            blend=codigestion_blend,
            full_extensions=active_extensions or None,
            full_initial_state_overrides=full_initial_state_overrides,
            full_influent_state_overrides=full_influent_state_overrides,
            full_extension_parameter_overrides=full_extension_parameter_overrides or None,
            custom_substrate_values=custom_substrate_values,
            hydraulic_mode=hydraulic_mode,
        )
        return result, None
    except Exception as exc:
        return None, format_simulation_error(exc)


def save_draft_to_state(draft: SimulationDraft) -> dict:
    """Wrapper sobre draft_to_session_state."""
    return draft_to_session_state(draft)
