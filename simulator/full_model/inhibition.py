from __future__ import annotations

from typing import Mapping


def build_inhibition_factors(state: Mapping[str, float], params: Mapping[str, float]) -> dict[str, float]:
    s_h_ion = max(float(state["S_H_ion"]), 1e-14)
    s_in = max(float(state["S_IN"]), 0.0)
    s_h2 = max(float(state["S_h2"]), 0.0)
    s_nh3 = max(float(state["S_nh3"]), 0.0)

    i_ph_aa = (params["K_pH_aa"] ** params["nn_aa"]) / (s_h_ion ** params["nn_aa"] + params["K_pH_aa"] ** params["nn_aa"])
    i_ph_ac = (params["K_pH_ac"] ** params["n_ac"]) / (s_h_ion ** params["n_ac"] + params["K_pH_ac"] ** params["n_ac"])
    i_ph_h2 = (params["K_pH_h2"] ** params["n_h2"]) / (s_h_ion ** params["n_h2"] + params["K_pH_h2"] ** params["n_h2"])
    # Batstone 2002 Table A2: S_IN / (K_S_IN + S_IN); exactly zero growth without N.
    i_in_lim = s_in / (params["K_S_IN"] + s_in)
    i_h2_fa = 1.0 / (1.0 + (s_h2 / params["K_I_h2_fa"]))
    i_h2_c4 = 1.0 / (1.0 + (s_h2 / params["K_I_h2_c4"]))
    i_h2_pro = 1.0 / (1.0 + (s_h2 / params["K_I_h2_pro"]))
    i_nh3 = 1.0 / (1.0 + (s_nh3 / params["K_I_nh3"]))

    return {
        "I_pH_aa": float(i_ph_aa),
        "I_pH_ac": float(i_ph_ac),
        "I_pH_h2": float(i_ph_h2),
        "I_IN_lim": float(i_in_lim),
        "I_h2_fa": float(i_h2_fa),
        "I_h2_c4": float(i_h2_c4),
        "I_h2_pro": float(i_h2_pro),
        "I_nh3": float(i_nh3),
        "I_5": float(i_ph_aa * i_in_lim),
        "I_6": float(i_ph_aa * i_in_lim),
        "I_7": float(i_ph_aa * i_in_lim * i_h2_fa),
        "I_8": float(i_ph_aa * i_in_lim * i_h2_c4),
        "I_9": float(i_ph_aa * i_in_lim * i_h2_c4),
        "I_10": float(i_ph_aa * i_in_lim * i_h2_pro),
        "I_11": float(i_ph_ac * i_in_lim * i_nh3),
        "I_12": float(i_ph_h2 * i_in_lim),
    }
