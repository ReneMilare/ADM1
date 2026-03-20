from __future__ import annotations

from simulator.full_model.catalog_types import ProcessDefinition

PROCESS_SOURCE = "IWA ADM1.pdf; Rosen & Jeppsson (BSM2); vendor/PyADM1/src/PyADM1.py:399-442"


def _process(
    name: str,
    vendor_symbol: str,
    family: str,
    description: str,
    rate_expression: str,
    affected_states: tuple[str, ...],
    parameters: tuple[str, ...],
    inhibitions: tuple[str, ...] = (),
    notes: str = "",
) -> ProcessDefinition:
    return ProcessDefinition(
        name=name,
        vendor_symbol=vendor_symbol,
        family=family,  # type: ignore[arg-type]
        description=description,
        rate_expression=rate_expression,
        affected_states=affected_states,
        parameters=parameters,
        inhibitions=inhibitions,
        source=PROCESS_SOURCE,
        notes=notes,
    )


FULL_PROCESS_CATALOG = (
    _process("rho_1_disintegration", "Rho_1", "biochemical", "Desintegração do compósito particulado", "k_dis * X_xc", ("S_IC", "S_IN", "S_I", "X_xc", "X_ch", "X_pr", "X_li", "X_I"), ("k_dis", "f_sI_xc", "f_xI_xc", "f_ch_xc", "f_pr_xc", "f_li_xc", "N_xc", "N_I", "N_aa")),
    _process("rho_2_hydrolysis_carbohydrates", "Rho_2", "biochemical", "Hidrólise de carboidratos", "k_hyd_ch * X_ch", ("S_su", "S_IC", "X_ch"), ("k_hyd_ch",)),
    _process("rho_3_hydrolysis_proteins", "Rho_3", "biochemical", "Hidrólise de proteínas", "k_hyd_pr * X_pr", ("S_aa", "S_IC", "X_pr"), ("k_hyd_pr",)),
    _process("rho_4_hydrolysis_lipids", "Rho_4", "biochemical", "Hidrólise de lipídios", "k_hyd_li * X_li", ("S_su", "S_fa", "S_IC", "X_li"), ("k_hyd_li", "f_fa_li")),
    _process("rho_5_uptake_sugars", "Rho_5", "biochemical", "Consumo de açúcares", "k_m_su * S_su / (K_S_su + S_su) * X_su * I_5", ("S_su", "S_bu", "S_pro", "S_ac", "S_h2", "S_IC", "S_IN", "X_su"), ("k_m_su", "K_S_su", "Y_su", "f_bu_su", "f_pro_su", "f_ac_su", "f_h2_su", "N_bac"), ("I_pH_aa", "I_IN_lim")),
    _process("rho_6_uptake_amino_acids", "Rho_6", "biochemical", "Consumo de aminoácidos", "k_m_aa * S_aa / (K_S_aa + S_aa) * X_aa * I_6", ("S_aa", "S_va", "S_bu", "S_pro", "S_ac", "S_h2", "S_IC", "S_IN", "X_aa"), ("k_m_aa", "K_S_aa", "Y_aa", "f_va_aa", "f_bu_aa", "f_pro_aa", "f_ac_aa", "f_h2_aa", "N_aa", "N_bac"), ("I_pH_aa", "I_IN_lim")),
    _process("rho_7_uptake_lcfa", "Rho_7", "biochemical", "Consumo de ácidos graxos de cadeia longa", "k_m_fa * S_fa / (K_S_fa + S_fa) * X_fa * I_7", ("S_fa", "S_ac", "S_h2", "S_IC", "S_IN", "X_fa"), ("k_m_fa", "K_S_fa", "K_I_h2_fa", "Y_fa", "N_bac"), ("I_pH_aa", "I_IN_lim", "I_h2_fa")),
    _process("rho_8_uptake_valerate", "Rho_8", "biochemical", "Consumo de valerato", "k_m_c4 * S_va / (K_S_c4 + S_va) * X_c4 * (S_va / (S_bu + S_va + 1e-6)) * I_8", ("S_va", "S_pro", "S_ac", "S_h2", "S_IC", "S_IN", "X_c4"), ("k_m_c4", "K_S_c4", "K_I_h2_c4", "Y_c4", "N_bac"), ("I_pH_aa", "I_IN_lim", "I_h2_c4")),
    _process("rho_9_uptake_butyrate", "Rho_9", "biochemical", "Consumo de butirato", "k_m_c4 * S_bu / (K_S_c4 + S_bu) * X_c4 * (S_bu / (S_bu + S_va + 1e-6)) * I_9", ("S_bu", "S_ac", "S_h2", "S_IC", "S_IN", "X_c4"), ("k_m_c4", "K_S_c4", "K_I_h2_c4", "Y_c4", "N_bac"), ("I_pH_aa", "I_IN_lim", "I_h2_c4")),
    _process("rho_10_uptake_propionate", "Rho_10", "biochemical", "Consumo de propionato", "k_m_pro * S_pro / (K_S_pro + S_pro) * X_pro * I_10", ("S_pro", "S_ac", "S_h2", "S_IC", "S_IN", "X_pro"), ("k_m_pro", "K_S_pro", "K_I_h2_pro", "Y_pro", "N_bac"), ("I_pH_aa", "I_IN_lim", "I_h2_pro")),
    _process("rho_11_uptake_acetate", "Rho_11", "biochemical", "Consumo de acetato", "k_m_ac * S_ac / (K_S_ac + S_ac) * X_ac * I_11", ("S_ac", "S_ch4", "S_IC", "S_IN", "X_ac"), ("k_m_ac", "K_S_ac", "K_I_nh3", "Y_ac", "N_bac"), ("I_pH_ac", "I_IN_lim", "I_nh3")),
    _process("rho_12_uptake_hydrogen", "Rho_12", "biochemical", "Consumo de hidrogênio", "k_m_h2 * S_h2 / (K_S_h2 + S_h2) * X_h2 * I_12", ("S_h2", "S_ch4", "S_IC", "S_IN", "X_h2"), ("k_m_h2", "K_S_h2", "Y_h2", "N_bac"), ("I_pH_h2", "I_IN_lim")),
    _process("rho_13_decay_sugar_biomass", "Rho_13", "biochemical", "Decaimento de biomassa degradadora de açúcares", "k_dec_X_su * X_su", ("S_IC", "S_IN", "X_xc", "X_su"), ("k_dec_X_su", "N_bac", "N_xc")),
    _process("rho_14_decay_amino_acid_biomass", "Rho_14", "biochemical", "Decaimento de biomassa degradadora de aminoácidos", "k_dec_X_aa * X_aa", ("S_IC", "S_IN", "X_xc", "X_aa"), ("k_dec_X_aa", "N_bac", "N_xc")),
    _process("rho_15_decay_lcfa_biomass", "Rho_15", "biochemical", "Decaimento de biomassa degradadora de LCFA", "k_dec_X_fa * X_fa", ("S_IC", "S_IN", "X_xc", "X_fa"), ("k_dec_X_fa", "N_bac", "N_xc")),
    _process("rho_16_decay_c4_biomass", "Rho_16", "biochemical", "Decaimento de biomassa degradadora de C4", "k_dec_X_c4 * X_c4", ("S_IC", "S_IN", "X_xc", "X_c4"), ("k_dec_X_c4", "N_bac", "N_xc")),
    _process("rho_17_decay_propionate_biomass", "Rho_17", "biochemical", "Decaimento de biomassa degradadora de propionato", "k_dec_X_pro * X_pro", ("S_IC", "S_IN", "X_xc", "X_pro"), ("k_dec_X_pro", "N_bac", "N_xc")),
    _process("rho_18_decay_acetate_biomass", "Rho_18", "biochemical", "Decaimento de biomassa acetoclástica", "k_dec_X_ac * X_ac", ("S_IC", "S_IN", "X_xc", "X_ac"), ("k_dec_X_ac", "N_bac", "N_xc")),
    _process("rho_19_decay_hydrogen_biomass", "Rho_19", "biochemical", "Decaimento de biomassa hidrogenotrófica", "k_dec_X_h2 * X_h2", ("S_IC", "S_IN", "X_xc", "X_h2"), ("k_dec_X_h2", "N_bac", "N_xc")),
    _process("rho_A_4_valerate_dissociation", "Rho_A_4", "acid_base", "Dissociação ácido-base do valerato", "k_A_B_va * (S_va_ion * (K_a_va + S_H_ion) - K_a_va * S_va)", ("S_va", "S_va_ion", "S_H_ion"), ("k_A_B_va", "K_a_va")),
    _process("rho_A_5_butyrate_dissociation", "Rho_A_5", "acid_base", "Dissociação ácido-base do butirato", "k_A_B_bu * (S_bu_ion * (K_a_bu + S_H_ion) - K_a_bu * S_bu)", ("S_bu", "S_bu_ion", "S_H_ion"), ("k_A_B_bu", "K_a_bu")),
    _process("rho_A_6_propionate_dissociation", "Rho_A_6", "acid_base", "Dissociação ácido-base do propionato", "k_A_B_pro * (S_pro_ion * (K_a_pro + S_H_ion) - K_a_pro * S_pro)", ("S_pro", "S_pro_ion", "S_H_ion"), ("k_A_B_pro", "K_a_pro")),
    _process("rho_A_7_acetate_dissociation", "Rho_A_7", "acid_base", "Dissociação ácido-base do acetato", "k_A_B_ac * (S_ac_ion * (K_a_ac + S_H_ion) - K_a_ac * S_ac)", ("S_ac", "S_ac_ion", "S_H_ion"), ("k_A_B_ac", "K_a_ac")),
    _process("rho_A_10_co2_bicarbonate", "Rho_A_10", "acid_base", "Equilíbrio CO2/HCO3-", "k_A_B_co2 * (S_hco3_ion * (K_a_co2 + S_H_ion) - K_a_co2 * S_IC)", ("S_IC", "S_hco3_ion", "S_co2", "S_H_ion"), ("k_A_B_co2", "K_a_co2")),
    _process("rho_A_11_ammonia_ammonium", "Rho_A_11", "acid_base", "Equilíbrio NH3/NH4+", "k_A_B_IN * (S_nh3 * (K_a_IN + S_H_ion) - K_a_IN * S_IN)", ("S_IN", "S_nh3", "S_nh4_ion", "S_H_ion"), ("k_A_B_IN", "K_a_IN")),
    _process("rho_T_8_hydrogen_transfer", "Rho_T_8", "gas_transfer", "Transferência gás-líquido de H2", "k_L_a * (S_h2 - 16 * K_H_h2 * p_gas_h2)", ("S_h2", "S_gas_h2"), ("k_L_a", "K_H_h2")),
    _process("rho_T_9_methane_transfer", "Rho_T_9", "gas_transfer", "Transferência gás-líquido de CH4", "k_L_a * (S_ch4 - 64 * K_H_ch4 * p_gas_ch4)", ("S_ch4", "S_gas_ch4"), ("k_L_a", "K_H_ch4")),
    _process("rho_T_10_co2_transfer", "Rho_T_10", "gas_transfer", "Transferência gás-líquido de CO2", "k_L_a * (S_co2 - K_H_co2 * p_gas_co2)", ("S_co2", "S_gas_co2"), ("k_L_a", "K_H_co2")),
)

FULL_PROCESS_NAMES = tuple(process.name for process in FULL_PROCESS_CATALOG)
FULL_PROCESS_INDEX = {name: index for index, name in enumerate(FULL_PROCESS_NAMES)}
BIOCHEMICAL_PROCESS_NAMES = tuple(process.name for process in FULL_PROCESS_CATALOG if process.family == "biochemical")
ACID_BASE_PROCESS_NAMES = tuple(process.name for process in FULL_PROCESS_CATALOG if process.family == "acid_base")
GAS_TRANSFER_PROCESS_NAMES = tuple(process.name for process in FULL_PROCESS_CATALOG if process.family == "gas_transfer")
