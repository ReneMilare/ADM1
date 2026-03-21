from __future__ import annotations

from simulator.full_model.catalog_types import RelationDefinition
from simulator.full_model.process_catalog import ACID_BASE_PROCESS_NAMES, BIOCHEMICAL_PROCESS_NAMES, GAS_TRANSFER_PROCESS_NAMES
from simulator.full_model.state_catalog import FULL_STATE_NAMES

STOICH_SOURCE = "Rosen & Jeppsson (BSM2); vendor/PyADM1/src/PyADM1.py:446-543,575-585"

CARBON_SIGMA_TERMS = {
    "s_1": "-C_xc + f_sI_xc * C_sI + f_ch_xc * C_ch + f_pr_xc * C_pr + f_li_xc * C_li + f_xI_xc * C_xI",
    "s_2": "-C_ch + C_su",
    "s_3": "-C_pr + C_aa",
    "s_4": "-C_li + (1 - f_fa_li) * C_su + f_fa_li * C_fa",
    "s_5": "-C_su + (1 - Y_su) * ((1 - f_lac_su - f_et_su) * (f_bu_su * C_bu + f_pro_su * C_pro + f_ac_su * C_ac) + f_lac_su * C_lac + f_et_su * C_et) + Y_su * C_bac",
    "s_6": "-C_aa + (1 - Y_aa) * (f_va_aa * C_va + f_bu_aa * C_bu + f_pro_aa * C_pro + f_ac_aa * C_ac) + Y_aa * C_bac",
    "s_7": "-C_fa + (1 - Y_fa) * 0.7 * C_ac + Y_fa * C_bac",
    "s_8": "-C_va + (1 - Y_c4) * 0.54 * C_pro + (1 - Y_c4) * 0.31 * C_ac + Y_c4 * C_bac",
    "s_9": "-C_bu + (1 - Y_c4) * 0.8 * C_ac + Y_c4 * C_bac",
    "s_10": "-C_pro + (1 - Y_pro) * 0.57 * C_ac + Y_pro * C_bac",
    "s_11": "-C_ac + (1 - Y_ac) * C_ch4 + Y_ac * C_bac",
    "s_12": "(1 - Y_h2) * C_ch4 + Y_h2 * C_bac",
    "s_13": "-C_bac + C_xc",
}

