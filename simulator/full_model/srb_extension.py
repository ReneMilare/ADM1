"""E4 — Redução de Sulfato por Bactérias SRB (Sulfate-Reducing Bacteria Extension).

Adds sulfate reduction to the ADM1 framework, introducing competing pathways
where SRB compete with acetogens and methanogens for H2 and acetate.

States:
    S_SO4   (kmol/m³): Dissolved sulfate, limiting substrate for SRB
    S_H2S   (kmolS/m³): Total dissolved sulfide (H2S + HS⁻), produced by SRB
    X_SRB_ac (kgCOD/m³): SRB acetate-oxidizers (Desulfobacter group)
    X_SRB_h2 (kgCOD/m³): SRB H2-oxidizers (Desulfovibrio group)

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

H2S stripping (simplified, first-order):
    The gas-phase H2S state is not added (extension gas states don't receive gas
    dynamics from rhs.py). Instead, stripping is modeled as a first-order loss
    from S_H2S with rate constant k_La_H2S, representing the mass transfer to
    the gas phase.

H2S inhibition (v1 limitation):
    H2S inhibits methanogenesis (rho_11, rho_12). Direct modification of core
    process rates requires changes to kinetics.py, which is outside the extension
    architecture in this version. The competitive effect on S_h2 and S_ac
    (substrates consumed by SRB instead of methanogens) provides indirect inhibition.

Reference:
    Fedorovich et al. (2003). "Model for anaerobic wastewater treatment with
    simultaneous sulfate reduction." Water Science and Technology 48(6):137-144.
    Barrera et al. (2015). "Importance of sulfate reduction in an upflow anaerobic
    sludge bed (UASB) reactor treating sulfate-rich wastewater from the fish
    canning industry." Chemical Engineering Journal 277:146-154.
    doi:10.1016/j.cej.2015.04.083
"""
from __future__ import annotations

from typing import Mapping

import numpy as np

from simulator.full_model.assembly import FullModelAssembly
from simulator.full_model.catalog_types import ParameterDefinition, ProcessDefinition, StateDefinition
from simulator.full_model.extensions import FullModelExtensionContribution
from simulator.full_model.units import DAY_INV, DIMENSIONLESS, KG_COD_M3, KMOL_S_M3

_SRC = "Fedorovich et al. (2003) WST 48(6):137-144; Barrera et al. (2015) doi:10.1016/j.cej.2015.04.083"
_KMOL_M3 = "kmol/m3"


