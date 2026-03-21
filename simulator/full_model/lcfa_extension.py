"""E5 — Adsorção de LCFA (Long-Chain Fatty Acid Adsorption Extension).

Adds a surface-adsorbed LCFA intermediate (X_LCFA_ads) to capture the kinetic
lag between free LCFA (S_fa) and actual biodegradation. This is important in
systems treating lipid-rich wastes (grease trap, DAF sludge, OFMSW).

Mechanism (Palatsi 2010):
  Free LCFA (S_fa) first adsorbs onto the active biomass surface:
      S_fa + X_total_active → X_LCFA_ads  (k_ads, first-order in X_total_active)

  Adsorbed LCFA desorbs back to free LCFA:
      X_LCFA_ads → S_fa  (k_des, first-order in X_LCFA_ads)

  Adsorbed LCFA is also biologically degraded (via standard beta-oxidation):
      X_LCFA_ads → products (modeled as negative term in X_LCFA_ads balance)
      Note: the actual degradation products (H2, acetate) are computed by core
      rho_6 (S_fa uptake). The adsorption layer only affects the AVAILABLE S_fa
      pool, creating kinetic inhibition of LCFA-degrading acetogens.

v1 Limitation:
  The classical LCFA inhibition (competitive sorption blocking cell surface) is
  approximated via the adsorption/desorption dynamics reducing S_fa. Direct
  inhibition constants on X_fa (rho_6) require modification of kinetics.py,
  which is outside the extension architecture in this version.

Reference:
    Palatsi et al. (2010). "Anaerobic digestion of slaughterhouse waste —
    Description and validation of a new model for long-chain fatty acids."
    Bioresource Technology 101(14):5523-5532. doi:10.1016/j.biortech.2010.02.069
    Zonta et al. (2013). "Strategies to improve the energy efficiency of the
    anaerobic digestion of slaughterhouse waste." Bioresource Technology 142:
    431-438. doi:10.1016/j.biortech.2013.05.061
"""
from __future__ import annotations

from typing import Mapping

import numpy as np

from simulator.full_model.assembly import FullModelAssembly
from simulator.full_model.catalog_types import ParameterDefinition, ProcessDefinition, StateDefinition
from simulator.full_model.extensions import FullModelExtensionContribution
from simulator.full_model.units import DAY_INV, DIMENSIONLESS, KG_COD_M3

_SRC = "Palatsi et al. (2010) doi:10.1016/j.biortech.2010.02.069; Zonta et al. (2013) doi:10.1016/j.biortech.2013.05.061"

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
                parameters=("k_ads_LCFA",),
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
                value=10.0,
                unit="m3/kgCOD/d",
                group="biochemical",
                classification="provisional",
                description="Constante de adsorção de LCFA (k_ads × X_total_active).",
                source=_SRC,
                notes="Palatsi 2010 Table 2. Units: m³/(kgCOD·d).",
            ),
            ParameterDefinition(
                name="k_des_LCFA",
                value=0.2,
                unit=DAY_INV,
                group="biochemical",
                classification="provisional",
                description="Constante de primeira ordem para dessorção de LCFA.",
                source=_SRC,
                notes="Palatsi 2010 Table 2.",
            ),
            ParameterDefinition(
                name="k_m_LCFA_ads",
                value=6.0,
                unit=DAY_INV,
                group="biochemical",
                classification="provisional",
                description="Taxa máxima de degradação de LCFA adsorvido por X_fa.",
                source=_SRC,
                notes="Uses same kinetics as rho_6 but substrate is X_LCFA_ads.",
            ),
            ParameterDefinition(
                name="K_S_LCFA_ads",
                value=0.40,
                unit=KG_COD_M3,
                group="biochemical",
                classification="provisional",
                description="Meia-saturação para degradação de LCFA adsorvido.",
                source=_SRC,
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
        )

    def _rates(self, state: Mapping[str, float], params: Mapping[str, float]) -> dict[str, float]:
        s_fa = max(float(state.get("S_fa", 0.0)), 0.0)
        x_lcfa_ads = max(float(state.get("X_LCFA_ads", 0.0)), 0.0)
        x_fa = max(float(state.get("X_fa", 0.0)), 0.0)
        s_h_ion = max(float(state.get("S_H_ion", 1e-7)), 1e-14)
        s_in = max(float(state.get("S_IN", 1e-4)), 1e-12)
        s_h2 = max(float(state.get("S_h2", 0.0)), 1e-12)

        # Total active biomass concentration (m³-denominator for second-order adsorption)
        x_total_active = sum(max(float(state.get(xi, 0.0)), 0.0) for xi in _ACTIVE_BIOMASS)

        i_ph_aa = (params["K_pH_aa"] ** params["nn_aa"]) / (s_h_ion ** params["nn_aa"] + params["K_pH_aa"] ** params["nn_aa"])
        i_in_lim = 1.0 / (1.0 + params["K_S_IN"] / s_in)
        i_h2_fa = 1.0 / (1.0 + s_h2 / params["K_I_h2_fa"])

        rho_ads = float(params["k_ads_LCFA"]) * s_fa * x_total_active
        rho_des = float(params["k_des_LCFA"]) * x_lcfa_ads
        k_s_lcfa_ads = float(params["K_S_LCFA_ads"])
        rho_deg = float(params["k_m_LCFA_ads"]) * x_lcfa_ads / (k_s_lcfa_ads + x_lcfa_ads) * x_fa * i_ph_aa * i_in_lim * i_h2_fa

        return {
            "rho_E5_LCFA_adsorption": rho_ads,
            "rho_E5_LCFA_desorption": rho_des,
            "rho_E5_LCFA_ads_degradation": rho_deg,
        }

    def _diagnostics(
        self, matrix: np.ndarray, assembly: FullModelAssembly, params: Mapping[str, float]
    ) -> dict[str, list[float]]:
        x_lcfa_ads = np.clip(matrix[:, assembly.full_state_index["X_LCFA_ads"]], 0.0, None)
        return {
            "X_LCFA_ads": x_lcfa_ads.astype(float).tolist(),
        }


LCFA_EXTENSION = _LCFAExtension()
