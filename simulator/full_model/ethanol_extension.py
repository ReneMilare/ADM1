"""E10 — Via do Etanol (Ethanol Pathway Extension).

Adds ethanol (S_et) as an explicit intermediate during sugar fermentation, and a
dedicated ethanol-oxidizing acetogen (X_et) that converts ethanol to acetate and H2.

Stoichiometry (per kgCOD substrate):
  Ethanol overflow from sugars (COD-conserving):
      S_su → S_et

  Ethanol catabolism (COD-conserving):
      S_et → (1-Y)*f_ac*S_ac + (1-Y)*f_h2*S_h2 + Y*X_et
      Reaction: C2H5OH + H2O → CH3COOH + 2 H2
        Ethanol COD = 96 gO2/mol (C2H5OH + 3 O2 → 2 CO2 + 3 H2O)
        Acetate COD  = 64 gO2/mol → f_ac_et = 64/96 = 0.6667
        H2 COD       = 32 gO2/mol → f_h2_et = 32/96 = 0.3333
      Carbon content: C_et = 2/96 = 0.02083 kmolC/kgCOD
        (2 mol C per mol C2H5OH, MW_COD = 96 gO2/mol)

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


class _EthanolExtension:
    name = "ethanol"
    description = "E10: etanol como intermediário explícito na fermentação de açúcares (Poggio 2022)."

    def contribute(self) -> FullModelExtensionContribution:
        states = (
            StateDefinition(
                name="S_et",
                description="Etanol dissolvido (intermediário da fermentação de açúcares).",
                unit=KG_COD_M3,
                phase="liquid",
                domain="soluble",
                role="dynamic",
                cod_role="cod",
                elemental_proxy=None,
                source=_SRC,
                notes="C_et = 2/96 = 0.02083 kmolC/kgCOD. Menor que C_bac.",
            ),
            StateDefinition(
                name="X_et",
                description="Acetogens oxidadores de etanol.",
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
                name="rho_E10_ethanol_from_sugars",
                vendor_symbol="Rho_E10_1",
                family="biochemical",
                description="Produção de etanol como overflow da fermentação de açúcares.",
                rate_expression="computed_by_extension",
                affected_states=("S_su", "S_et"),
                parameters=("k_et_from_su", "K_S_et_su"),
                inhibitions=("I_pH_aa", "I_IN_lim"),
                source=_SRC,
            ),
            ProcessDefinition(
                name="rho_E10_uptake_ethanol",
                vendor_symbol="Rho_E10_2",
                family="biochemical",
                description="Consumo de etanol por X_et → acetato + H2.",
                rate_expression="computed_by_extension",
                affected_states=("S_et", "S_ac", "S_h2", "S_IC", "S_IN", "X_et"),
                parameters=("k_m_et", "K_S_et", "Y_et"),
                inhibitions=("I_pH_aa", "I_IN_lim", "I_h2_pro"),
                source=_SRC,
            ),
            ProcessDefinition(
                name="rho_E10_decay_X_et",
                vendor_symbol="Rho_E10_3",
                family="biochemical",
                description="Decaimento de X_et → X_xc.",
                rate_expression="computed_by_extension",
                affected_states=("X_xc", "X_et", "S_IC", "S_IN"),
                parameters=("k_dec_X_et",),
                inhibitions=(),
                source=_SRC,
            ),
        )

        parameters = (
            ParameterDefinition(
                name="k_et_from_su",
                value=0.05,
                unit=DAY_INV,
                group="biochemical",
                classification="provisional",
                description="Taxa de overflow de açúcares para etanol.",
                source=_SRC,
            ),
            ParameterDefinition(
                name="K_S_et_su",
                value=0.5,
                unit=KG_COD_M3,
                group="biochemical",
                classification="provisional",
                description="Meia-saturação para produção de etanol a partir de açúcares.",
                source=_SRC,
            ),
            ParameterDefinition(
                name="k_m_et",
                value=6.0,
                unit=DAY_INV,
                group="biochemical",
                classification="provisional",
                description="Taxa máxima de consumo de etanol por X_et.",
                source=_SRC,
                notes="Poggio 2022 Table 1.",
            ),
            ParameterDefinition(
                name="K_S_et",
                value=0.3,
                unit=KG_COD_M3,
                group="biochemical",
                classification="provisional",
                description="Meia-saturação para etanol (X_et).",
                source=_SRC,
            ),
            ParameterDefinition(
                name="Y_et",
                value=0.05,
                unit=DIMENSIONLESS,
                group="stoichiometric",
                classification="provisional",
                description="Rendimento de biomassa no consumo de etanol.",
                source=_SRC,
            ),
            ParameterDefinition(
                name="k_dec_X_et",
                value=0.02,
                unit=DAY_INV,
                group="biochemical",
                classification="provisional",
                description="Taxa de decaimento de X_et.",
                source=_SRC,
            ),
            ParameterDefinition(
                name="C_et",
                value=0.02083,
                unit=KMOL_C_PER_KG_COD,
                group="stoichiometric",
                classification="canonical",
                description="Conteúdo de carbono do etanol (2 molC / 96 gCOD = 0.02083).",
                source=_SRC,
                notes="C2H5OH: 2 mol C per mol, COD = 96 gO2/mol (3×O2) → C_et = 2/96.",
            ),
            ParameterDefinition(
                name="f_ac_et",
                value=0.6667,
                unit=DIMENSIONLESS,
                group="stoichiometric",
                classification="canonical",
                description="Fração COD catabolisado de etanol → acetato (64/96 ≈ 0.6667).",
                source=_SRC,
            ),
            ParameterDefinition(
                name="f_h2_et",
                value=0.3333,
                unit=DIMENSIONLESS,
                group="stoichiometric",
                classification="canonical",
                description="Fração COD catabolisado de etanol → H2 (32/96 ≈ 0.3333).",
                source=_SRC,
            ),
        )

        # S_IC for ethanol overflow: C_su - C_et ≠ 0 (C_su=0.03125 > C_et=0.02083)
        #   ΔS_IC = -(C_su - C_et) per kgCOD: sugar has more C than ethanol; the deficit
        #   is captured as CO2 during fermentation.
        # S_IC for uptake: C_et - (1-Y)*f_ac_et*C_ac - Y*C_bac
        #   = 0.02083 - 0.95*0.6667*0.03125 - 0.05*0.03125
        #   = 0.02083 - 0.01979 - 0.00156 = -0.000525 → tiny S_IC decrease (C-poor substrate)
        biochemical_stoichiometry_rows = {
            "rho_E10_ethanol_from_sugars": {
                "S_su": "-1",
                "S_et": "1",
                # C_su != C_et: ΔS_IC = C_et - C_su (negative: CO2 produced during fermentation)
                "S_IC": "C_et - C_su",
                # S_IN = 0: no nitrogen involved
            },
            "rho_E10_uptake_ethanol": {
                "S_et": "-1",
                "S_ac": "(1.0 - Y_et) * f_ac_et",
                "S_h2": "(1.0 - Y_et) * f_h2_et",
                "S_IC": "C_et - (1.0 - Y_et) * f_ac_et * C_ac - Y_et * C_bac",
                "S_IN": "-Y_et * N_bac",
                "X_et": "Y_et",
            },
            "rho_E10_decay_X_et": {
                "X_xc": "1",
                "X_et": "-1",
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
        s_et = max(float(state.get("S_et", 0.0)), 0.0)
        x_su = max(float(state.get("X_su", 0.0)), 0.0)
        x_et = max(float(state.get("X_et", 0.0)), 0.0)
        s_h_ion = max(float(state.get("S_H_ion", 1e-7)), 1e-14)
        s_in = max(float(state.get("S_IN", 1e-4)), 1e-12)
        s_h2 = max(float(state.get("S_h2", 0.0)), 1e-12)

        i_ph_aa = (params["K_pH_aa"] ** params["nn_aa"]) / (s_h_ion ** params["nn_aa"] + params["K_pH_aa"] ** params["nn_aa"])
        i_in_lim = 1.0 / (1.0 + params["K_S_IN"] / s_in)
        i_h2_pro = 1.0 / (1.0 + s_h2 / params["K_I_h2_pro"])

        rho1 = float(params["k_et_from_su"]) * s_su / (float(params["K_S_et_su"]) + s_su) * x_su * i_ph_aa * i_in_lim
        rho2 = float(params["k_m_et"]) * s_et / (float(params["K_S_et"]) + s_et) * x_et * i_ph_aa * i_in_lim * i_h2_pro
        rho3 = float(params["k_dec_X_et"]) * x_et

        return {
            "rho_E10_ethanol_from_sugars": rho1,
            "rho_E10_uptake_ethanol": rho2,
            "rho_E10_decay_X_et": rho3,
        }

    def _diagnostics(
        self, matrix: np.ndarray, assembly: FullModelAssembly, params: Mapping[str, float]
    ) -> dict[str, list[float]]:
        s_et = np.clip(matrix[:, assembly.full_state_index["S_et"]], 0.0, None)
        x_et = np.clip(matrix[:, assembly.full_state_index["X_et"]], 0.0, None)
        return {
            "S_et": s_et.astype(float).tolist(),
            "X_et": x_et.astype(float).tolist(),
        }


ETHANOL_EXTENSION = _EthanolExtension()
