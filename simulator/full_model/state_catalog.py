from __future__ import annotations

from simulator.full_model.catalog_types import StateDefinition
from simulator.full_model.mappings.pyadm1_names import PYADM1_STATE_ORDER
from simulator.full_model.units import KG_COD_M3, KMOL_M3

STATE_SOURCE = "IWA ADM1.pdf; Rosen & Jeppsson (BSM2); vendor/PyADM1/src/PyADM1.py:79-118,575-585"


def _state(
    name: str,
    description: str,
    unit: str,
    *,
    phase: str,
    domain: str,
    role: str,
    cod_role: str,
    elemental_proxy: str | None,
    notes: str = "",
    result_alias: str | None = None,
) -> StateDefinition:
    return StateDefinition(
        name=name,
        pyadm1_name=name,
        result_alias=result_alias,
        description=description,
        unit=unit,
        phase=phase,
        domain=domain,
        role=role,  # type: ignore[arg-type]
        cod_role=cod_role,
        elemental_proxy=elemental_proxy,
        source=STATE_SOURCE,
        notes=notes,
    )


_STATES_BY_NAME = {
    "S_su": _state("S_su", "Monossacarídeos solúveis", KG_COD_M3, phase="liquid", domain="substrate", role="dynamic", cod_role="cod", elemental_proxy="C_su"),
    "S_aa": _state("S_aa", "Aminoácidos solúveis", KG_COD_M3, phase="liquid", domain="substrate", role="dynamic", cod_role="cod", elemental_proxy="C_aa"),
    "S_fa": _state("S_fa", "Ácidos graxos de cadeia longa", KG_COD_M3, phase="liquid", domain="substrate", role="dynamic", cod_role="cod", elemental_proxy="C_fa"),
    "S_va": _state("S_va", "Valerato", KG_COD_M3, phase="liquid", domain="vfa", role="dynamic", cod_role="cod", elemental_proxy="C_va"),
    "S_bu": _state("S_bu", "Butirato", KG_COD_M3, phase="liquid", domain="vfa", role="dynamic", cod_role="cod", elemental_proxy="C_bu"),
    "S_pro": _state("S_pro", "Propionato", KG_COD_M3, phase="liquid", domain="vfa", role="dynamic", cod_role="cod", elemental_proxy="C_pro"),
    "S_ac": _state("S_ac", "Acetato", KG_COD_M3, phase="liquid", domain="vfa", role="dynamic", cod_role="cod", elemental_proxy="C_ac"),
    "S_h2": _state("S_h2", "Hidrog?nio dissolvido", KG_COD_M3, phase="liquid", domain="gas_precursor", role="dynamic", cod_role="cod", elemental_proxy="0", notes="Estado din?mico can?nico do ADM1; participa da ODE e da transfer?ncia g?s-l?quido."),
    "S_ch4": _state("S_ch4", "Metano dissolvido", KG_COD_M3, phase="liquid", domain="gas_precursor", role="dynamic", cod_role="cod", elemental_proxy="C_ch4"),
    "S_IC": _state("S_IC", "Carbono inorgânico total dissolvido", KMOL_M3, phase="liquid", domain="inorganic_carbon", role="dynamic", cod_role="inorganic_carbon", elemental_proxy="1 mol C/mol"),
    "S_IN": _state("S_IN", "Nitrogênio inorgânico total dissolvido", KMOL_M3, phase="liquid", domain="nitrogen", role="dynamic", cod_role="nitrogen", elemental_proxy="1 mol N/mol"),
    "S_I": _state("S_I", "Matéria orgânica solúvel inerte", KG_COD_M3, phase="liquid", domain="inert", role="dynamic", cod_role="cod", elemental_proxy="C_sI"),
    "X_xc": _state("X_xc", "Compósito particulado", KG_COD_M3, phase="solid", domain="particulate", role="dynamic", cod_role="cod", elemental_proxy="C_xc"),
    "X_ch": _state("X_ch", "Carboidratos particulados", KG_COD_M3, phase="solid", domain="particulate", role="dynamic", cod_role="cod", elemental_proxy="C_ch"),
    "X_pr": _state("X_pr", "Proteínas particuladas", KG_COD_M3, phase="solid", domain="particulate", role="dynamic", cod_role="cod", elemental_proxy="C_pr"),
    "X_li": _state("X_li", "Lipídios particulados", KG_COD_M3, phase="solid", domain="particulate", role="dynamic", cod_role="cod", elemental_proxy="C_li"),
    "X_su": _state("X_su", "Biomassa degradadora de açúcares", KG_COD_M3, phase="solid", domain="biomass", role="dynamic", cod_role="cod", elemental_proxy="C_bac"),
    "X_aa": _state("X_aa", "Biomassa degradadora de aminoácidos", KG_COD_M3, phase="solid", domain="biomass", role="dynamic", cod_role="cod", elemental_proxy="C_bac"),
    "X_fa": _state("X_fa", "Biomassa degradadora de LCFA", KG_COD_M3, phase="solid", domain="biomass", role="dynamic", cod_role="cod", elemental_proxy="C_bac"),
    "X_c4": _state("X_c4", "Biomassa degradadora de valerato e butirato", KG_COD_M3, phase="solid", domain="biomass", role="dynamic", cod_role="cod", elemental_proxy="C_bac"),
    "X_pro": _state("X_pro", "Biomassa degradadora de propionato", KG_COD_M3, phase="solid", domain="biomass", role="dynamic", cod_role="cod", elemental_proxy="C_bac"),
    "X_ac": _state("X_ac", "Biomassa acetoclástica", KG_COD_M3, phase="solid", domain="biomass", role="dynamic", cod_role="cod", elemental_proxy="C_bac"),
    "X_h2": _state("X_h2", "Biomassa hidrogenotrófica", KG_COD_M3, phase="solid", domain="biomass", role="dynamic", cod_role="cod", elemental_proxy="C_bac"),
    "X_I": _state("X_I", "Matéria orgânica particulada inerte", KG_COD_M3, phase="solid", domain="inert", role="dynamic", cod_role="cod", elemental_proxy="C_xI"),
    "S_cation": _state("S_cation", "Cátions fortes", KMOL_M3, phase="liquid", domain="charge_balance", role="dynamic", cod_role="charge_only", elemental_proxy=None),
    "S_anion": _state("S_anion", "Ânions fortes", KMOL_M3, phase="liquid", domain="charge_balance", role="dynamic", cod_role="charge_only", elemental_proxy=None),
    "S_H_ion": _state("S_H_ion", "Íon hidrogênio", KMOL_M3, phase="liquid", domain="acid_base", role="pseudo_state", cod_role="charge_only", elemental_proxy=None, result_alias="pH", notes="Estado interno resolvido por Newton-Raphson; a interface externa reporta pH."),
    "S_va_ion": _state("S_va_ion", "Valerato ionizado", KG_COD_M3, phase="liquid", domain="acid_base", role="algebraic", cod_role="charge_only", elemental_proxy="C_va"),
    "S_bu_ion": _state("S_bu_ion", "Butirato ionizado", KG_COD_M3, phase="liquid", domain="acid_base", role="algebraic", cod_role="charge_only", elemental_proxy="C_bu"),
    "S_pro_ion": _state("S_pro_ion", "Propionato ionizado", KG_COD_M3, phase="liquid", domain="acid_base", role="algebraic", cod_role="charge_only", elemental_proxy="C_pro"),
    "S_ac_ion": _state("S_ac_ion", "Acetato ionizado", KG_COD_M3, phase="liquid", domain="acid_base", role="algebraic", cod_role="charge_only", elemental_proxy="C_ac"),
    "S_hco3_ion": _state("S_hco3_ion", "Bicarbonato", KMOL_M3, phase="liquid", domain="acid_base", role="algebraic", cod_role="inorganic_carbon", elemental_proxy="1 mol C/mol"),
    "S_co2": _state("S_co2", "CO2 dissolvido livre", KMOL_M3, phase="liquid", domain="acid_base", role="algebraic", cod_role="inorganic_carbon", elemental_proxy="1 mol C/mol"),
    "S_nh3": _state("S_nh3", "Amônia livre dissolvida", KMOL_M3, phase="liquid", domain="acid_base", role="algebraic", cod_role="nitrogen", elemental_proxy="1 mol N/mol"),
    "S_nh4_ion": _state("S_nh4_ion", "Amônio dissolvido", KMOL_M3, phase="liquid", domain="acid_base", role="algebraic", cod_role="nitrogen", elemental_proxy="1 mol N/mol"),
    "S_gas_h2": _state("S_gas_h2", "Hidrogênio no headspace", KG_COD_M3, phase="gas", domain="gas_phase", role="dynamic", cod_role="cod", elemental_proxy="0"),
    "S_gas_ch4": _state("S_gas_ch4", "Metano no headspace", KG_COD_M3, phase="gas", domain="gas_phase", role="dynamic", cod_role="cod", elemental_proxy="C_ch4"),
    "S_gas_co2": _state("S_gas_co2", "CO2 no headspace", KMOL_M3, phase="gas", domain="gas_phase", role="dynamic", cod_role="inorganic_carbon", elemental_proxy="1 mol C/mol"),
}

FULL_STATE_CATALOG = tuple(_STATES_BY_NAME[name] for name in PYADM1_STATE_ORDER)
FULL_STATE_NAMES = tuple(state.name for state in FULL_STATE_CATALOG)
FULL_STATE_INDEX = {name: index for index, name in enumerate(FULL_STATE_NAMES)}

DYNAMIC_STATE_NAMES = tuple(state.name for state in FULL_STATE_CATALOG if state.role == "dynamic")
ALGEBRAIC_STATE_NAMES = tuple(state.name for state in FULL_STATE_CATALOG if state.role == "algebraic")
PSEUDO_STATE_NAMES = tuple(state.name for state in FULL_STATE_CATALOG if state.role == "pseudo_state")
