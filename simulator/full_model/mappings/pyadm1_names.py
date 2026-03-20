from __future__ import annotations

PYADM1_SOLUBLE_STATES = (
    "S_su",
    "S_aa",
    "S_fa",
    "S_va",
    "S_bu",
    "S_pro",
    "S_ac",
    "S_h2",
    "S_ch4",
    "S_IC",
    "S_IN",
    "S_I",
)

PYADM1_PARTICULATE_STATES = (
    "X_xc",
    "X_ch",
    "X_pr",
    "X_li",
    "X_su",
    "X_aa",
    "X_fa",
    "X_c4",
    "X_pro",
    "X_ac",
    "X_h2",
    "X_I",
)

PYADM1_CHARGE_STATES = (
    "S_cation",
    "S_anion",
)

PYADM1_ACID_BASE_STATES = (
    "S_H_ion",
    "S_va_ion",
    "S_bu_ion",
    "S_pro_ion",
    "S_ac_ion",
    "S_hco3_ion",
    "S_co2",
    "S_nh3",
    "S_nh4_ion",
)

PYADM1_GAS_STATES = (
    "S_gas_h2",
    "S_gas_ch4",
    "S_gas_co2",
)

PYADM1_STATE_ORDER = (
    *PYADM1_SOLUBLE_STATES,
    *PYADM1_PARTICULATE_STATES,
    *PYADM1_CHARGE_STATES,
    *PYADM1_ACID_BASE_STATES,
    *PYADM1_GAS_STATES,
)

PYADM1_INTERNAL_TO_RESULT_ALIAS = {
    "S_H_ion": "pH",
}

PYADM1_RESULT_ORDER = (
    "S_su",
    "S_aa",
    "S_fa",
    "S_va",
    "S_bu",
    "S_pro",
    "S_ac",
    "S_h2",
    "S_ch4",
    "S_IC",
    "S_IN",
    "S_I",
    "X_xc",
    "X_ch",
    "X_pr",
    "X_li",
    "X_su",
    "X_aa",
    "X_fa",
    "X_c4",
    "X_pro",
    "X_ac",
    "X_h2",
    "X_I",
    "S_cation",
    "S_anion",
    "pH",
    "S_va_ion",
    "S_bu_ion",
    "S_pro_ion",
    "S_ac_ion",
    "S_hco3_ion",
    "S_co2",
    "S_nh3",
    "S_nh4_ion",
    "S_gas_h2",
    "S_gas_ch4",
    "S_gas_co2",
)
