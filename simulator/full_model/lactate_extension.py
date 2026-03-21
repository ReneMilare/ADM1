"""E6 — Via do Lactato (Lactate Pathway Extension).

Adds lactate (S_lac) as an explicit intermediate during sugar fermentation, and
a dedicated lactate-fermenting acetogen (X_lac) that converts lactate to acetate
and H2.

Stoichiometry (per kgCOD substrate):
  Lactate overflow from sugars (COD-conserving, no net S_IC/S_IN change):
      S_su → S_lac  (C_su = C_lac = 0.03125 kmolC/kgCOD, both = C3-body fraction)

  Lactate catabolism (COD-conserving):
      S_lac → (1-Y)*f_ac*S_ac + (1-Y)*f_h2*S_h2 + Y*X_lac
      f_ac_lac = 64/96 = 0.6667, f_h2_lac = 32/96 = 0.3333
      (CH3CHOHCOOH → CH3COOH + CO2 + H2)

Reference:
    Poggio et al. (2022). Microorganisms 10(2):430.
    doi:10.3390/microorganisms10020430
"""
from __future__ import annotations

from typing import Mapping

import numpy as np

from simulator.full_model.assembly import FullModelAssembly
from simulator.full_model.catalog_types import ParameterDefinition, ProcessDefinition, StateDefinition
from simulator.full_model.extensions import FullModelExtensionContribution
from simulator.full_model.units import DAY_INV, DIMENSIONLESS, KG_COD_M3, KMOL_C_PER_KG_COD

_SRC = "Poggio et al. (2022) Microorganisms doi:10.3390/microorganisms10020430"