class _SRBExtension:
    name = "srb"
    description = "E4: redução de sulfato por bactérias SRB competindo com metanogênese (Fedorovich 2003)."

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
                      "v1: no S_gas_H2S state; stripping modeled as first-order loss k_La_H2S.",
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
                name="rho_E4_H2S_stripping",
                vendor_symbol="Rho_E4_5",
                family="biochemical",
                description="Stripping simplificado de H2S da fase líquida (first-order loss).",
                rate_expression="computed_by_extension",
                affected_states=("S_H2S",),
                parameters=("k_La_H2S",),
                inhibitions=(),
                source=_SRC,
                notes="v1: first-order loss approximating gas stripping. No S_gas_H2S state. "
                      "H2S_eq from Henry's law not applied (k_La_H2S is net loss rate).",
            ),
        )

        parameters = (
            ParameterDefinition(
                name="k_m_SRB_ac",
                value=0.25,
                unit=DAY_INV,
                group="biochemical",
                classification="provisional",
                description="Taxa máxima de consumo de acetato por X_SRB_ac.",
                source=_SRC,
                notes="Fedorovich 2003 Table 1.",
            ),
            ParameterDefinition(
                name="K_S_SRB_ac",
                value=0.10,
                unit=KG_COD_M3,
                group="biochemical",
                classification="provisional",
                description="Meia-saturação para acetato (X_SRB_ac).",
                source=_SRC,
            ),
            ParameterDefinition(
                name="K_S_SO4_ac",
                value=0.005,
                unit=_KMOL_M3,
                group="biochemical",
                classification="provisional",
                description="Meia-saturação para sulfato na oxidação de acetato (kmol/m³).",
                source=_SRC,
                notes="≈ 0.48 g SO4/L; typical for acetate-oxidizing SRB.",
            ),
            ParameterDefinition(
                name="Y_SRB_ac",
                value=0.04,
                unit=DIMENSIONLESS,
                group="stoichiometric",
                classification="provisional",
                description="Rendimento de biomassa de SRB_ac (gCOD_X / gCOD_ac).",
                source=_SRC,
                notes="SRB have lower yield than acetogens due to less energy per mol SO4.",
            ),
            ParameterDefinition(
                name="k_m_SRB_h2",
                value=0.30,
                unit=DAY_INV,
                group="biochemical",
                classification="provisional",
                description="Taxa máxima de consumo de H2 por X_SRB_h2.",
                source=_SRC,
            ),
            ParameterDefinition(
                name="K_S_SRB_h2",
                value=7e-6,
                unit=KG_COD_M3,
                group="biochemical",
                classification="provisional",
                description="Meia-saturação para H2 em SRB_h2 (kgCOD/m³).",
                source=_SRC,
                notes="7×10⁻⁶ kgCOD/m³ ≈ 3.5 µM H2 (similar to hydrogenotrophic methanogens).",
            ),
            ParameterDefinition(
                name="K_S_SO4_h2",
                value=0.002,
                unit=_KMOL_M3,
                group="biochemical",
                classification="provisional",
                description="Meia-saturação para sulfato na oxidação de H2 (kmol/m³).",
                source=_SRC,
            ),
            ParameterDefinition(
                name="Y_SRB_h2",
                value=0.05,
                unit=DIMENSIONLESS,
                group="stoichiometric",
                classification="provisional",
                description="Rendimento de biomassa de SRB_h2 (gCOD_X / gCOD_H2).",
                source=_SRC,
            ),
            ParameterDefinition(
                name="k_dec_X_SRB_ac",
                value=0.02,
                unit=DAY_INV,
                group="biochemical",
                classification="provisional",
                description="Taxa de decaimento de X_SRB_ac.",
                source=_SRC,
            ),
            ParameterDefinition(
                name="k_dec_X_SRB_h2",
                value=0.02,
                unit=DAY_INV,
                group="biochemical",
                classification="provisional",
                description="Taxa de decaimento de X_SRB_h2.",
                source=_SRC,
            ),
            ParameterDefinition(
                name="K_I_H2S",
                value=0.01,
                unit=KMOL_S_M3,
                group="biochemical",
                classification="provisional",
                description="Constante de inibição de H2S sobre metanogênese (kmolS/m³).",
                source=_SRC,
                notes="≈ 0.34 g S/L ≈ 0.01 M dissolved H2S. Fedorovich 2003. "
                      "v1 limitation: not applied to core rho_11/rho_12 (requires kinetics.py modification).",
            ),
            ParameterDefinition(
                name="k_La_H2S",
                value=0.5,
                unit=DAY_INV,
                group="physicochemical",
                classification="provisional",
                description="Coeficiente de transferência de massa de H2S para a fase gasosa (d⁻¹).",
                source=_SRC,
                notes="Net first-order stripping coefficient. Not a Henry's law implementation. "
                      "Effective k_La may range 0.1–2.0 d⁻¹ depending on mixing and headspace.",
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
        #     1 kgCOD H2 = 1000/(2*2) = 250 mol H2 (H2 + 0.5O2; MW_O2=32 → 2gCOD/mol)
        #     Wait: 1 mol H2 = 2 gH2, COD = O2_consumed = 2*32/2 = 16 g? No:
        #     H2 + 0.5 O2 → H2O; gCOD/mol = 0.5 * 32 = 16 gO2/mol H2
        #     So 1 kgCOD H2 = 1000/16 = 62.5 mol H2
        #     4H2 reduces 1 mol SO4 → 62.5/4 = 15.625 mol SO4/kgCOD H2 catabolized
        #     ΔS_SO4 = -(1-Y_SRB_h2) * 15.625 / 1000 = -(1-Y_SRB_h2) / 64  kmol/kgCOD
        #   S_IC = 0 for H2 (no C in H2); but S_IN = -Y*N_bac (biomass needs N)
        #
        # H2S_stripping: direct first-order loss from S_H2S (not COD-based)
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
            "rho_E4_H2S_stripping": {
                # H2S stripping: S_H2S decreases but no other state changes
                # (in reality H2S enters gas phase, but we don't have S_gas_H2S)
                "S_H2S": "-1",
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
        s_ac = max(float(state.get("S_ac", 0.0)), 0.0)
        s_h2 = max(float(state.get("S_h2", 0.0)), 1e-12)
        s_so4 = max(float(state.get("S_SO4", 0.0)), 0.0)
        s_h2s = max(float(state.get("S_H2S", 0.0)), 0.0)
        x_srb_ac = max(float(state.get("X_SRB_ac", 0.0)), 0.0)
        x_srb_h2 = max(float(state.get("X_SRB_h2", 0.0)), 0.0)
        s_h_ion = max(float(state.get("S_H_ion", 1e-7)), 1e-14)
        s_in = max(float(state.get("S_IN", 1e-4)), 1e-12)

        # pH inhibitions (use acetate pH limits for SRB_ac, H2-type for SRB_h2)
        i_ph_ac = (params["K_pH_ac"] ** params["n_ac"]) / (s_h_ion ** params["n_ac"] + params["K_pH_ac"] ** params["n_ac"])
        i_ph_h2 = (params["K_pH_h2"] ** params["n_h2"]) / (s_h_ion ** params["n_h2"] + params["K_pH_h2"] ** params["n_h2"])
        i_in_lim = 1.0 / (1.0 + params["K_S_IN"] / s_in)

        # Sulfate limitation (dual Monod: substrate × SO4)
        k_so4_ac = float(params["K_S_SO4_ac"])
        k_so4_h2 = float(params["K_S_SO4_h2"])
        i_so4_ac = s_so4 / (k_so4_ac + s_so4)
        i_so4_h2 = s_so4 / (k_so4_h2 + s_so4)

        # H2S inhibition on SRB themselves (feedback)
        k_i_h2s = float(params.get("K_I_H2S", 0.01))
        i_h2s = k_i_h2s / (k_i_h2s + s_h2s)

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
        rho_dec_srb_ac = float(params["k_dec_X_SRB_ac"]) * x_srb_ac
        rho_dec_srb_h2 = float(params["k_dec_X_SRB_h2"]) * x_srb_h2
        rho_strip = float(params["k_La_H2S"]) * s_h2s

        return {
            "rho_E4_SRB_uptake_ac": rho_srb_ac,
            "rho_E4_SRB_uptake_h2": rho_srb_h2,
            "rho_E4_decay_X_SRB_ac": rho_dec_srb_ac,
            "rho_E4_decay_X_SRB_h2": rho_dec_srb_h2,
            "rho_E4_H2S_stripping": rho_strip,
        }

    def _diagnostics(
        self, matrix: np.ndarray, assembly: FullModelAssembly, params: Mapping[str, float]
    ) -> dict[str, list[float]]:
        s_so4 = np.clip(matrix[:, assembly.full_state_index["S_SO4"]], 0.0, None)
        s_h2s = np.clip(matrix[:, assembly.full_state_index["S_H2S"]], 0.0, None)
        x_srb_ac = np.clip(matrix[:, assembly.full_state_index["X_SRB_ac"]], 0.0, None)
        x_srb_h2 = np.clip(matrix[:, assembly.full_state_index["X_SRB_h2"]], 0.0, None)
        return {
            "S_SO4": s_so4.astype(float).tolist(),
            "S_H2S": s_h2s.astype(float).tolist(),
            "X_SRB_ac": x_srb_ac.astype(float).tolist(),
            "X_SRB_h2": x_srb_h2.astype(float).tolist(),
        }


SRB_EXTENSION = _SRBExtension()