BIOCHEMICAL_STOICHIOMETRY_ROWS = {
    "rho_1_disintegration": {
        "S_IC": "-s_1",
        "S_IN": "N_xc - f_xI_xc * N_I - f_sI_xc * N_I - f_pr_xc * N_aa",
        "S_I": "f_sI_xc",
        "X_xc": "-1",
        "X_ch": "f_ch_xc",
        "X_pr": "f_pr_xc",
        "X_li": "f_li_xc",
        "X_I": "f_xI_xc",
    },
    "rho_2_hydrolysis_carbohydrates": {"S_su": "1", "S_IC": "-s_2", "X_ch": "-1"},
    "rho_3_hydrolysis_proteins": {"S_aa": "1", "S_IC": "-s_3", "X_pr": "-1"},
    "rho_4_hydrolysis_lipids": {"S_su": "1 - f_fa_li", "S_fa": "f_fa_li", "S_IC": "-s_4", "X_li": "-1"},
    "rho_5_uptake_sugars": {
        # VFA/H2 fractions are scaled by (1 - f_lac_su - f_et_su) to make room for lactate/ethanol
        # overflow products when E6/E10 are active. When both are 0 (default), this reduces to
        # the original ADM1 stoichiometry. S_lac and S_et entries are added by E6/E10 patches.
        "S_su": "-1",
        "S_bu": "(1 - Y_su) * f_bu_su * (1 - f_lac_su - f_et_su)",
        "S_pro": "(1 - Y_su) * f_pro_su * (1 - f_lac_su - f_et_su)",
        "S_ac": "(1 - Y_su) * f_ac_su * (1 - f_lac_su - f_et_su)",
        "S_h2": "(1 - Y_su) * f_h2_su * (1 - f_lac_su - f_et_su)",
        "S_IC": "-s_5",
        "S_IN": "-Y_su * N_bac",
        "X_su": "Y_su",
    },
    "rho_6_uptake_amino_acids": {
        "S_aa": "-1",
        "S_va": "(1 - Y_aa) * f_va_aa",
        "S_bu": "(1 - Y_aa) * f_bu_aa",
        "S_pro": "(1 - Y_aa) * f_pro_aa",
        "S_ac": "(1 - Y_aa) * f_ac_aa",
        "S_h2": "(1 - Y_aa) * f_h2_aa",
        "S_IC": "-s_6",
        "S_IN": "N_aa - Y_aa * N_bac",
        "X_aa": "Y_aa",
    },
    "rho_7_uptake_lcfa": {
        "S_fa": "-1",
        "S_ac": "(1 - Y_fa) * 0.7",
        "S_h2": "(1 - Y_fa) * 0.3",
        "S_IC": "-s_7",
        "S_IN": "-Y_fa * N_bac",
        "X_fa": "Y_fa",
    },
    "rho_8_uptake_valerate": {
        "S_va": "-1",
        "S_pro": "(1 - Y_c4) * 0.54",
        "S_ac": "(1 - Y_c4) * 0.31",
        "S_h2": "(1 - Y_c4) * 0.15",
        "S_IC": "-s_8",
        "S_IN": "-Y_c4 * N_bac",
        "X_c4": "Y_c4",
    },
    "rho_9_uptake_butyrate": {
        "S_bu": "-1",
        "S_ac": "(1 - Y_c4) * 0.8",
        "S_h2": "(1 - Y_c4) * 0.2",
        "S_IC": "-s_9",
        "S_IN": "-Y_c4 * N_bac",
        "X_c4": "Y_c4",
    },
    "rho_10_uptake_propionate": {
        "S_pro": "-1",
        "S_ac": "(1 - Y_pro) * 0.57",
        "S_h2": "(1 - Y_pro) * 0.43",
        "S_IC": "-s_10",
        "S_IN": "-Y_pro * N_bac",
        "X_pro": "Y_pro",
    },
    "rho_11_uptake_acetate": {
        "S_ac": "-1",
        "S_ch4": "1 - Y_ac",
        "S_IC": "-s_11",
        "S_IN": "-Y_ac * N_bac",
        "X_ac": "Y_ac",
    },
    "rho_12_uptake_hydrogen": {
        "S_h2": "-1",
        "S_ch4": "1 - Y_h2",
        "S_IC": "-s_12",
        "S_IN": "-Y_h2 * N_bac",
        "X_h2": "Y_h2",
    },
    "rho_13_decay_sugar_biomass": {"S_IC": "-s_13", "S_IN": "N_bac - N_xc", "X_xc": "1", "X_su": "-1"},
    "rho_14_decay_amino_acid_biomass": {"S_IC": "-s_13", "S_IN": "N_bac - N_xc", "X_xc": "1", "X_aa": "-1"},
    "rho_15_decay_lcfa_biomass": {"S_IC": "-s_13", "S_IN": "N_bac - N_xc", "X_xc": "1", "X_fa": "-1"},
    "rho_16_decay_c4_biomass": {"S_IC": "-s_13", "S_IN": "N_bac - N_xc", "X_xc": "1", "X_c4": "-1"},
    "rho_17_decay_propionate_biomass": {"S_IC": "-s_13", "S_IN": "N_bac - N_xc", "X_xc": "1", "X_pro": "-1"},
    "rho_18_decay_acetate_biomass": {"S_IC": "-s_13", "S_IN": "N_bac - N_xc", "X_xc": "1", "X_ac": "-1"},
    "rho_19_decay_hydrogen_biomass": {"S_IC": "-s_13", "S_IN": "N_bac - N_xc", "X_xc": "1", "X_h2": "-1"},
}

