"""E10 — Via do Etanol (Ethanol Pathway Extension).

Adds ethanol (S_et) as an explicit soluble substrate and a dedicated
ethanol-oxidizing acetogen (X_et) that converts ethanol to acetate and H2.

Two ethanol sources are modeled:
  1. Sugar overflow: a fraction f_et_su of rho_5_uptake_sugars products is
     redirected to S_et instead of the canonical VFA+H2 mix (García-Gen 2013).
     The core rho_5 row scales its VFA terms by (1 - f_lac_su - f_et_su) and
     E10 contributes a stoichiometry_patch adding S_et to that row.
  2. External feed: S_et can also be supplied directly via the influent
     (e.g., fermentation effluents with residual ethanol).

Stoichiometry (per kgCOD substrate):
  Ethanol catabolism (COD-conserving):
      S_et → (1-Y)*f_ac*S_ac + (1-Y)*f_h2*S_h2 + Y*X_et
      Reaction: C2H5OH + H2O → CH3COOH + 2 H2
        Ethanol COD = 96 gO2/mol (C2H5OH + 3 O2 → 2 CO2 + 3 H2O)
        Acetate COD  = 64 gO2/mol → f_ac_et = 64/96 = 0.6667
        H2 COD       = 32 gO2/mol → f_h2_et = 32/96 = 0.3333
      Carbon content: C_et = 2/96 = 0.02083 kmolC/kgCOD
        (2 mol C per mol C2H5OH, MW_COD = 96 gO2/mol)

Kinetic parameters (García-Gen 2013 / Batstone 2004):
  k_m_et  = 3.0 d⁻¹    — García-Gen 2013 Table 4, citing Batstone 2004 (COD basis)
  K_S_et  = 0.50 kgCOD/m³ — García-Gen 2013 Table 4, citing Batstone 2004 (COD basis)
  Y_et    = 0.05 kgCOD/kgCOD — yield consistent with ADM1 acetogen range (0.04–0.06)
  k_dec_X_et = 0.02 d⁻¹ — Batstone 2002 (ADM1 standard)

Reference:
    García-Gen S et al. (2013). "Generalised model for food waste interconversion
    kinetics during anaerobic digestion." Bioresource Technology 147:525-533.
    doi:10.1016/j.biortech.2013.08.063
"""
from __future__ import annotations

from typing import Mapping

import numpy as np

from simulator.full_model.assembly import FullModelAssembly
from simulator.full_model.catalog_types import ParameterDefinition, ProcessDefinition, StateDefinition
from simulator.full_model.extensions import FullModelExtensionContribution
from simulator.full_model.units import DAY_INV, DIMENSIONLESS, KG_COD_M3

_SRC = "García-Gen et al. (2013) Bioresource Technology 147:525-533 doi:10.1016/j.biortech.2013.08.063"


class _EthanolExtension:
    name = "ethanol"
    description = "E10: etanol como substrato externo com X_et dedicado para acetogens oxidadores (García-Gen 2013)."

    def contribute(self) -> FullModelExtensionContribution:
        states = (
            StateDefinition(
                name="S_et",
                description="Etanol dissolvido (substrato externo, e.g., efluentes de fermentação).",
                unit=KG_COD_M3,
                phase="liquid",
                domain="soluble",
                role="dynamic",
                cod_role="cod",
                elemental_proxy=None,
                source=_SRC,
                notes="C_et = 2/96 = 0.02083 kmolC/kgCOD. Fornecido via alimentação; sem overflow de S_su.",
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
                name="rho_E10_uptake_ethanol",
                vendor_symbol="Rho_E10_1",
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
                vendor_symbol="Rho_E10_2",
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
                name="f_et_su",
                value=0.05,
                unit=DIMENSIONLESS,
                group="stoichiometric",
                classification="provisional",
                description="Fração de overflow de açúcares → etanol (overrides core default 0.0).",
                source=_SRC,
                notes="García-Gen 2013: etanol como produto de overflow da fermentação de açúcares. "
                      "Valor provisional — requer calibração para cada sistema. "
                      "f_lac_su + f_et_su deve ser < 1.0 para manter frações VFA positivas.",
            ),
            ParameterDefinition(
                name="k_m_et",
                value=3.0,
                unit=DAY_INV,
                group="biochemical",
                classification="calibrated",
                description="Taxa máxima de consumo de etanol por X_et.",
                source=_SRC,
                notes="García-Gen 2013 Table 4, citando Batstone 2004: k_m_et = 3 kgCOD/(kgCOD·d) "
                      "em base COD. García-Gen expressa em unidades molares (0.0438 mol/(C·mol·h)); "
                      "o valor em base COD é o referenciado em Batstone (2004).",
            ),
            ParameterDefinition(
                name="K_S_et",
                value=0.5,
                unit=KG_COD_M3,
                group="biochemical",
                classification="calibrated",
                description="Meia-saturação para etanol (X_et).",
                source=_SRC,
                notes="García-Gen 2013 Table 4, citando Batstone 2004: K_s_et = 0.5 kgCOD/m³ "
                      "em base COD.",
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
                classification="calibrated",
                description="Taxa de decaimento de X_et.",
                source=_SRC,
                notes="Batstone 2002 (ADM1 standard): k_dec = 0.02 d⁻¹ para acetogens.",
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

        # S_IC for uptake: C_et - (1-Y)*f_ac_et*C_ac - Y*C_bac
        #   = 0.02083 - 0.95*0.6667*0.03125 - 0.05*0.03125
        #   = 0.02083 - 0.01979 - 0.00156 = -0.000525 → tiny S_IC decrease (C-poor substrate)
        biochemical_stoichiometry_rows = {
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

        # Patch rho_5_uptake_sugars to add S_et as overflow product of sugar fermentation.
        # The core rho_5 row already scales its VFA terms by (1 - f_lac_su - f_et_su),
        # so adding (1-Y_su)*f_et_su here maintains exact COD conservation.
        stoichiometry_patches = {
            "rho_5_uptake_sugars": {
                "S_et": "(1 - Y_su) * f_et_su",
            },
        }

        return FullModelExtensionContribution(
            states=states,
            processes=processes,
            parameters=parameters,
            biochemical_stoichiometry_rows=biochemical_stoichiometry_rows,
            stoichiometry_patches=stoichiometry_patches,
            rate_function=self._rates,
            diagnostics_hook=self._diagnostics,
        )

    def _rates(self, state: Mapping[str, float], params: Mapping[str, float]) -> dict[str, float]:
        s_et = max(float(state.get("S_et", 0.0)), 0.0)
        x_et = max(float(state.get("X_et", 0.0)), 0.0)
        s_h_ion = max(float(state.get("S_H_ion", 1e-7)), 1e-14)
        s_in = max(float(state.get("S_IN", 1e-4)), 1e-12)
        s_h2 = max(float(state.get("S_h2", 0.0)), 1e-12)

        i_ph_aa = (params["K_pH_aa"] ** params["nn_aa"]) / (s_h_ion ** params["nn_aa"] + params["K_pH_aa"] ** params["nn_aa"])
        i_in_lim = 1.0 / (1.0 + params["K_S_IN"] / s_in)
        i_h2_pro = 1.0 / (1.0 + s_h2 / params["K_I_h2_pro"])

        rho_uptake = float(params["k_m_et"]) * s_et / (float(params["K_S_et"]) + s_et) * x_et * i_ph_aa * i_in_lim * i_h2_pro
        rho_decay = float(params["k_dec_X_et"]) * x_et

        return {
            "rho_E10_uptake_ethanol": rho_uptake,
            "rho_E10_decay_X_et": rho_decay,
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
