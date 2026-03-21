"""E6 — Via do Lactato (Lactate Pathway Extension).

Adds lactate (S_lac) as an explicit soluble substrate and a dedicated
lactate-fermenting acetogen (X_lac) that converts lactate to acetate and H2.

Two lactate sources are modeled:
  1. Sugar overflow: a fraction f_lac_su of rho_5_uptake_sugars products is
     redirected to S_lac instead of the canonical VFA+H2 mix (Satpathy 2016).
     The core rho_5 row scales its VFA terms by (1 - f_lac_su - f_et_su) and
     E6 contributes a stoichiometry_patch adding S_lac to that row.
  2. External feed: S_lac can also be supplied directly via the influent
     (e.g., pre-acidified effluents, silage leachate, dairy waste).

Stoichiometry (per kgCOD substrate):
  Lactate catabolism (COD-conserving):
      S_lac → (1-Y)*f_ac*S_ac + (1-Y)*f_h2*S_h2 + Y*X_lac
      f_ac_lac = 64/96 = 0.6667, f_h2_lac = 32/96 = 0.3333
      (CH3CHOHCOOH → CH3COOH + CO2 + H2)

Kinetic parameters (Satpathy 2016 Parts I/II):
  k_m_lac = 13.0 d⁻¹   — Satpathy Part I Table 3 (citing Hinken et al.)
  K_S_lac = 0.08 kgCOD/m³ — Satpathy Part I Table 3, chemostat at D = 0.002 h⁻¹
  Y_lac   = 0.06 kgCOD/kgCOD — Satpathy Part II Table 2 (full-scale plant)
  k_dec_X_lac = 0.02 d⁻¹  — Batstone 2002 (ADM1 standard)

Reference:
    Satpathy P et al. (2016). "Integration of lactic acid fermentation in the
    anaerobic digestion model No. 1 (ADM1) — Part I: Model development."
    Journal of Environmental Science and Health, Part A 51(13):1103-1114.
    doi:10.1080/10934529.2016.1212558

    Satpathy P et al. (2016). "Integration of lactic acid fermentation in the
    anaerobic digestion model No. 1 (ADM1) — Part II: Validation with pilot-scale data."
    Journal of Environmental Science and Health, Part A 51(13):1115-1125.
    doi:10.1080/10934529.2016.1212559
"""
from __future__ import annotations

from typing import Mapping

import numpy as np

from simulator.full_model.assembly import FullModelAssembly
from simulator.full_model.catalog_types import ParameterDefinition, ProcessDefinition, StateDefinition
from simulator.full_model.extensions import FullModelExtensionContribution
from simulator.full_model.units import DAY_INV, DIMENSIONLESS, KG_COD_M3

_SRC = (
    "Satpathy et al. (2016) J Environ Sci Health Part A 51(13):1103-1114 doi:10.1080/10934529.2016.1212558; "
    "Satpathy et al. (2016) J Environ Sci Health Part A 51(13):1115-1125 doi:10.1080/10934529.2016.1212559"
)


