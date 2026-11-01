"""E15 — Biometanação de Syngas (Syngas Biomethanation Extension).

Adds CO as an explicit substrate for anaerobic digestion, enabling simulation of
syngas (CO + H2 + CO2) biomethanation. CO dissolves from the gas phase, is
consumed by specialized CO-utilizing microorganisms (X_met_CO) via an enzymatic
water-gas shift reaction (CO + H2O → CO2 + H2), and the produced H2 is then
consumed by existing hydrogenotrophic methanogens.

Architecture:
  - S_CO   (liquid, kgCOD/m³): dissolved CO
  - S_gas_CO (gas, kgCOD/m³):  CO in the headspace
  - X_met_CO (liquid, kgCOD/m³): CO-utilizing homoacetogens/Carboxydotrophic methanogens

CO uptake pathway (dominant, per the reference paper):
    CO + H2O  →  CO2 + H2   (enzymatic WGS, catalyzed by CO dehydrogenase)
    4H2 + CO2 →  CH4 + 2H2O (hydrogenotrophic methanogenesis — existing ADM1 rho_12)
Net: 4CO + 2H2O → CH4 + 3CO2

Stoichiometry (per kgCOD S_CO consumed):
  S_CO:   -1
  S_h2:   +(1 - Y_met_CO)   [H2 produced from WGS, COD-balanced since COD(CO) = COD(H2) = 16 gO2/mol]
  S_IC:   +C_CO - Y_met_CO*C_bac  [C from CO → CO2 minus C to biomass]
  S_IN:   -Y_met_CO * N_bac
  X_met_CO: +Y_met_CO

  where C_CO = 0.0625 kmolC/kgCOD (1 mol C per 16 gCOD CO)

Gas-liquid CO transfer (Henry's law, analogous to H2):
  rho_transfer = k_La_CO * (S_CO - 16 * K_H_CO * p_gas_CO)
  p_gas_CO = S_gas_CO * R * T / 16  [bar; identical denominator to H2 since both have 16 gCOD/mol]

Note on gas dynamics:
  rhs.py applies venting -(q_gas/V_gas)*S_gas_CO for all extension gas states automatically
  (see FullCSTRRhs.__call__). The stoichiometry coefficient V_liq/V_gas for S_gas_CO converts
  the liquid-basis transfer rate to a gas-volume basis.

CO inhibition of acetoclastic and hydrogenotrophic methanogenesis:
  Sun et al. (2021) define:
    Icoac = 1 / (1 + S_CO / KI,COac)
    IcoH2 = 1 / (1 + S_CO / KI,COH2)
  which are implemented here as competitive inhibition factors on rho_11 and rho_12.

Domain note:
  Default parameters are derived for mesophilic (35°C) CSTR biomethanation.
  Thermophilic conditions increase CO transfer rates but also shift community
  composition. At elevated CO partial pressures the inhibition terms on acetate and
  hydrogen uptake become relevant. Use X_met_CO initial inoculum > 0.01
  kgCOD/m³ or the simulation will not show CO consumption.

Reference:
    Sun H, Yang Z, Zhao Q, Kurbonova M, Zhang R, Liu G, Wang W (2021).
    Modification and extension of anaerobic digestion model No.1 (ADM1)
    for syngas biomethanation simulation: From lab-scale to pilot-scale.
    Chemical Engineering Journal 403:126177. doi:10.1016/j.cej.2020.126177

    The local paper calibrates YCO, kmCO, KsCO and kdecCO (Table 4),
    formulates Icoac/IcoH2 for acetoclastic and hydrogenotrophic uptake
    (Eq. 14-15), and reports acetate-dominant lab-scale versus
    hydrogenotrophic-dominant pilot-scale pathways.
"""
from __future__ import annotations

from typing import Mapping

import numpy as np

from simulator.full_model.assembly import FullModelAssembly
from simulator.full_model.catalog_types import ParameterDefinition, ProcessDefinition, StateDefinition
from simulator.full_model.extensions import FullModelExtensionContribution
from simulator.full_model.units import DAY_INV, DIMENSIONLESS, KG_COD_M3, KMOL_C_PER_KG_COD

_SRC = (
    "Sun et al. (2021) Chem Eng J 403:126177 doi:10.1016/j.cej.2020.126177; "
    "Batstone et al. (2002) Water Sci Technol 45(10):65-73"
)
_KMOL_M3 = "kmol/m3"