ACID_BASE_RELATIONS = {
    "rho_A_4_valerate_dissociation": RelationDefinition("rho_A_4_valerate_dissociation", "S_va_ion * (K_a_va + S_H_ion) - K_a_va * S_va", ("S_va", "S_va_ion", "S_H_ion"), STOICH_SOURCE),
    "rho_A_5_butyrate_dissociation": RelationDefinition("rho_A_5_butyrate_dissociation", "S_bu_ion * (K_a_bu + S_H_ion) - K_a_bu * S_bu", ("S_bu", "S_bu_ion", "S_H_ion"), STOICH_SOURCE),
    "rho_A_6_propionate_dissociation": RelationDefinition("rho_A_6_propionate_dissociation", "S_pro_ion * (K_a_pro + S_H_ion) - K_a_pro * S_pro", ("S_pro", "S_pro_ion", "S_H_ion"), STOICH_SOURCE),
    "rho_A_7_acetate_dissociation": RelationDefinition("rho_A_7_acetate_dissociation", "S_ac_ion * (K_a_ac + S_H_ion) - K_a_ac * S_ac", ("S_ac", "S_ac_ion", "S_H_ion"), STOICH_SOURCE),
    "rho_A_10_co2_bicarbonate": RelationDefinition("rho_A_10_co2_bicarbonate", "S_hco3_ion * (K_a_co2 + S_H_ion) - K_a_co2 * S_IC", ("S_IC", "S_hco3_ion", "S_H_ion"), STOICH_SOURCE),
    "rho_A_11_ammonia_ammonium": RelationDefinition("rho_A_11_ammonia_ammonium", "S_nh3 * (K_a_IN + S_H_ion) - K_a_IN * S_IN", ("S_IN", "S_nh3", "S_H_ion"), STOICH_SOURCE),
}

GAS_TRANSFER_RELATIONS = {
    "rho_T_8_hydrogen_transfer": RelationDefinition("rho_T_8_hydrogen_transfer", "S_h2 - 16 * K_H_h2 * p_gas_h2", ("S_h2", "S_gas_h2"), STOICH_SOURCE),
    "rho_T_9_methane_transfer": RelationDefinition("rho_T_9_methane_transfer", "S_ch4 - 64 * K_H_ch4 * p_gas_ch4", ("S_ch4", "S_gas_ch4"), STOICH_SOURCE),
    "rho_T_10_co2_transfer": RelationDefinition("rho_T_10_co2_transfer", "S_co2 - K_H_co2 * p_gas_co2", ("S_co2", "S_gas_co2"), STOICH_SOURCE),
}

CHARGE_BALANCE_RESIDUAL = RelationDefinition(
    "charge_balance_S_H_ion",
    "S_cation + (S_IN - S_nh3) + S_H_ion - S_hco3_ion - S_ac_ion / 64.0 - S_pro_ion / 112.0 - S_bu_ion / 160.0 - S_va_ion / 208.0 - K_w / S_H_ion - S_anion",
    ("S_cation", "S_anion", "S_IN", "S_nh3", "S_H_ion", "S_hco3_ion", "S_ac_ion", "S_pro_ion", "S_bu_ion", "S_va_ion"),
    STOICH_SOURCE,
    notes="Residual zerado por Newton-Raphson na formulação escolhida para a Fase 2.",
)


def dense_biochemical_symbolic_matrix() -> tuple[tuple[str, ...], tuple[str, ...], tuple[tuple[str, ...], ...]]:
    rows = []
    for process_name in BIOCHEMICAL_PROCESS_NAMES:
        sparse_row = BIOCHEMICAL_STOICHIOMETRY_ROWS[process_name]
        rows.append(tuple(sparse_row.get(state_name, "0") for state_name in FULL_STATE_NAMES))
    return FULL_STATE_NAMES, BIOCHEMICAL_PROCESS_NAMES, tuple(rows)


def _validate_catalog_references() -> None:
    state_set = set(FULL_STATE_NAMES)
    for sparse_row in BIOCHEMICAL_STOICHIOMETRY_ROWS.values():
        unknown_states = set(sparse_row) - state_set
        if unknown_states:
            raise ValueError(f"Estados desconhecidos na estequiometria ADM1 full: {sorted(unknown_states)}")
    if set(BIOCHEMICAL_STOICHIOMETRY_ROWS) != set(BIOCHEMICAL_PROCESS_NAMES):
        raise ValueError("As linhas bioquímicas não cobrem exatamente os processos bioquímicos catalogados.")
    if set(ACID_BASE_RELATIONS) != set(ACID_BASE_PROCESS_NAMES):
        raise ValueError("As relações ácido-base não cobrem exatamente os processos ácido-base catalogados.")
    if set(GAS_TRANSFER_RELATIONS) != set(GAS_TRANSFER_PROCESS_NAMES):
        raise ValueError("As relações de transferência não cobrem exatamente os processos gasosos catalogados.")


_validate_catalog_references()