class _LactateExtension:
    name = "lactate"
    description = "E6: lactato como intermediário explícito na fermentação de açúcares (Poggio 2022)."

    def contribute(self) -> FullModelExtensionContribution:
        states = (
            StateDefinition(
                name="S_lac",
                description="Lactato dissolvido (intermediário da fermentação de açúcares).",
                unit=KG_COD_M3,
                phase="liquid",
                domain="soluble",
                role="dynamic",
                cod_role="cod",
                elemental_proxy="C_su",
                source=_SRC,
                notes="C_lac = C_su = 0.03125 kmolC/kgCOD.",
            ),
            StateDefinition(
                name="X_lac",
                description="Acetogens fermentadores de lactato.",
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
                name="rho_E6_lactate_from_sugars",
                vendor_symbol="Rho_E6_1",
                family="biochemical",
                description="Produção de lactato como overflow da fermentação de açúcares.",
                rate_expression="computed_by_extension",
                affected_states=("S_su", "S_lac"),
                parameters=("k_lac_from_su", "K_S_lac_su"),
                inhibitions=("I_pH_aa", "I_IN_lim"),
                source=_SRC,
            ),
            ProcessDefinition(
                name="rho_E6_uptake_lactate",
                vendor_symbol="Rho_E6_2",
                family="biochemical",
                description="Consumo de lactato por X_lac → acetato + H2.",
                rate_expression="computed_by_extension",
                affected_states=("S_lac", "S_ac", "S_h2", "S_IC", "S_IN", "X_lac"),
                parameters=("k_m_lac", "K_S_lac", "Y_lac"),
                inhibitions=("I_pH_aa", "I_IN_lim", "I_h2_pro"),
                source=_SRC,
            ),
            ProcessDefinition(
                name="rho_E6_decay_X_lac",
                vendor_symbol="Rho_E6_3",
                family="biochemical",
                description="Decaimento de X_lac → X_xc.",
                rate_expression="computed_by_extension",
                affected_states=("X_xc", "X_lac", "S_IC", "S_IN"),
                parameters=("k_dec_X_lac",),
                inhibitions=(),
                source=_SRC,
            ),
        )

        parameters = (
            ParameterDefinition(
                name="k_lac_from_su",
                value=0.08,
                unit=DAY_INV,
                group="biochemical",
                classification="provisional",
                description="Taxa de overflow de açúcares para lactato.",
                source=_SRC,
            ),
            ParameterDefinition(
                name="K_S_lac_su",
                value=0.5,
                unit=KG_COD_M3,
                group="biochemical",
                classification="provisional",
                description="Meia-saturação para produção de lactato a partir de açúcares.",
                source=_SRC,
            ),
            ParameterDefinition(
                name="k_m_lac",
                value=8.0,
                unit=DAY_INV,
                group="biochemical",
                classification="provisional",
                description="Taxa máxima de consumo de lactato por X_lac.",
                source=_SRC,
                notes="Poggio 2022 Table 1.",
            ),
            ParameterDefinition(
                name="K_S_lac",
                value=0.4,
                unit=KG_COD_M3,
                group="biochemical",
                classification="provisional",
                description="Meia-saturação para lactato (X_lac).",
                source=_SRC,
            ),
            ParameterDefinition(
                name="Y_lac",
                value=0.05,
                unit=DIMENSIONLESS,
                group="stoichiometric",
                classification="provisional",
                description="Rendimento de biomassa no consumo de lactato.",
                source=_SRC,
            ),
            ParameterDefinition(
                name="k_dec_X_lac",
                value=0.02,
                unit=DAY_INV,
                group="biochemical",
                classification="provisional",
                description="Taxa de decaimento de X_lac.",
                source=_SRC,
            ),
            ParameterDefinition(
                name="C_lac",
                value=0.03125,
                unit=KMOL_C_PER_KG_COD,
                group="stoichiometric",
                classification="canonical",
                description="Conteúdo de carbono do lactato (3 molC / 96 gCOD = 0.03125).",
                source=_SRC,
            ),
            ParameterDefinition(
                name="f_ac_lac",
                value=0.6667,
                unit=DIMENSIONLESS,
                group="stoichiometric",
                classification="canonical",
                description="Fração COD catabolisado do lactato → acetato (64/96 ≈ 0.6667).",
                source=_SRC,
            ),
            ParameterDefinition(
                name="f_h2_lac",
                value=0.3333,
                unit=DIMENSIONLESS,
                group="stoichiometric",
                classification="canonical",
                description="Fração COD catabolisado do lactato → H2 (32/96 ≈ 0.3333).",
                source=_SRC,
            ),
        )

        # S_IC for uptake = C_lac - (1-Y)*f_ac_lac*C_ac - Y*C_bac
        # numerically: 0.03125 - 0.9500*0.6667*0.03125 - 0.05*0.03125 ≈ +0.00977 (CO2 released)
        biochemical_stoichiometry_rows = {
            "rho_E6_lactate_from_sugars": {
                "S_su": "-1",
                "S_lac": "1",
                # ΔS_IC = 0: C_su == C_lac; ΔS_IN = 0
            },
            "rho_E6_uptake_lactate": {
                "S_lac": "-1",
                "S_ac": "(1.0 - Y_lac) * f_ac_lac",
                "S_h2": "(1.0 - Y_lac) * f_h2_lac",
                "S_IC": "C_lac - (1.0 - Y_lac) * f_ac_lac * C_ac - Y_lac * C_bac",
                "S_IN": "-Y_lac * N_bac",
                "X_lac": "Y_lac",
            },
            "rho_E6_decay_X_lac": {
                "X_xc": "1",
                "X_lac": "-1",
                "S_IC": "-s_13",
                "S_IN": "N_bac - N_xc",
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
        s_su = max(float(state.get("S_su", 0.0)), 0.0)
        s_lac = max(float(state.get("S_lac", 0.0)), 0.0)
        x_su = max(float(state.get("X_su", 0.0)), 0.0)
        x_lac = max(float(state.get("X_lac", 0.0)), 0.0)
        s_h_ion = max(float(state.get("S_H_ion", 1e-7)), 1e-14)
        s_in = max(float(state.get("S_IN", 1e-4)), 1e-12)
        s_h2 = max(float(state.get("S_h2", 0.0)), 1e-12)

        i_ph_aa = (params["K_pH_aa"] ** params["nn_aa"]) / (s_h_ion ** params["nn_aa"] + params["K_pH_aa"] ** params["nn_aa"])
        i_in_lim = 1.0 / (1.0 + params["K_S_IN"] / s_in)
        i_h2_pro = 1.0 / (1.0 + s_h2 / params["K_I_h2_pro"])

        rho1 = float(params["k_lac_from_su"]) * s_su / (float(params["K_S_lac_su"]) + s_su) * x_su * i_ph_aa * i_in_lim
        rho2 = float(params["k_m_lac"]) * s_lac / (float(params["K_S_lac"]) + s_lac) * x_lac * i_ph_aa * i_in_lim * i_h2_pro
        rho3 = float(params["k_dec_X_lac"]) * x_lac

        return {
            "rho_E6_lactate_from_sugars": rho1,
            "rho_E6_uptake_lactate": rho2,
            "rho_E6_decay_X_lac": rho3,
        }

    def _diagnostics(
        self, matrix: np.ndarray, assembly: FullModelAssembly, params: Mapping[str, float]
    ) -> dict[str, list[float]]:
        s_lac = np.clip(matrix[:, assembly.full_state_index["S_lac"]], 0.0, None)
        x_lac = np.clip(matrix[:, assembly.full_state_index["X_lac"]], 0.0, None)
        return {
            "S_lac": s_lac.astype(float).tolist(),
            "X_lac": x_lac.astype(float).tolist(),
        }


LACTATE_EXTENSION = _LactateExtension()
