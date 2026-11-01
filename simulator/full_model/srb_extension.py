"""E4 — Redução de Sulfato por Bactérias SRB (Sulfate-Reducing Bacteria Extension).

Adds sulfate reduction to the ADM1 framework, introducing competing pathways
where SRB compete with acetogens and methanogens for H2, acetate, propionate,
and butyrate.

States:
    S_SO4   (kmol/m³): Dissolved sulfate, limiting substrate for SRB
    S_H2S   (kmolS/m³): Total dissolved sulfide (H2S + HS⁻), produced by SRB
    S_gas_H2S (kmolS/m³): Gas-phase H2S concentration
    X_SRB_ac (kgCOD/m³): SRB acetate-oxidizers (Desulfobacter group)
    X_SRB_h2 (kgCOD/m³): SRB H2-oxidizers (Desulfovibrio group)
    X_SRB_pro (kgCOD/m³): SRB propionate-oxidizers
    X_SRB_bu (kgCOD/m³): SRB butyrate-oxidizers

Reactions:
  SRB acetate oxidation:
      CH3COO⁻ + SO4²⁻ → 2HCO3⁻ + HS⁻
      1 mol acetate (64 gCOD) reduces 1 mol SO4 (→ 1 mol S²⁻/HS⁻)
      Per kgCOD acetate: ΔS_SO4 = -(1-Y_SRB_ac)/64, ΔS_H2S = +(1-Y_SRB_ac)/64
      (units: kmol S per kgCOD acetate)

  SRB H2 oxidation:
      4H2 + SO4²⁻ + H⁺ → HS⁻ + 4H2O
      4 mol H2 (32 gCOD each = 128 gCOD total) reduces 1 mol SO4
      Per kgCOD H2: ΔS_SO4 = -(1-Y_SRB_h2)/(4×2) = -(1-Y_SRB_h2)/8
      Wait: H2 is 2 gCOD/mol (H2 + 0.5 O2), so 1 mol H2 = 2 gCOD
      4 mol H2 = 8 gCOD. Per kgCOD H2: 1000/8 = 125 mol H2 → 125/4 mol SO4 consumed
      ΔS_SO4 per kgCOD H2 = -(1-Y_SRB_h2) × (1/8) kmolS/kgCOD
      ΔS_H2S per kgCOD H2 = +(1-Y_SRB_h2) × (1/8) kmolS/kgCOD

  SRB propionate oxidation:
      CH3CH2COO⁻ + 0.75 SO4²⁻ → CH3COO⁻ + CO2 + 0.75 HS⁻
      Per kgCOD propionate: acetate yield = 64/112 = 0.5714 kgCOD/kgCOD

  SRB butyrate oxidation:
      CH3CH2CH2COO⁻ + 0.5 SO4²⁻ → 2 CH3COO⁻ + 0.5 HS⁻
      Per kgCOD butyrate: acetate yield = 2×64/160 = 0.8 kgCOD/kgCOD

H2S gas-liquid transfer (Henry's law):
    rho_transfer = k_La_H2S * (H2S_free - K_H_H2S * p_gas_H2S)
    where p_gas_H2S = S_gas_H2S * R * T (similar to CH4/CO2/H2 in core).

H2S inhibition on methanogenesis:
    H2S inhibits acetoclastic methanogenesis (rho_11), hydrogenotrophic
    methanogenesis (rho_12), propionate degradation (rho_9), and butyrate
    degradation (rho_8) via first-order linear inhibition (Fedorovich 2003, Eq. 11):
        I_H2S = max(0.0, 1.0 - H2S_free / K_I_H2S)
    This is implemented via the InhibitionHookType mechanism in kinetics.py.

Reference:
    Fedorovich, Lens & Kalyuzhnyi (2003). "Extension of Anaerobic Digestion Model
    No. 1 with processes of sulfate reduction." Applied Biochemistry and
    Biotechnology 109(1-3):33-45. doi:10.1385/ABAB:109:1-3:33
    Barrera et al. (2015). "Modeling the anaerobic digestion of cane-molasses vinasse:
    Extension of the Anaerobic Digestion Model No. 1 (ADM1) with sulfate reduction
    for a very high strength and sulfate rich wastewater." Water Research 71:42-54.
    doi:10.1016/j.watres.2014.12.026
"""
from __future__ import annotations

from typing import Mapping

import numpy as np

from simulator.full_model.acid_base import speciate_sulfide
from simulator.full_model.assembly import FullModelAssembly
from simulator.full_model.catalog_types import ParameterDefinition, ProcessDefinition, StateDefinition
from simulator.full_model.extensions import FullModelExtensionContribution
from simulator.full_model.units import DAY_INV, DIMENSIONLESS, KG_COD_M3, KMOL_S_M3

