"""E5 — Adsorção de LCFA (Long-Chain Fatty Acid Adsorption Extension).

Adds a surface-adsorbed LCFA intermediate (X_LCFA_ads) to capture the kinetic
lag between free LCFA (S_fa) and actual biodegradation. This is important in
systems treating lipid-rich wastes (grease trap, DAF sludge, OFMSW).

Mechanism (Zonta et al. 2013, equation 1):
  Free LCFA (S_fa) first adsorbs onto the active biomass surface:
      rho_ads = k_ads * (S_fa / S_ref) * max(q_sat * X_total_active - X_LCFA_ads, 0)

  Adsorbed LCFA desorbs back to free LCFA:
      X_LCFA_ads → S_fa  (k_des, first-order in X_LCFA_ads)

  Adsorbed LCFA is also biologically degraded (via standard beta-oxidation):
      X_LCFA_ads → products (modeled as negative term in X_LCFA_ads balance)
      Note: the actual degradation products (H2, acetate) are computed by core
      rho_6 (S_fa uptake). The adsorption layer only affects the AVAILABLE S_fa
      pool, creating kinetic inhibition of LCFA-degrading acetogens.

Contact inhibition on rho_7_uptake_lcfa (Palatsi 2010):
  Adsorbed LCFA (X_LCFA_ads) blocks the cell surface of LCFA-degrading acetogens,
  reducing their effective uptake rate. This is modeled as non-competitive inhibition
  on the core rho_7_uptake_lcfa process:
      I_LCFA_contact = K_I_LCFA_ads / (K_I_LCFA_ads + X_LCFA_ads)
  where K_I_LCFA_ads = 3.35 kgCOD/m³ (Palatsi 2010 Table 5b, Approach A2, Batch II).
  Note: Palatsi A2 applies K_I to total free LCFA (S_fa); here we apply it to the
  adsorbed fraction (X_LCFA_ads). Palatsi's Approach A3 (preferred) uses a dynamic
  inhibition constant K_IFA = K'_I × (X_fa/S_fa) with K'_I = 2.37e-3 kgCOD/m³,
  but requires a different model structure. Applied via InhibitionHookType in kinetics.py.

Reference:
    Palatsi et al. (2010). "Long-chain fatty acids inhibition and adaptation in
    anaerobic thermophilic digestion: Batch tests, microbial community structure
    and mathematical modelling." Bioresource Technology 101(7):2243-2251.
    doi:10.1016/j.biortech.2009.11.069
    Zonta, Alves, Flotats & Palatsi (2013). "Modelling inhibitory effects of long
    chain fatty acids in the anaerobic digestion process." Water Research
    47(3):1369-1380. doi:10.1016/j.watres.2012.12.007
"""
from __future__ import annotations

from typing import Mapping

import numpy as np

from simulator.full_model.assembly import FullModelAssembly
from simulator.full_model.catalog_types import ParameterDefinition, ProcessDefinition, StateDefinition
from simulator.full_model.extensions import FullModelExtensionContribution
from simulator.full_model.units import DAY_INV, DIMENSIONLESS, KG_COD_M3

_SRC = "Palatsi et al. (2010) doi:10.1016/j.biortech.2009.11.069; Zonta et al. (2013) doi:10.1016/j.watres.2012.12.007"
_S_FA_REFERENCE_KG_COD_M3 = 1.0

# Core active biomass groups used to estimate X_total_active for adsorption
_ACTIVE_BIOMASS = ("X_su", "X_aa", "X_fa", "X_c4", "X_pro", "X_ac", "X_h2")


