from __future__ import annotations

from typing import Mapping

from simulator.full_model.model import DEFAULT_FULL_MODEL_ASSEMBLY, FullModelAssembly
from simulator.full_model.inhibition import build_inhibition_factors


BIOCHEMICAL_RATE_ORDER = DEFAULT_FULL_MODEL_ASSEMBLY.biochemical_process_names



def biochemical_rates(
    state: Mapping[str, float],
    params: Mapping[str, float],
    *,
    assembly: FullModelAssembly = DEFAULT_FULL_MODEL_ASSEMBLY,
) -> tuple[dict[str, float], dict[str, float]]:
    inhibitions = build_inhibition_factors(state, params)
    s_su = max(float(state["S_su"]), 0.0)
    s_aa = max(float(state["S_aa"]), 0.0)
    s_fa = max(float(state["S_fa"]), 0.0)
    s_va = max(float(state["S_va"]), 0.0)
    s_bu = max(float(state["S_bu"]), 0.0)
    s_pro = max(float(state["S_pro"]), 0.0)
    s_ac = max(float(state["S_ac"]), 0.0)
    s_h2 = max(float(state["S_h2"]), 0.0)
    rates = {
        "rho_1_disintegration": params["k_dis"] * max(float(state["X_xc"]), 0.0),
        "rho_2_hydrolysis_carbohydrates": params["k_hyd_ch"] * max(float(state["X_ch"]), 0.0),
        "rho_3_hydrolysis_proteins": params["k_hyd_pr"] * max(float(state["X_pr"]), 0.0),
        "rho_4_hydrolysis_lipids": params["k_hyd_li"] * max(float(state["X_li"]), 0.0),
        "rho_5_uptake_sugars": params["k_m_su"] * s_su / (params["K_S_su"] + s_su) * max(float(state["X_su"]), 0.0) * inhibitions["I_5"],
        "rho_6_uptake_amino_acids": params["k_m_aa"] * s_aa / (params["K_S_aa"] + s_aa) * max(float(state["X_aa"]), 0.0) * inhibitions["I_6"],
        "rho_7_uptake_lcfa": params["k_m_fa"] * s_fa / (params["K_S_fa"] + s_fa) * max(float(state["X_fa"]), 0.0) * inhibitions["I_7"],
        "rho_8_uptake_valerate": params["k_m_c4"] * s_va / (params["K_S_c4"] + s_va) * max(float(state["X_c4"]), 0.0) * (s_va / max(s_bu + s_va + 1e-6, 1e-6)) * inhibitions["I_8"],
        "rho_9_uptake_butyrate": params["k_m_c4"] * s_bu / (params["K_S_c4"] + s_bu) * max(float(state["X_c4"]), 0.0) * (s_bu / max(s_bu + s_va + 1e-6, 1e-6)) * inhibitions["I_9"],
        "rho_10_uptake_propionate": params["k_m_pro"] * s_pro / (params["K_S_pro"] + s_pro) * max(float(state["X_pro"]), 0.0) * inhibitions["I_10"],
        "rho_11_uptake_acetate": params["k_m_ac"] * s_ac / (params["K_S_ac"] + s_ac) * max(float(state["X_ac"]), 0.0) * inhibitions["I_11"],
        "rho_12_uptake_hydrogen": params["k_m_h2"] * s_h2 / (params["K_S_h2"] + s_h2) * max(float(state["X_h2"]), 0.0) * inhibitions["I_12"],
        "rho_13_decay_sugar_biomass": params["k_dec_X_su"] * max(float(state["X_su"]), 0.0),
        "rho_14_decay_amino_acid_biomass": params["k_dec_X_aa"] * max(float(state["X_aa"]), 0.0),
        "rho_15_decay_lcfa_biomass": params["k_dec_X_fa"] * max(float(state["X_fa"]), 0.0),
        "rho_16_decay_c4_biomass": params["k_dec_X_c4"] * max(float(state["X_c4"]), 0.0),
        "rho_17_decay_propionate_biomass": params["k_dec_X_pro"] * max(float(state["X_pro"]), 0.0),
        "rho_18_decay_acetate_biomass": params["k_dec_X_ac"] * max(float(state["X_ac"]), 0.0),
        "rho_19_decay_hydrogen_biomass": params["k_dec_X_h2"] * max(float(state["X_h2"]), 0.0),
    }
    for rate_function in assembly.extension_rate_functions:
        extension_rates = rate_function(state, params)
        overlap = set(extension_rates).intersection(rates)
        if overlap:
            raise ValueError(f"Processos bioquímicos duplicados entre núcleo e extensões: {sorted(overlap)}")
        rates.update({name: float(value) for name, value in extension_rates.items()})
    # Apply cross-process inhibition hooks (e.g., H2S on methanogenesis, LCFA contact inhibition,
    # phenolics on methanogenesis). Each hook returns {process_name: factor} where factor ∈ [0,1].
    # Multiple hooks for the same process are applied multiplicatively (AND logic).
    for hook in assembly.extension_inhibition_hooks:
        factors = hook(state, params)
        for process_name, factor in factors.items():
            if process_name in rates:
                rates[process_name] = rates[process_name] * max(float(factor), 0.0)
    missing = [name for name in assembly.biochemical_process_names if name not in rates]
    if missing:
        raise ValueError(f"Taxas bioquímicas ausentes no assembly full: {missing}")
    return {name: float(rates[name]) for name in assembly.biochemical_process_names}, inhibitions