class _SyngasExtension:
    name = "syngas"
    description = (
        "E15: biometanação de syngas com CO→H2 e CO→acetato, transporte gás-líquido e "
        "inibição de CO em acetogênese/metanogênese conforme Sun et al. (2021)."
    )

    def contribute(self) -> FullModelExtensionContribution:
        states = (
            StateDefinition(
                name="S_CO",
                description="CO dissolvido (substrato para X_met_CO via WGS enzimática).",
                unit=KG_COD_M3,
                phase="liquid",
                domain="soluble",
                role="dynamic",
                cod_role="cod",
                elemental_proxy="C_CO",
                source=_SRC,
                notes=(
                    "kgCOD/m³. 1 mol CO = 28 g, COD = 16 gO2/mol (same as H2). "
                    "Typical dissolved CO: 0.0001–0.002 kgCOD/m³ at biomethanation conditions. "
                    "Gas-liquid transfer driven by Henry's law (K_H_CO ≈ 8e-4 kmol/m³/bar at 35°C)."
                ),
            ),
            StateDefinition(
                name="S_gas_CO",
                description="CO na fase gasosa (headspace/syngas bubble).",
                unit=KG_COD_M3,
                phase="gas",
                domain="soluble",
                role="dynamic",
                cod_role="cod",
                elemental_proxy="C_CO",
                source=_SRC,
                notes=(
                    "kgCOD/m³_gas. Drives dissolution into S_CO. "
                    "p_gas_CO = S_gas_CO * R * T / 16 [bar]. "
                    "Venting applied by rhs.py (q_gas/V_gas * S_gas_CO). "
                    "Typical syngas: 20–30% CO v/v."
                ),
            ),
            StateDefinition(
                name="X_met_CO",
                description="Biomassa de micro-organismos carbóxidotróficos (utilizam CO via WGS).",
                unit=KG_COD_M3,
                phase="solid",
                domain="active_biomass",
                role="dynamic",
                cod_role="cod",
                elemental_proxy="C_bac",
                source=_SRC,
                notes=(
                    "CO-utilizing anaerobes (Carboxydothermus hydrogenoformans-like). "
                    "Require inoculum ≥ 0.01 kgCOD/m³. Decay → X_xc."
                ),
            ),
        )

        processes = (
            ProcessDefinition(
                name="rho_E15_CO_uptake",
                vendor_symbol="Rho_E15_1",
                family="biochemical",
                description=(
                    "Oxidação biológica de CO via WGS enzimática: CO + H2O → CO2 + H2 (+ biomassa). "
                    "Fração f_co_to_h2 do consumo total de CO."
                ),
                rate_expression="computed_by_extension",
                affected_states=("S_CO", "S_h2", "S_IC", "S_IN", "X_met_CO"),
                parameters=("k_m_met_CO", "K_S_CO", "Y_met_CO", "f_co_to_h2"),
                inhibitions=("I_pH_h2",),
                source=_SRC,
                notes=(
                    "Rate = total_CO_rate × f_co_to_h2. "
                    "Product H2 enters ADM1 pool and is consumed by X_h2 (rho_12). "
                    "Net: CO → H2 (WGS pathway, fraction f_co_to_h2)."
                ),
            ),
            ProcessDefinition(
                name="rho_E15_CO_acetate",
                vendor_symbol="Rho_E15_ac",
                family="biochemical",
                description=(
                    "Homoacetogênese de CO: 4CO + 2H2O → CH3COO⁻ + H⁺ + 2CO2 (+ biomassa). "
                    "Fração (1 - f_co_to_h2) do consumo total de CO."
                ),
                rate_expression="computed_by_extension",
                affected_states=("S_CO", "S_ac", "S_IC", "S_IN", "X_met_CO"),
                parameters=("k_m_met_CO", "K_S_CO", "Y_met_CO", "f_co_to_h2"),
                inhibitions=("I_pH_h2",),
                source=_SRC,
                notes=(
                    "Wood-Ljungdahl pathway: CO carbon split ~50% to acetate, ~50% to CO2. "
                    "Rate = total_CO_rate × (1 - f_co_to_h2). "
                    "Both rho_E15_CO_uptake and rho_E15_CO_acetate use the same X_met_CO population. "
                    "Per kgCOD CO (catabolism): S_ac += (1-Y); S_IC += C_CO - (1-Y)*C_ac - Y*C_bac."
                ),
            ),
            ProcessDefinition(
                name="rho_E15_decay_X_met_CO",
                vendor_symbol="Rho_E15_2",
                family="biochemical",
                description="Decaimento de X_met_CO → X_xc.",
                rate_expression="computed_by_extension",
                affected_states=("X_xc", "X_met_CO", "S_IC", "S_IN"),
                parameters=("k_dec_X_met_CO",),
                inhibitions=(),
                source=_SRC,
            ),
            ProcessDefinition(
                name="rho_E15_CO_transfer",
                vendor_symbol="Rho_E15_gas",
                family="biochemical",
                description="Transferência gás-líquido de CO (dissolução do syngas): S_gas_CO ↔ S_CO.",
                rate_expression="computed_by_extension",
                affected_states=("S_CO", "S_gas_CO"),
                parameters=("k_La_CO", "K_H_CO"),
                inhibitions=(),
                source=_SRC,
                notes="rho > 0 = net flux from liquid to gas (degassing). rho < 0 = dissolution.",
            ),
        )

        parameters = (
            ParameterDefinition(
                name="C_CO",
                value=1.0 / 16.0,
                unit=KMOL_C_PER_KG_COD,
                group="stoichiometric",
                classification="canonical",
                description="Carbono do CO: 1 mol C por 16 gDQO (Sun et al. 2021).",
                source=_SRC,
            ),
            ParameterDefinition(
                name="k_m_met_CO",
                value=75.0,
                unit=DAY_INV,
                group="biochemical",
                classification="calibrated",
                description="Taxa máxima específica de consumo de CO por X_met_CO (d⁻¹).",
                source=_SRC,
                notes=(
                    "Table 4 do paper-base: kmCO = 75 COD/(COD·d) para o ADM1_modified calibrado em lab-scale. "
                    "Mantido como default quando E15 está ativo."
                ),
            ),
            ParameterDefinition(
                name="K_S_CO",
                value=8.0e-6,
                unit=KG_COD_M3,
                group="biochemical",
                classification="calibrated",
                description="Constante de meia-saturação para CO dissolvido (kgCOD/m³).",
                source=_SRC,
                notes=(
                    "Table 4 do paper-base: KsCO = 8e-6 kgCOD/m³ para o ADM1_modified. "
                    "Valor muito baixo, consistente com alta afinidade aparente após calibração lab-scale."
                ),
            ),
            ParameterDefinition(
                name="Y_met_CO",
                value=0.025,
                unit=DIMENSIONLESS,
                group="stoichiometric",
                classification="calibrated",
                description="Rendimento de biomassa de X_met_CO (kgCOD_X / kgCOD_CO).",
                source=_SRC,
                notes=(
                    "Table 4 do paper-base: YCO = 0.025 COD/COD para a biomassa XCO. "
                    "Usado aqui como rendimento default de X_met_CO."
                ),
            ),
            ParameterDefinition(
                name="k_dec_X_met_CO",
                value=0.02,
                unit=DAY_INV,
                group="biochemical",
                classification="calibrated",
                description="Taxa de decaimento de X_met_CO (d⁻¹).",
                source=_SRC,
                notes="Table 4 do paper-base: kdecCO = 0.02 d⁻¹.",
            ),
            ParameterDefinition(
                name="k_m_ac",
                value=12.5,
                unit=DAY_INV,
                group="biochemical",
                classification="calibrated",
                description="Taxa máxima específica de acetoclásticos quando E15 está ativo.",
                source=_SRC,
                notes="Table 4 do paper-base: kmac = 12.5 COD/(COD·d) no ADM1_modified.",
            ),
            ParameterDefinition(
                name="k_m_h2",
                value=90.0,
                unit=DAY_INV,
                group="biochemical",
                classification="calibrated",
                description="Taxa máxima específica de hidrogenotróficos quando E15 está ativo.",
                source=_SRC,
                notes="Table 4 do paper-base: kmH2 = 90 COD/(COD·d) no ADM1_modified.",
            ),
            ParameterDefinition(
                name="K_S_ac",
                value=0.05,
                unit=KG_COD_M3,
                group="biochemical",
                classification="calibrated",
                description="Constante de meia-saturação de acetato quando E15 está ativo.",
                source=_SRC,
                notes="Table 4 do paper-base: Ksac = 0.05 kgCOD/m³ no ADM1_modified.",
            ),
            ParameterDefinition(
                name="K_S_h2",
                value=1.0e-6,
                unit=KG_COD_M3,
                group="biochemical",
                classification="calibrated",
                description="Constante de meia-saturação de hidrogênio quando E15 está ativo.",
                source=_SRC,
                notes="Table 4 do paper-base: KsH2 = 1e-6 kgCOD/m³ no ADM1_modified.",
            ),
            ParameterDefinition(
                name="K_H_CO",
                value=8.0e-4,
                unit="kmol/m3/bar",
                group="physicochemical",
                classification="calibrated",
                description="Constante de Henry para CO (kmol/m³/bar a 35°C).",
                source=_SRC,
                notes=(
                    "K_H_CO(25°C) ≈ 9.7e-4 mol/(L·atm) = 9.58e-4 kmol/(m³·bar). "
                    "At 35°C: ΔH_sol(CO) ≈ -13.7 kJ/mol → K_H(35°C) ≈ 8.0e-4 kmol/(m³·bar). "
                    "CO is only slightly more soluble than H2 (K_H_h2 ≈ 7.8e-4 at 35°C)."
                ),
            ),
            ParameterDefinition(
                name="k_La_CO",
                value=200.0,
                unit=DAY_INV,
                group="physicochemical",
                classification="calibrated",
                description="Coeficiente volumétrico de transferência de massa para CO (d⁻¹).",
                source=_SRC,
                notes="Same order of magnitude as k_La for H2/CH4/CO2 (200 d⁻¹ in ADM1 BSM2).",
            ),
            ParameterDefinition(
                name="K_I_CO",
                value=1.03e-3,
                unit=KG_COD_M3,
                group="biochemical",
                classification="calibrated",
                description="Constante de inibição de CO sobre metanogênese acetoclástica rho_11 (kgCOD/m³).",
                source=_SRC,
                notes=(
                    "Sun et al. (2021) Eq. 14: Icoac = 1 / (1 + S_CO / K_I,COac). "
                    "Sun et al. do not publish the value (supplementary Table A1: 'M-ND'). Value from "
                    "Postacchini et al. (2024) Bioresour. Technol. 407:131076, doi:10.1016/j.biortech.2024.131076, "
                    "Table 1: K_I,CO,AM = 1.8e-3 g CO/L, noncompetitive (Eq. 4), mesophilic mixed culture. "
                    "1.8e-3 / 28 g/mol x 16 gCOD/mol = 1.03e-3 kgCOD/m3. Fitted in batch with carboxydotrophs "
                    "suppressed; adapted cultures can tolerate more CO."
                ),
            ),
            ParameterDefinition(
                name="K_I_CO_h2",
                value=5.0e-3,
                unit=KG_COD_M3,
                group="biochemical",
                classification="calibrated",
                description="Constante de inibição de CO sobre metanogênese hidrogenotrófica rho_12 (kgCOD/m³).",
                source=_SRC,
                notes=(
                    "Sun et al. (2021) Eq. 15: IcoH2 = 1 / (1 + S_CO / K_I,COH2), applied to H2, butyrate "
                    "and propionate uptake (Table 3). No published value: Sun et al. list it as 'M-ND', and "
                    "Grimalt-Alemany et al. (2020) Appl. Energy 262:114502 (doi:10.1016/j.apenergy.2020.114502, "
                    "§3.5) found no CO inhibition of hydrogenotrophic methanogens in mixed cultures. This "
                    "placeholder keeps them less sensitive than acetoclastic methanogens."
                ),
            ),
            ParameterDefinition(
                name="f_co_to_h2",
                value=0.65,
                unit=DIMENSIONLESS,
                group="stoichiometric",
                classification="calibrated",
                description="Fração do consumo de CO via rota WGS (→ H2). Complemento (1-f) vai para homoacetogênese (→ acetato).",
                source=_SRC,
                notes=(
                    "Parâmetro proxy para repartir o consumo de CO entre WGS (→ H2) e CO-acetogênese (→ acetato). "
                    "Sun et al. (2021) mostram pathway final acetoclástico dominante no lab-scale (67–78%) e "
                    "hidrogenotrófico dominante no pilot-scale (~65%). Use valores menores para cenários lab-scale "
                    "e maiores para cenários pilot-scale/WGS-dominantes."
                ),
            ),
        )

        # Stoichiometry notes:
        #   rho_E15_CO_uptake: S_CO (1 kgCOD) → products
        #     S_CO: -1 (substrate consumed)
        #     S_h2: +(1-Y_met_CO) (H2 produced via WGS; COD-balanced since CO and H2 share 16 gCOD/mol)
        #     S_IC: carbon balance: CO provides 1 C per mol = 0.0625 kmolC/kgCOD
        #           catabolized fraction (1-Y) CO carbon → CO2 → S_IC
        #           anabolic fraction Y × C_bac → X_met_CO
        #           Δ S_IC = +0.0625 - Y × C_bac
        #           Simplified: +(0.0625 - Y_met_CO * (0.0625 + C_bac))
        #           = 0.0625 - Y_met_CO * C_bac
        #     S_IN: -Y_met_CO * N_bac (nitrogen for biomass growth)
        #     X_met_CO: +Y_met_CO
        #
        #   rho_E15_decay_X_met_CO: X_met_CO → X_xc (identical to other ADM1 biomass decays)
        #
        #   rho_E15_CO_transfer: CO gas-liquid (net transfer from liquid to gas when S_CO supersaturated)
        #     S_CO: -1 (rate × -1 removes dissolved CO when transferring to gas)
        #     S_gas_CO: +V_liq/V_gas (scales liquid-basis rate to gas-volume basis)
        #     rhs.py adds venting: -(q_gas/V_gas)*S_gas_CO for all extension gas states
        biochemical_stoichiometry_rows = {
            "rho_E15_CO_uptake": {
                "S_CO": "-1",
                "S_h2": "1 - Y_met_CO",
                # S_IC: C from CO (0.0625 kmolC/kgCOD) catabolism → CO2, minus C to biomass
                "S_IC": "C_CO - Y_met_CO * C_bac",
                "S_IN": "-Y_met_CO * N_bac",
                "X_met_CO": "Y_met_CO",
            },
            # CO homoacetogenesis: 4CO + 2H2O → CH3COO⁻ + H⁺ + 2CO2
            # Per kgCOD CO (catabolism fraction 1-Y):
            #   S_ac += (1-Y)  [COD-balanced: COD_CO ≡ COD_acetate per reaction]
            #   S_IC net = C_CO×(1-Y) - C_ac×(1-Y) - Y×C_bac
            #           = 0.0625 - (1-Y)×C_ac - Y×C_bac
            #   where C_CO=0.0625 kmolC/kgCOD, C_ac≈0.0313 kmolC/kgCOD
            "rho_E15_CO_acetate": {
                "S_CO": "-1",
                "S_ac": "1.0 - Y_met_CO",
                "S_IC": "C_CO - (1.0 - Y_met_CO) * C_ac - Y_met_CO * C_bac",
                "S_IN": "-Y_met_CO * N_bac",
                "X_met_CO": "Y_met_CO",
            },
            "rho_E15_decay_X_met_CO": {
                "X_xc": "1",
                "X_met_CO": "-1",
                "S_IC": "-s_13",
                "S_IN": "N_bac - N_xc",
            },
            "rho_E15_CO_transfer": {
                "S_CO": "-1",
                "S_gas_CO": "V_liq / V_gas",
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
        s_co = max(float(state.get("S_CO", 0.0)), 0.0)
        s_gas_co = max(float(state.get("S_gas_CO", 0.0)), 0.0)
        x_met_co = max(float(state.get("X_met_CO", 0.0)), 0.0)
        s_h_ion = max(float(state.get("S_H_ion", 1e-7)), 1e-14)
        s_in = max(float(state.get("S_IN", 0.0)), 0.0)

        # pH inhibition (same shape as hydrogenotrophic methanogens, analogous organisms)
        i_ph_h2 = (params["K_pH_h2"] ** params["n_h2"]) / (s_h_ion ** params["n_h2"] + params["K_pH_h2"] ** params["n_h2"])
        # Nitrogen limitation
        i_in_lim = s_in / (float(params["K_S_IN"]) + s_in)

        # Total CO uptake rate (both routes share X_met_CO and Monod kinetics)
        rho_co_total = (
            float(params["k_m_met_CO"])
            * s_co / (float(params["K_S_CO"]) + s_co)
            * x_met_co
            * i_ph_h2
            * i_in_lim
        )
        # Split between WGS (→ H2) and homoacetogenesis (→ acetate) routes
        f_to_h2 = float(params.get("f_co_to_h2", 1.0))
        rho_co_uptake = rho_co_total * f_to_h2
        rho_co_acetate = rho_co_total * (1.0 - f_to_h2)

        rho_dec_met_co = float(params["k_dec_X_met_CO"]) * x_met_co

        # Gas-liquid CO transfer (Henry's law, same convention as rho_t8 for H2 in gas_transfer.py)
        r_gas = float(params.get("R", 8.314e-2))  # bar·m³/(kmol·K)
        t_op = float(params.get("T_op", 308.15))
        p_gas_co = s_gas_co * r_gas * t_op / 16.0  # bar (analogous to p_gas_h2)
        k_h_co = float(params.get("K_H_CO", 8.0e-4))
        rho_co_transfer = float(params["k_La_CO"]) * (s_co - 16.0 * k_h_co * p_gas_co)

        return {
            "rho_E15_CO_uptake": rho_co_uptake,
            "rho_E15_CO_acetate": rho_co_acetate,
            "rho_E15_decay_X_met_CO": rho_dec_met_co,
            "rho_E15_CO_transfer": rho_co_transfer,
        }

    def _inhibition(self, state: Mapping[str, float], params: Mapping[str, float]) -> dict[str, float]:
        """Noncompetitive CO inhibition (Sun et al. 2021, §2.3.3, Eqs. 14-15, Table 3).

            I_CO_ac = 1 / (1 + S_CO / K_I,COac)   -> acetate uptake (rho_11)
            I_CO_h2 = 1 / (1 + S_CO / K_I,COH2)   -> H2 uptake (rho_12) and, per
                                                     Table 3, butyrate and
                                                     propionate uptake.
        Sun's glucose model has no valerate; ADM1 valerate uptake uses the same
        X_c4 as butyrate, so it receives I_CO_h2 too. Sun's Table 3 also adds
        H2 inhibition to acetate uptake (K_I,H2ac); it is not applied here.

        At typical dissolved CO concentrations (< 0.01 kgCOD/m³) both factors are > 0.99 —
        inhibition is negligible. At high CO partial pressures (> 0.3 bar) inhibition becomes significant.
        Hydrogenotrophic methanogens are somewhat more CO-tolerant than acetoclastic ones.
        """
        s_co = max(float(state.get("S_CO", 0.0)), 0.0)
        k_i_co_ac = float(params.get("K_I_CO", 1.03e-3))
        k_i_co_h2 = float(params.get("K_I_CO_h2", 5.0e-3))
        i_co_ac = k_i_co_ac / (k_i_co_ac + s_co)
        i_co_h2 = k_i_co_h2 / (k_i_co_h2 + s_co)
        return {
            "rho_8_uptake_valerate": i_co_h2,
            "rho_9_uptake_butyrate": i_co_h2,
            "rho_10_uptake_propionate": i_co_h2,
            "rho_11_uptake_acetate": i_co_ac,
            "rho_12_uptake_hydrogen": i_co_h2,
        }

    def _diagnostics(
        self,
        matrix: np.ndarray,
        assembly: FullModelAssembly,
        params: Mapping[str, float],
    ) -> dict[str, list[float]]:
        s_co = np.clip(matrix[:, assembly.full_state_index["S_CO"]], 0.0, None)
        s_gas_co = np.clip(matrix[:, assembly.full_state_index["S_gas_CO"]], 0.0, None)
        x_met_co = np.clip(matrix[:, assembly.full_state_index["X_met_CO"]], 0.0, None)
        s_ch4 = np.clip(matrix[:, assembly.full_state_index["S_ch4"]], 0.0, None)

        # Partial pressure of CO in headspace (bar)
        r_gas = float(params.get("R", 8.314e-2))
        t_op = float(params.get("T_op", 308.15))
        p_gas_co = s_gas_co * r_gas * t_op / 16.0  # bar

        # CO conversion proxy: fraction consumed relative to influent
        s_co_0 = float(params.get("S_CO_influent_proxy", 0.0)) or (s_co[0] if s_co[0] > 1e-6 else 1.0)
        co_conversion = np.clip(1.0 - s_co / max(s_co_0, 1e-9), 0.0, 1.0)

        # CH4 yield from CO pathway (proxy: total CH4 at time t)
        s_gas_ch4 = np.clip(matrix[:, assembly.full_state_index["S_gas_ch4"]], 0.0, None)
        r_gas_arr = np.full(len(s_co), r_gas)
        p_gas_ch4 = s_gas_ch4 * r_gas_arr * t_op / 64.0  # bar

        return {
            "S_CO": s_co.astype(float).tolist(),
            "S_gas_CO": s_gas_co.astype(float).tolist(),
            "X_met_CO": x_met_co.astype(float).tolist(),
            "p_gas_CO_bar": p_gas_co.astype(float).tolist(),
            "CO_conversion": co_conversion.astype(float).tolist(),
            "p_gas_CH4_bar": p_gas_ch4.astype(float).tolist(),
        }


SYNGAS_EXTENSION = _SyngasExtension()