class _LactateExtension:
    name = "lactate"
    description = "E6: lactato como substrato externo com X_lac dedicado para acetogens (Satpathy 2016)."

    def contribute(self) -> FullModelExtensionContribution:
        states = (
            StateDefinition(
                name="S_lac",
                description="Lactato dissolvido (substrato externo, e.g., efluente de pré-acidificação).",
                unit=KG_COD_M3,
                phase="liquid",
                domain="soluble",
                role="dynamic",
                cod_role="cod",
                elemental_proxy="C_su",
                source=_SRC,
                notes="C_lac = C_su = 0.03125 kmolC/kgCOD. Fornecido via alimentação; sem overflow de S_su.",
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
                name="rho_E6_uptake_lactate",
                vendor_symbol="Rho_E6_1",
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
                vendor_symbol="Rho_E6_2",
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
                name="f_lac_su",
                value=0.10,
                unit=DIMENSIONLESS,
                group="stoichiometric",
                classification="provisional",
                description="Fração de overflow de açúcares → lactato (overrides core default 0.0).",
                source=_SRC,
                notes="Satpathy 2016: lactato como produto de overflow da fermentação de açúcares. "
                      "Valor provisional — requer calibração para cada sistema. "
                      "f_lac_su + f_et_su deve ser < 1.0 para manter frações VFA positivas.",
            ),
            ParameterDefinition(
                name="k_m_lac",
                value=13.0,
                unit=DAY_INV,
                group="biochemical",
                classification="calibrated",
                description="Taxa máxima de consumo de lactato por X_lac.",
                source=_SRC,
                notes="Satpathy 2016 Part I Table 3 (citing Hinken et al.): k_m_lac = 13 kgCOD/(kgCOD·d).",
            ),
            ParameterDefinition(
                name="K_S_lac",
                value=0.08,
                unit=KG_COD_M3,
                group="biochemical",
                classification="calibrated",
                description="Meia-saturação para lactato (X_lac).",
                source=_SRC,
                notes="Satpathy 2016 Part I Table 3: K_S_lac = 0.08 kgCOD/m³, determinado em chemostat "
                      "com lactato a D = 0.002 h⁻¹. Part II recalibrou para 0.4202 em planta industrial "
                      "com resíduos alimentares; Part I é mais apropriado para reatores de lodo.",
            ),
            ParameterDefinition(
                name="Y_lac",
                value=0.06,
                unit=DIMENSIONLESS,
                group="stoichiometric",
                classification="calibrated",
                description="Rendimento de biomassa no consumo de lactato.",
                source=_SRC,
                notes="Satpathy 2016 Part II Table 2: Y_lac = 0.06 kgCOD/kgCOD em planta industrial "
                      "(Part I encontrou 0.3176 em chemostat enriquecido, mas 0.06 é mais consistente "
                      "com acetogens estritamente anaeróbios e com a faixa ADM1 para acetogens).",
            ),
            ParameterDefinition(
                name="k_dec_X_lac",
                value=0.02,
                unit=DAY_INV,
                group="biochemical",
                classification="calibrated",
                description="Taxa de decaimento de X_lac.",
                source=_SRC,
                notes="Batstone 2002 (ADM1 standard): k_dec = 0.02 d⁻¹ para acetogens.",
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
        # numerically: 0.03125 - 0.94*0.6667*0.03125 - 0.06*0.03125 ≈ +0.00977 (CO2 released)
        biochemical_stoichiometry_rows = {
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

        # Patch rho_5_uptake_sugars to add S_lac as overflow product of sugar fermentation.
        # The core rho_5 row already scales its VFA terms by (1 - f_lac_su - f_et_su),
        # so adding (1-Y_su)*f_lac_su here maintains exact COD conservation.
        stoichiometry_patches = {
            "rho_5_uptake_sugars": {
                "S_lac": "(1 - Y_su) * f_lac_su",
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
        s_lac = max(float(state.get("S_lac", 0.0)), 0.0)
        x_lac = max(float(state.get("X_lac", 0.0)), 0.0)
        s_h_ion = max(float(state.get("S_H_ion", 1e-7)), 1e-14)
        s_in = max(float(state.get("S_IN", 1e-4)), 1e-12)
        s_h2 = max(float(state.get("S_h2", 0.0)), 1e-12)

        i_ph_aa = (params["K_pH_aa"] ** params["nn_aa"]) / (s_h_ion ** params["nn_aa"] + params["K_pH_aa"] ** params["nn_aa"])
        i_in_lim = 1.0 / (1.0 + params["K_S_IN"] / s_in)
        i_h2_pro = 1.0 / (1.0 + s_h2 / params["K_I_h2_pro"])

        rho_uptake = float(params["k_m_lac"]) * s_lac / (float(params["K_S_lac"]) + s_lac) * x_lac * i_ph_aa * i_in_lim * i_h2_pro
        rho_decay = float(params["k_dec_X_lac"]) * x_lac

        return {
            "rho_E6_uptake_lactate": rho_uptake,
            "rho_E6_decay_X_lac": rho_decay,
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
