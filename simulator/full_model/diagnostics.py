from __future__ import annotations

import numpy as np

from simulator.full_model.gas_transfer import extra_gas_molar_divisors
from simulator.full_model.model import DEFAULT_FULL_MODEL_ASSEMBLY, FullModelAssembly



def translate_full_profiles(
    *,
    full_state_matrix: np.ndarray,
    parameter_values: dict[str, float],
    assembly: FullModelAssembly = DEFAULT_FULL_MODEL_ASSEMBLY,
) -> dict[str, list[float]]:
    matrix = np.clip(np.asarray(full_state_matrix, dtype=float), a_min=0.0, a_max=None)
    series = {name: matrix[:, assembly.full_state_index[name]].astype(float).tolist() for name in assembly.full_state_names}
    s_h_ion = matrix[:, assembly.full_state_index["S_H_ion"]]
    s_gas_h2 = matrix[:, assembly.full_state_index["S_gas_h2"]]
    s_gas_ch4 = matrix[:, assembly.full_state_index["S_gas_ch4"]]
    s_gas_co2 = matrix[:, assembly.full_state_index["S_gas_co2"]]
    p_h2 = s_gas_h2 * parameter_values["R"] * parameter_values["T_op"] / 16.0
    p_ch4 = s_gas_ch4 * parameter_values["R"] * parameter_values["T_op"] / 64.0
    p_co2 = s_gas_co2 * parameter_values["R"] * parameter_values["T_op"]
    extra_pressures = {
        name: matrix[:, assembly.full_state_index[name]] * parameter_values["R"] * parameter_values["T_op"] / divisor
        for name, divisor in extra_gas_molar_divisors(assembly).items()
    }
    p_total = np.maximum(p_h2 + p_ch4 + p_co2 + sum(extra_pressures.values()) + parameter_values["p_gas_h2o"], 1e-12)
    q_gas_headspace = np.maximum(parameter_values["k_p"] * (p_total - parameter_values["p_atm"]), 0.0)
    gas_normalization = p_total / max(parameter_values["p_atm"], 1e-12)
    biogas = np.maximum(q_gas_headspace * gas_normalization, 0.0)
    methane = np.maximum(biogas * (p_ch4 / p_total), 0.0)
    co2 = np.maximum(biogas * (p_co2 / p_total), 0.0)
    hydrogen = np.maximum(biogas * (p_h2 / p_total), 0.0)
    particulate_cod = matrix[:, assembly.full_state_index["X_xc"]] + matrix[:, assembly.full_state_index["X_ch"]] + matrix[:, assembly.full_state_index["X_pr"]] + matrix[:, assembly.full_state_index["X_li"]] + matrix[:, assembly.full_state_index["X_I"]]
    soluble_cod = matrix[:, assembly.full_state_index["S_su"]] + matrix[:, assembly.full_state_index["S_aa"]] + matrix[:, assembly.full_state_index["S_fa"]] + matrix[:, assembly.full_state_index["S_I"]]
    acidogens = matrix[:, assembly.full_state_index["X_su"]] + matrix[:, assembly.full_state_index["X_aa"]] + matrix[:, assembly.full_state_index["X_fa"]] + matrix[:, assembly.full_state_index["X_c4"]]
    acetate = matrix[:, assembly.full_state_index["S_ac"]]
    propionate = matrix[:, assembly.full_state_index["S_pro"]]
    vfa_total = acetate + propionate + matrix[:, assembly.full_state_index["S_va"]] + matrix[:, assembly.full_state_index["S_bu"]]
    biomass_cod = (
        matrix[:, assembly.full_state_index["X_su"]]
        + matrix[:, assembly.full_state_index["X_aa"]]
        + matrix[:, assembly.full_state_index["X_fa"]]
        + matrix[:, assembly.full_state_index["X_c4"]]
        + matrix[:, assembly.full_state_index["X_pro"]]
        + matrix[:, assembly.full_state_index["X_ac"]]
        + matrix[:, assembly.full_state_index["X_h2"]]
    )
    dissolved_gas_cod = (
        matrix[:, assembly.full_state_index["S_h2"]]
        + matrix[:, assembly.full_state_index["S_ch4"]]
    )
    effluent_cod = particulate_cod + soluble_cod + vfa_total + biomass_cod + dissolved_gas_cod
    volatile_solids = particulate_cod + acidogens + matrix[:, assembly.full_state_index["X_pro"]] + matrix[:, assembly.full_state_index["X_ac"]] + matrix[:, assembly.full_state_index["X_h2"]]
    series.update(
        {
            "particulate_cod": particulate_cod.astype(float).tolist(),
            "soluble_cod": soluble_cod.astype(float).tolist(),
            "acetate": acetate.astype(float).tolist(),
            "propionate": propionate.astype(float).tolist(),
            "hydrogen": matrix[:, assembly.full_state_index["S_h2"]].astype(float).tolist(),
            "acidogens": acidogens.astype(float).tolist(),
            "propionate_biomass": matrix[:, assembly.full_state_index["X_pro"]].astype(float).tolist(),
            "acetoclastic_biomass": matrix[:, assembly.full_state_index["X_ac"]].astype(float).tolist(),
            "hydrogenotrophic_biomass": matrix[:, assembly.full_state_index["X_h2"]].astype(float).tolist(),
            "inorganic_nitrogen": (matrix[:, assembly.full_state_index["S_IN"]] * 14.0).astype(float).tolist(),
            "alkalinity": matrix[:, assembly.full_state_index["S_IC"]].astype(float).tolist(),
            "ph": (-np.log10(np.maximum(s_h_ion, 1e-14))).astype(float).tolist(),
            "vfa_total": vfa_total.astype(float).tolist(),
            "methane_m3_day": methane.astype(float).tolist(),
            "co2_m3_day": co2.astype(float).tolist(),
            "h2_m3_day": hydrogen.astype(float).tolist(),
            "biogas_m3_day": biogas.astype(float).tolist(),
            "ch4_fraction": np.clip(methane / np.maximum(biogas, 1e-12), 0.0, 1.0).astype(float).tolist(),
            "effluent_cod": effluent_cod.astype(float).tolist(),
            "volatile_solids_proxy": volatile_solids.astype(float).tolist(),
            "q_gas_headspace_m3_day": q_gas_headspace.astype(float).tolist(),
            "Pgas_bar": p_total.astype(float).tolist(),
        }
    )
    for gas_name, flow_name in (("S_gas_CO", "co_m3_day"), ("S_gas_H2S", "h2s_m3_day")):
        if gas_name in extra_pressures:
            series[flow_name] = (biogas * extra_pressures[gas_name] / p_total).astype(float).tolist()
    for diagnostics_hook in assembly.diagnostics_hooks:
        series.update(diagnostics_hook(matrix, assembly, parameter_values))
    return {name: [float(value) for value in values] for name, values in series.items()}