_SRC = "Fedorovich, Lens & Kalyuzhnyi (2003) doi:10.1385/ABAB:109:1-3:33; Barrera et al. (2015) doi:10.1016/j.watres.2014.12.026"
_KMOL_M3 = "kmol/m3"


class _SRBExtension:
    name = "srb"
    description = "E4: redução de sulfato por 4 grupos SRB competindo com metanogênese (Fedorovich 2003)."

    def contribute(self) -> FullModelExtensionContribution:
        states = (
            StateDefinition(
                name="S_SO4",
                description="Sulfato dissolvido (substrato limitante para SRB).",
                unit=_KMOL_M3,
                phase="liquid",
                domain="soluble",
                role="dynamic",
                cod_role="inorganic",
                elemental_proxy=None,
                source=_SRC,
                notes="Units: kmol SO4 / m³. Typically 1-20 mM in municipal wastewaters.",
            ),
            StateDefinition(
                name="S_H2S",
                description="Sulfeto dissolvido total (H2S + HS⁻), produto da redução de sulfato.",
                unit=KMOL_S_M3,
                phase="liquid",
                domain="soluble",
                role="dynamic",
                cod_role="inorganic",
                elemental_proxy=None,
                source=_SRC,
                notes="Units: kmolS/m³. Inhibitory above ~0.3 mM (free H2S). "
                      "Gas-liquid transfer via k_La_H2S and Henry's law (K_H_H2S).",
            ),
            StateDefinition(
                name="S_gas_H2S",
                description="H2S na fase gasosa.",
                unit=KMOL_S_M3,
                phase="gas",
                domain="soluble",
                role="dynamic",
                cod_role="inorganic",
                elemental_proxy=None,
                source=_SRC,
                notes="Gas-phase H2S concentration. Gas-liquid transfer via k_La_H2S and Henry's law.",
            ),
            StateDefinition(
                name="X_SRB_ac",
                description="Biomassa de SRB oxidadores de acetato (grupo Desulfobacter).",
                unit=KG_COD_M3,
                phase="solid",
                domain="active_biomass",
                role="dynamic",
                cod_role="cod",
                elemental_proxy="C_bac",
                source=_SRC,
            ),
            StateDefinition(
                name="X_SRB_h2",
                description="Biomassa de SRB oxidadores de H2 (grupo Desulfovibrio).",
                unit=KG_COD_M3,
                phase="solid",
                domain="active_biomass",
                role="dynamic",
                cod_role="cod",
                elemental_proxy="C_bac",
                source=_SRC,
            ),
            StateDefinition(
                name="X_SRB_pro",
                description="Biomassa de SRB oxidadores de propionato.",
                unit=KG_COD_M3,
                phase="solid",
                domain="active_biomass",
                role="dynamic",
                cod_role="cod",
                elemental_proxy="C_bac",
                source=_SRC,
            ),
            StateDefinition(
                name="X_SRB_bu",
                description="Biomassa de SRB oxidadores de butirato.",
                unit=KG_COD_M3,
                phase="solid",
                domain="active_biomass",
                role="dynamic",
                cod_role="cod",
                elemental_proxy="C_bac",
                source=_SRC,
            ),
        )

        processes = (
            ProcessDefinition(
                name="rho_E4_SRB_uptake_ac",
                vendor_symbol="Rho_E4_1",
                family="biochemical",
                description="Oxidação de acetato por SRB: CH3COO⁻ + SO4²⁻ → 2HCO3⁻ + HS⁻.",
                rate_expression="computed_by_extension",
                affected_states=("S_ac", "S_SO4", "S_H2S", "S_IC", "S_IN", "X_SRB_ac"),
                parameters=("k_m_SRB_ac", "K_S_SRB_ac", "K_S_SO4_ac", "Y_SRB_ac"),
                inhibitions=("I_pH_ac",),
                source=_SRC,
            ),
            ProcessDefinition(
                name="rho_E4_SRB_uptake_h2",
                vendor_symbol="Rho_E4_2",
                family="biochemical",
                description="Oxidação de H2 por SRB: 4H2 + SO4²⁻ → HS⁻ + 4H2O.",
                rate_expression="computed_by_extension",
                affected_states=("S_h2", "S_SO4", "S_H2S", "S_IC", "S_IN", "X_SRB_h2"),
                parameters=("k_m_SRB_h2", "K_S_SRB_h2", "K_S_SO4_h2", "Y_SRB_h2"),
                inhibitions=("I_pH_h2",),
                source=_SRC,
            ),
            ProcessDefinition(
                name="rho_E4_decay_X_SRB_ac",
                vendor_symbol="Rho_E4_3",
                family="biochemical",
                description="Decaimento de X_SRB_ac → X_xc.",
                rate_expression="computed_by_extension",
                affected_states=("X_xc", "X_SRB_ac", "S_IC", "S_IN"),
                parameters=("k_dec_X_SRB_ac",),
                inhibitions=(),
                source=_SRC,
            ),
            ProcessDefinition(
                name="rho_E4_decay_X_SRB_h2",
                vendor_symbol="Rho_E4_4",
                family="biochemical",
                description="Decaimento de X_SRB_h2 → X_xc.",
                rate_expression="computed_by_extension",
                affected_states=("X_xc", "X_SRB_h2", "S_IC", "S_IN"),
                parameters=("k_dec_X_SRB_h2",),
                inhibitions=(),
                source=_SRC,
            ),
            ProcessDefinition(
                name="rho_E4_SRB_uptake_pro",
                vendor_symbol="Rho_E4_5b",
                family="biochemical",
                description="Oxidação de propionato por SRB: propionate + SO4²⁻ → products.",
                rate_expression="computed_by_extension",
                affected_states=("S_pro", "S_SO4", "S_H2S", "S_ac", "S_IC", "S_IN", "X_SRB_pro"),
                parameters=("k_m_SRB_pro", "K_S_SRB_pro", "K_S_SO4_pro", "Y_SRB_pro"),
                inhibitions=("I_pH_aa",),
                source=_SRC,
            ),
            ProcessDefinition(
                name="rho_E4_SRB_uptake_bu",
                vendor_symbol="Rho_E4_6b",
                family="biochemical",
                description="Oxidação de butirato por SRB: butyrate + SO4²⁻ → products.",
                rate_expression="computed_by_extension",
                affected_states=("S_bu", "S_SO4", "S_H2S", "S_ac", "S_IC", "S_IN", "X_SRB_bu"),
                parameters=("k_m_SRB_bu", "K_S_SRB_bu", "K_S_SO4_bu", "Y_SRB_bu"),
                inhibitions=("I_pH_aa",),
                source=_SRC,
            ),
            ProcessDefinition(
                name="rho_E4_decay_X_SRB_pro",
                vendor_symbol="Rho_E4_7b",
                family="biochemical",
                description="Decaimento de X_SRB_pro → X_xc.",
                rate_expression="computed_by_extension",
                affected_states=("X_xc", "X_SRB_pro", "S_IC", "S_IN"),
                parameters=("k_dec_X_SRB_pro",),
                inhibitions=(),
                source=_SRC,
            ),
            ProcessDefinition(
                name="rho_E4_decay_X_SRB_bu",
                vendor_symbol="Rho_E4_8b",
                family="biochemical",
                description="Decaimento de X_SRB_bu → X_xc.",
                rate_expression="computed_by_extension",
                affected_states=("X_xc", "X_SRB_bu", "S_IC", "S_IN"),
                parameters=("k_dec_X_SRB_bu",),
                inhibitions=(),
                source=_SRC,
            ),
            ProcessDefinition(
                name="rho_E4_H2S_transfer",
                vendor_symbol="Rho_E4_gas",
                family="biochemical",
                description="Transferência gás-líquido de H2S via Lei de Henry.",
                rate_expression="computed_by_extension",
                affected_states=("S_H2S", "S_gas_H2S"),
                parameters=("k_La_H2S", "K_H_H2S"),
                inhibitions=(),
                source=_SRC,
                notes="Barrera et al. (2015), Tables 2–3: rho = k_La_H2S * (H2S_free - K_H_H2S * p_H2S).",
            ),
        )

        parameters = (
            ParameterDefinition(
                name="k_m_SRB_ac",
                value=7.1,
                unit=DAY_INV,
                group="biochemical",
                classification="calibrated",
                description="Taxa máxima de consumo de acetato por X_SRB_ac.",
                source=_SRC,
                notes="Fedorovich 2003 Table 2: µ_max = 7.1 d⁻¹ para SRB acetato-oxidadoras.",
            ),
            ParameterDefinition(
                name="K_S_SRB_ac",
                value=0.22,
                unit=KG_COD_M3,
                group="biochemical",
                classification="calibrated",
                description="Meia-saturação para acetato (X_SRB_ac).",
                source=_SRC,
                notes="Fedorovich 2003 Table 2: K_S_ac = 0.22 kgCOD/m³.",
            ),
            ParameterDefinition(
                name="K_S_SO4_ac",
                value=1.0e-4,
                unit=_KMOL_M3,
                group="biochemical",
                classification="calibrated",
                description="Meia-saturação para sulfato na oxidação de acetato (kmol/m³).",
                source=_SRC,
                notes="Fedorovich 2003 Table 2: K_S_SO4 = 0.1 mmol/L = 1.0e-4 kmol/m³. "
                      "Very low — SRB efficiently scavenge sulfate even at trace concentrations.",
            ),
            ParameterDefinition(
                name="Y_SRB_ac",
                value=0.0342,
                unit=DIMENSIONLESS,
                group="stoichiometric",
                classification="calibrated",
                description="Rendimento de biomassa de SRB_ac (gCOD_X / gCOD_ac).",
                source=_SRC,
                notes="Fedorovich 2003 Table 2: Y_SRB_ac = 0.0342 kgCOD/kgCOD. "
                      "Lower than acetogens due to less Gibbs energy per mol SO4 reduced.",
            ),
            ParameterDefinition(
                name="k_m_SRB_h2",
                value=26.7,
                unit=DAY_INV,
                group="biochemical",
                classification="calibrated",
                description="Taxa máxima de consumo de H2 por X_SRB_h2.",
                source=_SRC,
                notes="Fedorovich 2003 Table 3: µ_max = 26.7 d⁻¹ para SRB H2-oxidadoras.",
            ),
            ParameterDefinition(
                name="K_S_SRB_h2",
                value=1e-4,
                unit=KG_COD_M3,
                group="biochemical",
                classification="calibrated",
                description="Meia-saturação para H2 em SRB_h2 (kgCOD/m³).",
                source=_SRC,
                notes="Fedorovich 2003 Table 3: K_S_H2 = 1e-4 kgCOD/m³ ≈ 6.25 µM H2. "
                      "Similar to hydrogenotrophic methanogens (competitive threshold).",
            ),
            ParameterDefinition(
                name="K_S_SO4_h2",
                value=1.04e-4,
                unit=_KMOL_M3,
                group="biochemical",
                classification="calibrated",
                description="Meia-saturação para sulfato na oxidação de H2 (kmol/m³).",
                source=_SRC,
                notes="Fedorovich 2003 Table 3: K_S_SO4 ≈ 0.104 mmol/L = 1.04e-4 kmol/m³.",
            ),
            ParameterDefinition(
                name="Y_SRB_h2",
                value=0.0366,
                unit=DIMENSIONLESS,
                group="stoichiometric",
                classification="calibrated",
                description="Rendimento de biomassa de SRB_h2 (gCOD_X / gCOD_H2).",
                source=_SRC,
                notes="Fedorovich 2003 Table 3: Y_SRB_h2 = 0.0366 kgCOD/kgCOD.",
            ),
            ParameterDefinition(
                name="k_dec_X_SRB_ac",
                value=0.015,
                unit=DAY_INV,
                group="biochemical",
                classification="calibrated",
                description="Taxa de decaimento de X_SRB_ac.",
                source=_SRC,
                notes="Fedorovich 2003 Table 2: b_dec = 0.015 d⁻¹ para SRB acetato-oxidadoras.",
            ),
            ParameterDefinition(
                name="k_dec_X_SRB_h2",
                value=0.01,
                unit=DAY_INV,
                group="biochemical",
                classification="calibrated",
                description="Taxa de decaimento de X_SRB_h2.",
                source=_SRC,
                notes="Fedorovich 2003 Table 3: b_dec = 0.01 d⁻¹ para SRB H2-oxidadoras.",
            ),
            ParameterDefinition(
                name="K_I_H2S",
                value=6.72e-3,
                unit=KMOL_S_M3,
                group="biochemical",
                classification="calibrated",
                description="Constante de inibição de H2S sobre metanogênese (kmolS/m³).",
                source=_SRC,
                notes="Fedorovich 2003: mean of reactor X3 (7.19e-3 mol/L) and X4 (6.25e-3 mol/L) "
                      "= 6.72e-3 kmolS/m³ ≈ 0.22 g S/L. Applied to rho_11 and rho_12 via "
                      "InhibitionHookType in kinetics.py.",
            ),
            ParameterDefinition(
                name="k_La_H2S",
                value=200.0,
                unit=DAY_INV,
                group="physicochemical",
                classification="calibrated",
                description="Coeficiente volumétrico de transferência de massa para H2S (d⁻¹).",
                source=_SRC,
                notes="Same order of magnitude as k_La for CO2/CH4/H2 in ADM1 (200 d⁻¹). "
                      "Represents gas-liquid mass transfer coefficient consistent with Henry's law formulation.",
            ),
            ParameterDefinition(
                name="K_H_H2S",
                value=0.099,
                unit="kmol/m3/bar",
                group="physicochemical",
                classification="calibrated",
                description="Constante de Henry para H2S (kmol/m³/bar a 35°C).",
                source=_SRC,
                notes="Sander 2015 compilation. H2S is much more soluble than CH4 or CO2.",
            ),
            # Propionate SRB parameters
            ParameterDefinition(
                name="k_m_SRB_pro",
                value=12.6,
                unit=DAY_INV,
                group="biochemical",
                classification="calibrated",
                description="Taxa máxima de consumo de propionato por X_SRB_pro.",
                source=_SRC,
                notes="Fedorovich et al. (2003), Table 2: literature value.",
            ),
            ParameterDefinition(
                name="K_S_SRB_pro",
                value=0.11,
                unit=KG_COD_M3,
                group="biochemical",
                classification="calibrated",
                description="Meia-saturação para propionato (X_SRB_pro).",
                source=_SRC,
                notes="Fedorovich et al. (2003), Table 2: literature value.",
            ),
            ParameterDefinition(
                name="K_S_SO4_pro",
                value=2.0e-4,
                unit=_KMOL_M3,
                group="biochemical",
                classification="calibrated",
                description="Meia-saturação para sulfato na oxidação de propionato.",
                source=_SRC,
                notes="Fedorovich et al. (2003), Table 2: literature value.",
            ),
            ParameterDefinition(
                name="Y_SRB_pro",
                value=0.0329,
                unit=DIMENSIONLESS,
                group="stoichiometric",
                classification="calibrated",
                description="Rendimento de biomassa de SRB_pro.",
                source=_SRC,
                notes="Fedorovich et al. (2003), Table 2: literature value.",
            ),
            ParameterDefinition(
                name="k_dec_X_SRB_pro",
                value=0.01,
                unit=DAY_INV,
                group="biochemical",
                classification="calibrated",
                description="Taxa de decaimento de X_SRB_pro.",
                source=_SRC,
                notes="Fedorovich et al. (2003), Table 2: literature value.",
            ),
            # Butyrate SRB parameters
            ParameterDefinition(
                name="k_m_SRB_bu",
                value=13.7,
                unit=DAY_INV,
                group="biochemical",
                classification="calibrated",
                description="Taxa máxima de consumo de butirato por X_SRB_bu.",
                source=_SRC,
                notes="Fedorovich et al. (2003), Table 2: literature value.",
            ),
            ParameterDefinition(
                name="K_S_SRB_bu",
                value=0.10,
                unit=KG_COD_M3,
                group="biochemical",
                classification="calibrated",
                description="Meia-saturação para butirato (X_SRB_bu).",
                source=_SRC,
                notes="Fedorovich et al. (2003), Table 2: literature value.",
            ),
            ParameterDefinition(
                name="K_S_SO4_bu",
                value=2.1e-4,
                unit=_KMOL_M3,
                group="biochemical",
                classification="calibrated",
                description="Meia-saturação para sulfato na oxidação de butirato.",
                source=_SRC,
                notes="Fedorovich et al. (2003), Table 2: literature value.",
            ),
            ParameterDefinition(
                name="Y_SRB_bu",
                value=0.0329,
                unit=DIMENSIONLESS,
                group="stoichiometric",
                classification="calibrated",
                description="Rendimento de biomassa de SRB_bu.",
                source=_SRC,
                notes="Fedorovich et al. (2003), Table 2: literature value.",
            ),
            ParameterDefinition(
                name="k_dec_X_SRB_bu",
                value=0.01,
                unit=DAY_INV,
                group="biochemical",
                classification="calibrated",
                description="Taxa de decaimento de X_SRB_bu.",
                source=_SRC,
                notes="Fedorovich et al. (2003), Table 2: literature value.",
            ),
        )

        # Stoichiometry notes:
        #   S_SO4 and S_H2S are in kmol/m³, not kgCOD/m³.
        #   Stoichiometric coefficients must be consistent with the ODE units.
        #
        #   For SRB_ac (acetate oxidation):
        #     1 kgCOD acetate = 1000/64 = 15.625 mol acetate
        #     Catabolized fraction = (1 - Y_SRB_ac) kgCOD
        #     SO4 consumed = (1-Y) * 15.625 * 1 mol SO4/mol acetate / 1000 kmol = (1-Y)/64 kmol
        #     HS⁻ produced = same: (1-Y)/64 kmol (S balance)
        #   S_IC = C_ac - Y*C_bac (from acetate to bicarbonate)
        #
        #   For SRB_h2 (H2 oxidation):
        #     1 mol H2: H2 + 0.5 O2 → H2O; gCOD/mol = 0.5 * 32 = 16 gO2/mol H2
        #     So 1 kgCOD H2 = 1000/16 = 62.5 mol H2
        #     4H2 reduces 1 mol SO4 → 62.5/4 = 15.625 mol SO4/kgCOD H2 catabolized
        #     ΔS_SO4 = -(1-Y_SRB_h2) * 15.625 / 1000 = -(1-Y_SRB_h2) / 64  kmol/kgCOD
        #   S_IC = 0 for H2 (no C in H2); but S_IN = -Y*N_bac (biomass needs N)
        #
        #   For SRB_pro (propionate oxidation):
        #     CH3CH2COO⁻ + 0.75 SO4²⁻ → CH3COO⁻ + CO2 + 0.75 HS⁻
        #     Acetate yield = 64/112 = 0.5714 kgCOD_ac / kgCOD_pro
        #
        #   For SRB_bu (butyrate oxidation):
        #     CH3CH2CH2COO⁻ + 0.5 SO4²⁻ → 2 CH3COO⁻ + 0.5 HS⁻
        #     Acetate yield = 2*64/160 = 0.8 kgCOD_ac / kgCOD_bu
        #
        # H2S_transfer: gas-liquid via Henry's law
        biochemical_stoichiometry_rows = {
            "rho_E4_SRB_uptake_ac": {
                "S_ac": "-1",
                "S_SO4": "-(1.0 - Y_SRB_ac) / 64.0",
                "S_H2S": "(1.0 - Y_SRB_ac) / 64.0",
                "S_IC": "C_ac - Y_SRB_ac * C_bac",
                "S_IN": "-Y_SRB_ac * N_bac",
                "X_SRB_ac": "Y_SRB_ac",
            },
            "rho_E4_SRB_uptake_h2": {
                "S_h2": "-1",
                "S_SO4": "-(1.0 - Y_SRB_h2) / 64.0",
                "S_H2S": "(1.0 - Y_SRB_h2) / 64.0",
                "S_IC": "-Y_SRB_h2 * C_bac",
                "S_IN": "-Y_SRB_h2 * N_bac",
                "X_SRB_h2": "Y_SRB_h2",
            },
            "rho_E4_decay_X_SRB_ac": {
                "X_xc": "1",
                "X_SRB_ac": "-1",
                "S_IC": "-s_13",
                "S_IN": "N_bac - N_xc",
            },
            "rho_E4_decay_X_SRB_h2": {
                "X_xc": "1",
                "X_SRB_h2": "-1",
                "S_IC": "-s_13",
                "S_IN": "N_bac - N_xc",
            },
            "rho_E4_SRB_uptake_pro": {
                "S_pro": "-1",
                "S_ac": "(1.0 - Y_SRB_pro) * (4.0 / 7.0)",
                "S_SO4": "-(1.0 - Y_SRB_pro) * 0.75 / 112.0",
                "S_H2S": "(1.0 - Y_SRB_pro) * 0.75 / 112.0",
                "S_IC": "C_pro - (1.0 - Y_SRB_pro) * (4.0 / 7.0) * C_ac - Y_SRB_pro * C_bac",
                "S_IN": "-Y_SRB_pro * N_bac",
                "X_SRB_pro": "Y_SRB_pro",
            },
            "rho_E4_SRB_uptake_bu": {
                "S_bu": "-1",
                "S_ac": "(1.0 - Y_SRB_bu) * 0.8",
                "S_SO4": "-(1.0 - Y_SRB_bu) * 0.5 / 160.0",
                "S_H2S": "(1.0 - Y_SRB_bu) * 0.5 / 160.0",
                "S_IC": "C_bu - (1.0 - Y_SRB_bu) * 0.8 * C_ac - Y_SRB_bu * C_bac",
                "S_IN": "-Y_SRB_bu * N_bac",
                "X_SRB_bu": "Y_SRB_bu",
            },
            "rho_E4_decay_X_SRB_pro": {
                "X_xc": "1",
                "X_SRB_pro": "-1",
                "S_IC": "-s_13",
                "S_IN": "N_bac - N_xc",
            },
            "rho_E4_decay_X_SRB_bu": {
                "X_xc": "1",
                "X_SRB_bu": "-1",
                "S_IC": "-s_13",
                "S_IN": "N_bac - N_xc",
            },
            "rho_E4_H2S_transfer": {
                "S_H2S": "-1",
                "S_gas_H2S": "V_liq / V_gas",
            },
        }

        return FullModelExtensionContribution(
            states=states,
            processes=processes,
            parameters=parameters,
            biochemical_stoichiometry_rows=biochemical_stoichiometry_rows,
            rate_function=self._rates,
            diagnostics_hook=self._diagnostics,
            inhibition_hook=self._inhibition,
        )

    def _rates(self, state: Mapping[str, float], params: Mapping[str, float]) -> dict[str, float]:
        s_ac = max(float(state.get("S_ac", 0.0)), 0.0)
        s_h2 = max(float(state.get("S_h2", 0.0)), 1e-12)
        s_pro = max(float(state.get("S_pro", 0.0)), 0.0)
        s_bu = max(float(state.get("S_bu", 0.0)), 0.0)
        s_so4 = max(float(state.get("S_SO4", 0.0)), 0.0)
        s_h2s = max(float(state.get("S_H2S", 0.0)), 0.0)
        s_gas_h2s = max(float(state.get("S_gas_H2S", 0.0)), 0.0)
        x_srb_ac = max(float(state.get("X_SRB_ac", 0.0)), 0.0)
        x_srb_h2 = max(float(state.get("X_SRB_h2", 0.0)), 0.0)
        x_srb_pro = max(float(state.get("X_SRB_pro", 0.0)), 0.0)
        x_srb_bu = max(float(state.get("X_SRB_bu", 0.0)), 0.0)
        s_h_ion = max(float(state.get("S_H_ion", 1e-7)), 1e-14)
        s_h2s_free, _ = speciate_sulfide(s_h2s, s_h_ion)
        s_in = max(float(state.get("S_IN", 0.0)), 0.0)

        # pH inhibitions
        i_ph_ac = (params["K_pH_ac"] ** params["n_ac"]) / (s_h_ion ** params["n_ac"] + params["K_pH_ac"] ** params["n_ac"])
        i_ph_h2 = (params["K_pH_h2"] ** params["n_h2"]) / (s_h_ion ** params["n_h2"] + params["K_pH_h2"] ** params["n_h2"])
        i_ph_aa = (params["K_pH_aa"] ** params["nn_aa"]) / (s_h_ion ** params["nn_aa"] + params["K_pH_aa"] ** params["nn_aa"])
        i_in_lim = s_in / (float(params["K_S_IN"]) + s_in)

        # Sulfate limitation (dual Monod: substrate × SO4)
        k_so4_ac = float(params["K_S_SO4_ac"])
        k_so4_h2 = float(params["K_S_SO4_h2"])
        k_so4_pro = float(params["K_S_SO4_pro"])
        k_so4_bu = float(params["K_S_SO4_bu"])
        i_so4_ac = s_so4 / (k_so4_ac + s_so4)
        i_so4_h2 = s_so4 / (k_so4_h2 + s_so4)
        i_so4_pro = s_so4 / (k_so4_pro + s_so4)
        i_so4_bu = s_so4 / (k_so4_bu + s_so4)

        # Free H2S: Barrera et al. (2015), §2.1; linear law: Fedorovich (2003), Eq. 11.
        k_i_h2s = float(params.get("K_I_H2S", 6.72e-3))
        i_h2s = max(0.0, 1.0 - s_h2s_free / k_i_h2s)

        rho_srb_ac = (
            float(params["k_m_SRB_ac"])
            * s_ac / (float(params["K_S_SRB_ac"]) + s_ac)
            * i_so4_ac
            * x_srb_ac
            * i_ph_ac
            * i_in_lim
            * i_h2s
        )
        rho_srb_h2 = (
            float(params["k_m_SRB_h2"])
            * s_h2 / (float(params["K_S_SRB_h2"]) + s_h2)
            * i_so4_h2
            * x_srb_h2
            * i_ph_h2
            * i_in_lim
            * i_h2s
        )
        rho_srb_pro = (
            float(params["k_m_SRB_pro"])
            * s_pro / (float(params["K_S_SRB_pro"]) + s_pro)
            * i_so4_pro
            * x_srb_pro
            * i_ph_aa
            * i_in_lim
            * i_h2s
        )
        rho_srb_bu = (
            float(params["k_m_SRB_bu"])
            * s_bu / (float(params["K_S_SRB_bu"]) + s_bu)
            * i_so4_bu
            * x_srb_bu
            * i_ph_aa
            * i_in_lim
            * i_h2s
        )
        rho_dec_srb_ac = float(params["k_dec_X_SRB_ac"]) * x_srb_ac
        rho_dec_srb_h2 = float(params["k_dec_X_SRB_h2"]) * x_srb_h2
        rho_dec_srb_pro = float(params["k_dec_X_SRB_pro"]) * x_srb_pro
        rho_dec_srb_bu = float(params["k_dec_X_SRB_bu"]) * x_srb_bu

        # Gas-liquid H2S transfer via Henry's law
        # p_gas_H2S = S_gas_H2S * R * T (simplified; consistent with core gas transfer)
        r_gas = float(params.get("R", 8.314e-2))  # bar·L/(mol·K) = 8.314e-2 bar·m³/(kmol·K)
        t_op = float(params.get("T_op", 308.15))
        p_gas_h2s = s_gas_h2s * r_gas * t_op
        k_h_h2s = float(params.get("K_H_H2S", 0.099))
        rho_transfer = float(params["k_La_H2S"]) * (s_h2s_free - k_h_h2s * p_gas_h2s)

        return {
            "rho_E4_SRB_uptake_ac": rho_srb_ac,
            "rho_E4_SRB_uptake_h2": rho_srb_h2,
            "rho_E4_decay_X_SRB_ac": rho_dec_srb_ac,
            "rho_E4_decay_X_SRB_h2": rho_dec_srb_h2,
            "rho_E4_SRB_uptake_pro": rho_srb_pro,
            "rho_E4_SRB_uptake_bu": rho_srb_bu,
            "rho_E4_decay_X_SRB_pro": rho_dec_srb_pro,
            "rho_E4_decay_X_SRB_bu": rho_dec_srb_bu,
            "rho_E4_H2S_transfer": rho_transfer,
        }

    def _inhibition(self, state: Mapping[str, float], params: Mapping[str, float]) -> dict[str, float]:
        """H2S first-order linear inhibition on methanogenesis and VFA degradation.

        Fedorovich 2003 (ABB 109:33-45) Eq. 11 — first-order inhibition kinetics:
            I_H2S = max(0.0, 1.0 - H2S_free / K_I_H2S)
        Free H2S follows Barrera et al. (2015), Tables 2–3.
        When H2S_free >= K_I_H2S, complete inhibition (I_H2S = 0).
        Applied to rho_11 (acetate → CH4), rho_12 (H2 → CH4),
        rho_8/rho_9 (valerate/butyrate) and rho_10 (propionate) degradation.
        """
        s_h2s = max(float(state.get("S_H2S", 0.0)), 0.0)
        s_h_ion = max(float(state.get("S_H_ion", 1e-7)), 1e-14)
        s_h2s_free, _ = speciate_sulfide(s_h2s, s_h_ion)
        k_i_h2s = float(params.get("K_I_H2S", 6.72e-3))
        i_h2s = max(0.0, 1.0 - s_h2s_free / k_i_h2s)
        return {
            "rho_11_uptake_acetate": i_h2s,
            "rho_12_uptake_hydrogen": i_h2s,
            "rho_8_uptake_valerate": i_h2s,
            "rho_9_uptake_butyrate": i_h2s,
            "rho_10_uptake_propionate": i_h2s,
        }

    def _diagnostics(
        self, matrix: np.ndarray, assembly: FullModelAssembly, params: Mapping[str, float]
    ) -> dict[str, list[float]]:
        s_so4 = np.clip(matrix[:, assembly.full_state_index["S_SO4"]], 0.0, None)
        s_h2s = np.clip(matrix[:, assembly.full_state_index["S_H2S"]], 0.0, None)
        s_gas_h2s = np.clip(matrix[:, assembly.full_state_index["S_gas_H2S"]], 0.0, None)
        x_srb_ac = np.clip(matrix[:, assembly.full_state_index["X_SRB_ac"]], 0.0, None)
        x_srb_h2 = np.clip(matrix[:, assembly.full_state_index["X_SRB_h2"]], 0.0, None)
        x_srb_pro = np.clip(matrix[:, assembly.full_state_index["X_SRB_pro"]], 0.0, None)
        x_srb_bu = np.clip(matrix[:, assembly.full_state_index["X_SRB_bu"]], 0.0, None)
        return {
            "S_SO4": s_so4.astype(float).tolist(),
            "S_H2S": s_h2s.astype(float).tolist(),
            "S_gas_H2S": s_gas_h2s.astype(float).tolist(),
            "X_SRB_ac": x_srb_ac.astype(float).tolist(),
            "X_SRB_h2": x_srb_h2.astype(float).tolist(),
            "X_SRB_pro": x_srb_pro.astype(float).tolist(),
            "X_SRB_bu": x_srb_bu.astype(float).tolist(),
        }


SRB_EXTENSION = _SRBExtension()