class _LCFAExtension:
    name = "lcfa_adsorption"
    description = "E5: adsorção de LCFA livre na superfície da biomassa ativa (Palatsi 2010)."

    def contribute(self) -> FullModelExtensionContribution:
        states = (
            StateDefinition(
                name="X_LCFA_ads",
                description="LCFA adsorvido na superfície da biomassa ativa.",
                unit=KG_COD_M3,
                phase="solid",
                domain="inert_or_inorganic",
                role="dynamic",
                cod_role="cod",
                elemental_proxy="C_fa",
                source=_SRC,
                notes="Intermediário cinético entre S_fa livre e degradação. "
                      "Mesma composição elementar de S_fa (C_fa = 0.02179 kmolC/kgCOD).",
            ),
        )

        processes = (
            ProcessDefinition(
                name="rho_E5_LCFA_adsorption",
                vendor_symbol="Rho_E5_1",
                family="biochemical",
                description="Adsorção de LCFA livre na superfície da biomassa ativa.",
                rate_expression="computed_by_extension",
                affected_states=("S_fa", "X_LCFA_ads"),
                parameters=("k_ads_LCFA", "q_sat_LCFA"),
                inhibitions=(),
                source=_SRC,
            ),
            ProcessDefinition(
                name="rho_E5_LCFA_desorption",
                vendor_symbol="Rho_E5_2",
                family="biochemical",
                description="Dessorção de LCFA adsorvido de volta à fase líquida.",
                rate_expression="computed_by_extension",
                affected_states=("X_LCFA_ads", "S_fa"),
                parameters=("k_des_LCFA",),
                inhibitions=(),
                source=_SRC,
            ),
            ProcessDefinition(
                name="rho_E5_LCFA_ads_degradation",
                vendor_symbol="Rho_E5_3",
                family="biochemical",
                description="Degradação biológica direta do LCFA adsorvido (beta-oxidação na superfície).",
                rate_expression="computed_by_extension",
                affected_states=("X_LCFA_ads", "S_ac", "S_h2", "S_IC", "X_fa"),
                parameters=("k_m_LCFA_ads", "K_S_LCFA_ads", "Y_fa"),
                inhibitions=("I_pH_aa", "I_IN_lim", "I_h2_fa"),
                source=_SRC,
                notes="Uses core ADM1 Y_fa and stoichiometry for beta-oxidation of LCFA.",
            ),
        )

        parameters = (
            ParameterDefinition(
                name="k_ads_LCFA",
                value=0.350,
                unit=DAY_INV,
                group="biochemical",
                classification="provisional",
                description="Constante de adsorção de LCFA com concentração de referência.",
                source=_SRC,
                notes="Zonta et al. (2013), supplementary Table B: 0.350 d^-1. "
                      "Equation 1 multiplies two concentrations, so its coefficient requires "
                      "m3/(kgCOD d), inconsistent with the table. Assumed reference concentration "
                      "1 kgCOD/m3 to normalize S_fa; the numerical value is provisional and requires calibration.",
            ),
            ParameterDefinition(
                name="q_sat_LCFA",
                value=0.82 / (0.85 * 1.42),
                unit="kgCOD_LCFA/kgCOD_biomass",
                group="biochemical",
                classification="provisional",
                description="Capacidade de adsorção por DQO de biomassa ativa.",
                source="Zonta et al. (2013) doi:10.1016/j.watres.2012.12.007; "
                       "https://theses.lib.polyu.edu.hk/bitstream/200/3897/1/b15354325.pdf; "
                       "Rao (2018), The operational viability of implementing anaerobic digestion technology",
                notes="Supplementary Table B: 0.82 kgCOD/kgTS, CI-95% ±1.107 labelled wide and unrealistic. "
                      "Assume TS equals TSS, VSS/TSS=0.85 (Ng 1999, section 4.2), and "
                      "1.42 kgCOD/kgVSS (Rao 2018, section 2.5): 0.82/(0.85*1.42). "
                      "Approximate all VSS as active biomass; unlike Zonta, inert and slowly biodegradable "
                      "solids are excluded from adsorption sites. These assumptions require local validation.",
            ),
            ParameterDefinition(
                name="k_des_LCFA",
                value=0.2,
                unit=DAY_INV,
                group="biochemical",
                classification="calibrated",
                description="Constante de primeira ordem para dessorção de LCFA.",
                source=_SRC,
                notes="Zonta et al. (2013), supplementary Table B: k_dis,bio = 0.2 d^-1, CI-95% ±0.174.",
            ),
            ParameterDefinition(
                name="k_m_LCFA_ads",
                value=21.69,
                unit=DAY_INV,
                group="biochemical",
                classification="calibrated",
                description="Taxa máxima de degradação de LCFA adsorvido por X_fa.",
                source=_SRC,
                notes="Palatsi 2010 Table 5b, Approach A2 (Batch II): k_m_LCFA_ads = 21.69 d⁻¹. "
                      "Substrate is X_LCFA_ads rather than free S_fa.",
            ),
            ParameterDefinition(
                name="K_S_LCFA_ads",
                value=0.40,
                unit=KG_COD_M3,
                group="biochemical",
                classification="calibrated",
                description="Meia-saturação para degradação de LCFA adsorvido.",
                source=_SRC,
                notes="Palatsi 2010 Table 5b: K_S for adsorbed LCFA degradation. "
                      "Same order as core K_S_fa (0.4 kgCOD/m³ ADM1 Table 6).",
            ),
            ParameterDefinition(
                name="f_ac_fa",
                value=0.7,
                unit="dimensionless",
                group="stoichiometric",
                classification="canonical",
                description="Fração COD catabolisado de LCFA → acetato (0.7, ADM1 Table 6).",
                source=_SRC,
                notes="Same value as core ADM1 rho_7 (used as literal 0.7 there; explicit here for eval namespace).",
            ),
            ParameterDefinition(
                name="f_h2_fa",
                value=0.3,
                unit="dimensionless",
                group="stoichiometric",
                classification="canonical",
                description="Fração COD catabolisado de LCFA → H2 (0.3, ADM1 Table 6).",
                source=_SRC,
            ),
            ParameterDefinition(
                name="K_I_LCFA_ads",
                value=3.35,
                unit=KG_COD_M3,
                group="biochemical",
                classification="calibrated",
                description="Constante de inibição por contato de LCFA adsorvido sobre rho_7 (kgCOD/m³).",
                source=_SRC,
                notes="Palatsi 2010 Table 5b, Approach A2 (Batch II): K_I = 3.35 kgCOD/m³. "
                      "Em Palatsi A2, K_I é aplicada a S_fa (LCFA livre total) na inibição não-competitiva "
                      "das metanogêneses acetoclástica e hidrogenotrófica. Aqui aplicamos a X_LCFA_ads "
                      "(fração adsorvida) por coerência com a estrutura de adsorção do modelo. "
                      "Palatsi A3 (preferido) usa K'_I = 2.37e-3 kgCOD/m³ com K_IFA = K'_I*(X_fa/S_fa).",
            ),
        )

        # Adsorption: S_fa → X_LCFA_ads (COD-conserving, same elemental composition)
        # Desorption: X_LCFA_ads → S_fa (reverse)
        # Degradation of adsorbed LCFA: same stoichiometry as core rho_6 (S_fa → S_ac + S_h2 + X_fa)
        #   Using ADM1 Table 6 for S_fa: f_h2_fa=0.3, f_ac_fa=0.7 (by COD)
        #   S_IC = C_fa - (1-Y_fa)*f_ac_fa*C_ac - Y_fa*C_bac
        biochemical_stoichiometry_rows = {
            "rho_E5_LCFA_adsorption": {
                "S_fa": "-1",
                "X_LCFA_ads": "1",
            },
            "rho_E5_LCFA_desorption": {
                "X_LCFA_ads": "-1",
                "S_fa": "1",
            },
            "rho_E5_LCFA_ads_degradation": {
                "X_LCFA_ads": "-1",
                "S_ac": "(1.0 - Y_fa) * f_ac_fa",
                "S_h2": "(1.0 - Y_fa) * f_h2_fa",
                "S_IC": "C_fa - (1.0 - Y_fa) * f_ac_fa * C_ac - Y_fa * C_bac",
                "S_IN": "-Y_fa * N_bac",
                "X_fa": "Y_fa",
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
        s_fa = max(float(state.get("S_fa", 0.0)), 0.0)
        x_lcfa_ads = max(float(state.get("X_LCFA_ads", 0.0)), 0.0)
        x_fa = max(float(state.get("X_fa", 0.0)), 0.0)
        s_h_ion = max(float(state.get("S_H_ion", 1e-7)), 1e-14)
        s_in = max(float(state.get("S_IN", 0.0)), 0.0)
        s_h2 = max(float(state.get("S_h2", 0.0)), 1e-12)

        x_total_active = sum(max(float(state.get(xi, 0.0)), 0.0) for xi in _ACTIVE_BIOMASS)

        i_ph_aa = (params["K_pH_aa"] ** params["nn_aa"]) / (s_h_ion ** params["nn_aa"] + params["K_pH_aa"] ** params["nn_aa"])
        i_in_lim = s_in / (float(params["K_S_IN"]) + s_in)
        i_h2_fa = 1.0 / (1.0 + s_h2 / params["K_I_h2_fa"])

        # Zonta et al. (2013), Eq. 1: normalize S_fa by the assumed 1 kgCOD/m3 reference.
        available_capacity = max(float(params["q_sat_LCFA"]) * x_total_active - x_lcfa_ads, 0.0)
        rho_ads = float(params["k_ads_LCFA"]) * (s_fa / _S_FA_REFERENCE_KG_COD_M3) * available_capacity
        rho_des = float(params["k_des_LCFA"]) * x_lcfa_ads
        k_s_lcfa_ads = float(params["K_S_LCFA_ads"])
        rho_deg = float(params["k_m_LCFA_ads"]) * x_lcfa_ads / (k_s_lcfa_ads + x_lcfa_ads) * x_fa * i_ph_aa * i_in_lim * i_h2_fa

        return {
            "rho_E5_LCFA_adsorption": rho_ads,
            "rho_E5_LCFA_desorption": rho_des,
            "rho_E5_LCFA_ads_degradation": rho_deg,
        }

    def _inhibition(self, state: Mapping[str, float], params: Mapping[str, float]) -> dict[str, float]:
        """Non-competitive contact inhibition of LCFA-degrading acetogens by adsorbed LCFA.

        Adsorbed LCFA (X_LCFA_ads) blocks the cell surface, reducing the effective uptake
        rate of rho_7_uptake_lcfa (core LCFA β-oxidation). Model from Palatsi 2010 Table 2:
            I_LCFA_contact = K_I_LCFA_ads / (K_I_LCFA_ads + X_LCFA_ads)
        """
        x_lcfa_ads = max(float(state.get("X_LCFA_ads", 0.0)), 0.0)
        k_i = float(params.get("K_I_LCFA_ads", 0.10))
        i_lcfa = k_i / (k_i + x_lcfa_ads)
        return {"rho_7_uptake_lcfa": i_lcfa}

    def _diagnostics(
        self, matrix: np.ndarray, assembly: FullModelAssembly, params: Mapping[str, float]
    ) -> dict[str, list[float]]:
        x_lcfa_ads = np.clip(matrix[:, assembly.full_state_index["X_LCFA_ads"]], 0.0, None)
        return {
            "X_LCFA_ads": x_lcfa_ads.astype(float).tolist(),
        }


LCFA_EXTENSION = _LCFAExtension()
