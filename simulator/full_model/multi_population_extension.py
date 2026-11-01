"""E12 — Multi-população de Acetoclásticos e Hidrogenotróficos.

Replaces the single acetoclastic (X_ac) and hydrogenotrophic (X_h2) biomass pools
from ADM1 core with two sub-populations each:
  - Population 1: oligotrophic (low k_m, low K_S) — competitive at low substrate
  - Population 2: copiotrophic (high k_m, high K_S) — competitive at high substrate

This extension implements ecological niche partitioning within methanogenic
communities as described by Noguera et al. (1994) and Batstone et al. (2006).
The two-population approach can capture:
  1. Slower response but stability at low acetate from oligotrophs.
  2. Faster kinetics and washout risk from copiotrophs at feast conditions.

States added (replacing X_ac and X_h2 via stoichiometry_patches):
  X_ac_1: oligotrophic acetoclastic methanogens  (kgCOD/m³)
  X_ac_2: copiotrophic acetoclastic methanogens  (kgCOD/m³)
  X_h2_1: oligotrophic hydrogenotrophic methanogens  (kgCOD/m³)
  X_h2_2: copiotrophic hydrogenotrophic methanogens  (kgCOD/m³)

The core uptake and decay rates for X_ac and X_h2 are disabled, so that only
the E12 sub-populations are active for these groups.

Inhibitions applied (consistent with core ADM1):
  Acetoclastic (both populations): I_pH_ac (Hill), I_NH3 (competitive), I_IN_lim
  Hydrogenotrophic (both populations): I_pH_h2 (Hill), I_IN_lim

Kinetic parameter rationale:
  Oligotrophic (pop 1): lower k_m, lower K_S → high affinity, low max rate.
  Copiotrophic (pop 2): higher k_m, higher K_S → low affinity, high max rate.
  This mimics the oligotroph/copiotroph trade-off reported in methanogenic communities.

Reference:
    Noguera DR, Brusseau GA, Rittmann BE, Stahl DA (1994). "A unified model
    describing the role of hydrogen in the growth of Desulfovibrio vulgaris under
    different environmental conditions." Biotechnol Bioeng 44(9):1088–1094.
    doi:10.1002/bit.260440912

    Batstone DJ, Picioreanu C, van Loosdrecht MCM (2006). "Multidimensional
    modelling to investigate interspecies hydrogen transfer in anaerobic biofilms."
    Water Research 40(16):3099–3108. doi:10.1016/j.watres.2006.06.014

    Batstone DJ, Keller J, Angelidaki I et al. (2002). "The IWA Anaerobic Digestion
    Model No 1 (ADM1)." Water Sci Technol 45(10):65–73.
"""
from __future__ import annotations

from typing import Mapping

import numpy as np

from simulator.full_model.assembly import FullModelAssembly
from simulator.full_model.catalog_types import ParameterDefinition, ProcessDefinition, StateDefinition
from simulator.full_model.extensions import FullModelExtensionContribution
from simulator.full_model.units import DAY_INV, DIMENSIONLESS, KG_COD_M3

_SRC = (
    "Noguera et al. (1994) Biotechnol Bioeng 44:1088–1094 doi:10.1002/bit.260440912; "
    "Batstone et al. (2006) Water Res 40:3099–3108 doi:10.1016/j.watres.2006.06.014; "
    "Batstone et al. (2002) ADM1 IWA, Water Sci Technol 45(10):65–73"
)


class _MultiPopulationExtension:
    name = "multi_population"
    description = (
        "E12: dois sub-grupos por função (oligótrofos/copiótrofos) para acetoclásticos "
        "e hidrogenotróficos, substituindo X_ac e X_h2 do núcleo ADM1."
    )

    def contribute(self) -> FullModelExtensionContribution:
        states = (
            StateDefinition(
                name="X_ac_1",
                description="Metanogênicos acetoclásticos oligotróficos (baixo K_S, baixo k_m).",
                unit=KG_COD_M3,
                phase="solid",
                domain="active_biomass",
                role="dynamic",
                cod_role="cod",
                elemental_proxy="C_bac",
                source=_SRC,
                notes="Oligotrophic: competitive at low S_ac. k_m=5 d⁻¹, K_S=0.05 kgCOD/m³.",
            ),
            StateDefinition(
                name="X_ac_2",
                description="Metanogênicos acetoclásticos copiótrofos (alto K_S, alto k_m).",
                unit=KG_COD_M3,
                phase="solid",
                domain="active_biomass",
                role="dynamic",
                cod_role="cod",
                elemental_proxy="C_bac",
                source=_SRC,
                notes="Copiotrophic: competitive at high S_ac. k_m=12 d⁻¹, K_S=0.30 kgCOD/m³.",
            ),
            StateDefinition(
                name="X_h2_1",
                description="Metanogênicos hidrogenotróficos oligotróficos.",
                unit=KG_COD_M3,
                phase="solid",
                domain="active_biomass",
                role="dynamic",
                cod_role="cod",
                elemental_proxy="C_bac",
                source=_SRC,
                notes="Oligotrophic: k_m=20 d⁻¹, K_S=1e-5 kgCOD/m³.",
            ),
            StateDefinition(
                name="X_h2_2",
                description="Metanogênicos hidrogenotróficos copiótrofos.",
                unit=KG_COD_M3,
                phase="solid",
                domain="active_biomass",
                role="dynamic",
                cod_role="cod",
                elemental_proxy="C_bac",
                source=_SRC,
                notes="Copiotrophic: k_m=50 d⁻¹, K_S=5e-5 kgCOD/m³.",
            ),
        )

        processes = (
            # --- Acetoclastic population 1 (oligotrophic) ---
            ProcessDefinition(
                name="rho_E12_uptake_ac_1",
                vendor_symbol="Rho_E12_1",
                family="biochemical",
                description="Consumo de acetato por X_ac_1 (oligótrofos, baixo K_S).",
                rate_expression="computed_by_extension",
                affected_states=("S_ac", "S_IC", "S_IN", "X_ac_1"),
                parameters=("k_m_ac_1", "K_S_ac_1", "Y_ac_mp"),
                inhibitions=("I_pH_ac", "I_NH3", "I_IN_lim"),
                source=_SRC,
            ),
            ProcessDefinition(
                name="rho_E12_decay_ac_1",
                vendor_symbol="Rho_E12_2",
                family="biochemical",
                description="Decaimento de X_ac_1 → X_xc.",
                rate_expression="computed_by_extension",
                affected_states=("X_xc", "X_ac_1", "S_IC", "S_IN"),
                parameters=("k_dec_X_ac_mp",),
                inhibitions=(),
                source=_SRC,
            ),
            # --- Acetoclastic population 2 (copiotrophic) ---
            ProcessDefinition(
                name="rho_E12_uptake_ac_2",
                vendor_symbol="Rho_E12_3",
                family="biochemical",
                description="Consumo de acetato por X_ac_2 (copiótrofos, alto K_S).",
                rate_expression="computed_by_extension",
                affected_states=("S_ac", "S_IC", "S_IN", "X_ac_2"),
                parameters=("k_m_ac_2", "K_S_ac_2", "Y_ac_mp"),
                inhibitions=("I_pH_ac", "I_NH3", "I_IN_lim"),
                source=_SRC,
            ),
            ProcessDefinition(
                name="rho_E12_decay_ac_2",
                vendor_symbol="Rho_E12_4",
                family="biochemical",
                description="Decaimento de X_ac_2 → X_xc.",
                rate_expression="computed_by_extension",
                affected_states=("X_xc", "X_ac_2", "S_IC", "S_IN"),
                parameters=("k_dec_X_ac_mp",),
                inhibitions=(),
                source=_SRC,
            ),
            # --- Hydrogenotrophic population 1 (oligotrophic) ---
            ProcessDefinition(
                name="rho_E12_uptake_h2_1",
                vendor_symbol="Rho_E12_5",
                family="biochemical",
                description="Consumo de H2 por X_h2_1 (oligótrofos).",
                rate_expression="computed_by_extension",
                affected_states=("S_h2", "S_IC", "S_IN", "X_h2_1"),
                parameters=("k_m_h2_1", "K_S_h2_1", "Y_h2_mp"),
                inhibitions=("I_pH_h2", "I_IN_lim"),
                source=_SRC,
            ),
            ProcessDefinition(
                name="rho_E12_decay_h2_1",
                vendor_symbol="Rho_E12_6",
                family="biochemical",
                description="Decaimento de X_h2_1 → X_xc.",
                rate_expression="computed_by_extension",
                affected_states=("X_xc", "X_h2_1", "S_IC", "S_IN"),
                parameters=("k_dec_X_h2_mp",),
                inhibitions=(),
                source=_SRC,
            ),
            # --- Hydrogenotrophic population 2 (copiotrophic) ---
            ProcessDefinition(
                name="rho_E12_uptake_h2_2",
                vendor_symbol="Rho_E12_7",
                family="biochemical",
                description="Consumo de H2 por X_h2_2 (copiótrofos).",
                rate_expression="computed_by_extension",
                affected_states=("S_h2", "S_IC", "S_IN", "X_h2_2"),
                parameters=("k_m_h2_2", "K_S_h2_2", "Y_h2_mp"),
                inhibitions=("I_pH_h2", "I_IN_lim"),
                source=_SRC,
            ),
            ProcessDefinition(
                name="rho_E12_decay_h2_2",
                vendor_symbol="Rho_E12_8",
                family="biochemical",
                description="Decaimento de X_h2_2 → X_xc.",
                rate_expression="computed_by_extension",
                affected_states=("X_xc", "X_h2_2", "S_IC", "S_IN"),
                parameters=("k_dec_X_h2_mp",),
                inhibitions=(),
                source=_SRC,
            ),
        )

        parameters = (
            # --- Oligotrophic acetoclastic parameters ---
            ParameterDefinition(
                name="k_m_ac_1",
                value=5.0,
                unit=DAY_INV,
                group="biochemical",
                classification="calibrated",
                description="Taxa máxima de consumo de acetato por X_ac_1 (oligótrofa).",
                source=_SRC,
                notes="Lower than core k_m_ac=8 d⁻¹. Oligotroph: slower max rate, higher affinity.",
            ),
            ParameterDefinition(
                name="K_S_ac_1",
                value=0.05,
                unit=KG_COD_M3,
                group="biochemical",
                classification="calibrated",
                description="Meia-saturação de acetato para X_ac_1 (oligótrofa, baixo K_S).",
                source=_SRC,
                notes="Lower than core K_S_ac=0.15. Oligotroph strategy: high affinity at low S_ac.",
            ),
            # --- Copiotrophic acetoclastic parameters ---
            ParameterDefinition(
                name="k_m_ac_2",
                value=12.0,
                unit=DAY_INV,
                group="biochemical",
                classification="calibrated",
                description="Taxa máxima de consumo de acetato por X_ac_2 (copiótrofa).",
                source=_SRC,
                notes="Higher than core k_m_ac=8 d⁻¹. Copiotroph: fast max rate at high S_ac.",
            ),
            ParameterDefinition(
                name="K_S_ac_2",
                value=0.30,
                unit=KG_COD_M3,
                group="biochemical",
                classification="calibrated",
                description="Meia-saturação de acetato para X_ac_2 (copiótrofa, alto K_S).",
                source=_SRC,
                notes="Higher than core K_S_ac=0.15. Copiotroph: lower affinity but faster growth.",
            ),
            # --- Oligotrophic hydrogenotrophic parameters ---
            ParameterDefinition(
                name="k_m_h2_1",
                value=20.0,
                unit=DAY_INV,
                group="biochemical",
                classification="calibrated",
                description="Taxa máxima de consumo de H2 por X_h2_1 (oligótrofa).",
                source=_SRC,
                notes="Lower than core k_m_h2=35 d⁻¹. High-affinity H2 utilizers.",
            ),
            ParameterDefinition(
                name="K_S_h2_1",
                value=1.0e-5,
                unit=KG_COD_M3,
                group="biochemical",
                classification="calibrated",
                description="Meia-saturação de H2 para X_h2_1 (oligótrofa).",
                source=_SRC,
                notes="Lower than core K_S_h2=7e-6 kgCOD/m³ — similar but slightly higher affinity.",
            ),
            # --- Copiotrophic hydrogenotrophic parameters ---
            ParameterDefinition(
                name="k_m_h2_2",
                value=50.0,
                unit=DAY_INV,
                group="biochemical",
                classification="calibrated",
                description="Taxa máxima de consumo de H2 por X_h2_2 (copiótrofa).",
                source=_SRC,
                notes="Higher than core k_m_h2=35 d⁻¹. Fast H2 consumers in burst conditions.",
            ),
            ParameterDefinition(
                name="K_S_h2_2",
                value=5.0e-5,
                unit=KG_COD_M3,
                group="biochemical",
                classification="calibrated",
                description="Meia-saturação de H2 para X_h2_2 (copiótrofa).",
                source=_SRC,
                notes="Higher K_S than X_h2_1. Copiotroph: active only at higher H2 concentrations.",
            ),
            # --- Shared yield and decay ---
            ParameterDefinition(
                name="Y_ac_mp",
                value=0.05,
                unit=DIMENSIONLESS,
                group="stoichiometric",
                classification="canonical",
                description="Rendimento de biomassa acetoclástica multi-população (igual ao núcleo Y_ac).",
                source=_SRC,
                notes="Same as ADM1 core Y_ac = 0.05. Used for both X_ac_1 and X_ac_2.",
            ),
            ParameterDefinition(
                name="Y_h2_mp",
                value=0.06,
                unit=DIMENSIONLESS,
                group="stoichiometric",
                classification="canonical",
                description="Rendimento de biomassa hidrogenotrófica multi-população (igual ao núcleo Y_h2).",
                source=_SRC,
                notes="Same as ADM1 core Y_h2 = 0.06. Used for both X_h2_1 and X_h2_2.",
            ),
            ParameterDefinition(
                name="k_dec_X_ac_mp",
                value=0.02,
                unit=DAY_INV,
                group="biochemical",
                classification="canonical",
                description="Taxa de decaimento dos acetoclásticos multi-população.",
                source=_SRC,
                notes="Same as core k_dec_X_ac = 0.02 d⁻¹ (Batstone 2002).",
            ),
            ParameterDefinition(
                name="k_dec_X_h2_mp",
                value=0.02,
                unit=DAY_INV,
                group="biochemical",
                classification="canonical",
                description="Taxa de decaimento dos hidrogenotróficos multi-população.",
                source=_SRC,
                notes="Same as core k_dec_X_h2 = 0.02 d⁻¹ (Batstone 2002).",
            ),
        )

        # Stoichiometry for acetoclastic uptake (matches rho_11 structure):
        # S_ac: -1 (consumed)
        # S_ch4: (1 - Y_ac_mp) (produced)
        # S_IC: -s_11 = -(−C_ac + (1-Y_ac)*C_ch4 + Y_ac*C_bac) = C_ac - (1-Y)*C_ch4 - Y*C_bac
        # S_IN: -Y_ac_mp * N_bac
        # X_ac_1 or X_ac_2: Y_ac_mp
        biochemical_stoichiometry_rows = {
            "rho_E12_uptake_ac_1": {
                "S_ac": "-1",
                "S_ch4": "1 - Y_ac_mp",
                "S_IC": "C_ac - (1 - Y_ac_mp) * C_ch4 - Y_ac_mp * C_bac",
                "S_IN": "-Y_ac_mp * N_bac",
                "X_ac_1": "Y_ac_mp",
            },
            "rho_E12_decay_ac_1": {
                "X_xc": "1",
                "X_ac_1": "-1",
                "S_IC": "-s_13",
                "S_IN": "N_bac - N_xc",
            },
            "rho_E12_uptake_ac_2": {
                "S_ac": "-1",
                "S_ch4": "1 - Y_ac_mp",
                "S_IC": "C_ac - (1 - Y_ac_mp) * C_ch4 - Y_ac_mp * C_bac",
                "S_IN": "-Y_ac_mp * N_bac",
                "X_ac_2": "Y_ac_mp",
            },
            "rho_E12_decay_ac_2": {
                "X_xc": "1",
                "X_ac_2": "-1",
                "S_IC": "-s_13",
                "S_IN": "N_bac - N_xc",
            },
            # Stoichiometry for hydrogenotrophic uptake (matches rho_12 structure):
            # S_h2: -1 (consumed)
            # S_ch4: (1 - Y_h2_mp) (produced)
            # S_IC: -s_12 = -(+( 1-Y_h2)*C_ch4 + Y_h2*C_bac) = -(1-Y_h2)*C_ch4 - Y_h2*C_bac
            # Note s_12 = "(1 - Y_h2) * C_ch4 + Y_h2 * C_bac" so -s_12 is negative of that
            "rho_E12_uptake_h2_1": {
                "S_h2": "-1",
                "S_ch4": "1 - Y_h2_mp",
                "S_IC": "-((1 - Y_h2_mp) * C_ch4 + Y_h2_mp * C_bac)",
                "S_IN": "-Y_h2_mp * N_bac",
                "X_h2_1": "Y_h2_mp",
            },
            "rho_E12_decay_h2_1": {
                "X_xc": "1",
                "X_h2_1": "-1",
                "S_IC": "-s_13",
                "S_IN": "N_bac - N_xc",
            },
            "rho_E12_uptake_h2_2": {
                "S_h2": "-1",
                "S_ch4": "1 - Y_h2_mp",
                "S_IC": "-((1 - Y_h2_mp) * C_ch4 + Y_h2_mp * C_bac)",
                "S_IN": "-Y_h2_mp * N_bac",
                "X_h2_2": "Y_h2_mp",
            },
            "rho_E12_decay_h2_2": {
                "X_xc": "1",
                "X_h2_2": "-1",
                "S_IC": "-s_13",
                "S_IN": "N_bac - N_xc",
            },
        }

        # Core rates are disabled by the base-rate modifier below.
        stoichiometry_patches = {
            "rho_11_uptake_acetate": {"X_ac": "0"},
            "rho_12_uptake_hydrogen": {"X_h2": "0"},
            "rho_18_decay_acetate_biomass": {"X_ac": "0"},
            "rho_19_decay_hydrogen_biomass": {"X_h2": "0"},
        }

        return FullModelExtensionContribution(
            states=states,
            processes=processes,
            parameters=parameters,
            biochemical_stoichiometry_rows=biochemical_stoichiometry_rows,
            stoichiometry_patches=stoichiometry_patches,
            rate_function=self._rates,
            diagnostics_hook=self._diagnostics,
            base_rate_modifier_hook=self._disable_core_rates,
            inhibition_hook=self._inhibition,
        )

    def _disable_core_rates(self, state: Mapping[str, float], params: Mapping[str, float]) -> dict[str, float]:
        return {name: 0.0 for name in (
            "rho_11_uptake_acetate", "rho_12_uptake_hydrogen",
            "rho_18_decay_acetate_biomass", "rho_19_decay_hydrogen_biomass",
        )}

    def _inhibition(self, state: Mapping[str, float], params: Mapping[str, float]) -> dict[str, float]:
        # The core methanogenesis processes are disabled, so every other
        # extension's factor on them must be forwarded to the replacement
        # sub-populations (one common core -> replacement mapping).
        from simulator.full_model.phenolics_extension import PHENOLICS_EXTENSION
        from simulator.full_model.srb_extension import SRB_EXTENSION
        from simulator.full_model.syngas_extension import SYNGAS_EXTENSION
        from simulator.full_model.trace_elements_extension import TRACE_ELEMENTS_EXTENSION

        replacements = {
            "rho_11_uptake_acetate": ("rho_E12_uptake_ac_1", "rho_E12_uptake_ac_2"),
            "rho_12_uptake_hydrogen": ("rho_E12_uptake_h2_1", "rho_E12_uptake_h2_2"),
        }
        result = {name: 1.0 for names in replacements.values() for name in names}
        for marker, extension in (("K_I_phen", PHENOLICS_EXTENSION),
                                  ("K_I_CO", SYNGAS_EXTENSION),
                                  ("K_I_H2S", SRB_EXTENSION),
                                  ("K_TE_Ni_ac", TRACE_ELEMENTS_EXTENSION)):
            if marker in params:
                factors = extension._inhibition(state, params)
                for core_name, targets in replacements.items():
                    for target in targets:
                        result[target] *= factors.get(core_name, 1.0)
        return result

    def _rates(
        self, state: Mapping[str, float], params: Mapping[str, float]
    ) -> dict[str, float]:
        s_ac = max(float(state.get("S_ac", 0.0)), 0.0)
        s_h2 = max(float(state.get("S_h2", 0.0)), 1e-15)
        x_ac_1 = max(float(state.get("X_ac_1", 0.0)), 0.0)
        x_ac_2 = max(float(state.get("X_ac_2", 0.0)), 0.0)
        x_h2_1 = max(float(state.get("X_h2_1", 0.0)), 0.0)
        x_h2_2 = max(float(state.get("X_h2_2", 0.0)), 0.0)
        s_h_ion = max(float(state.get("S_H_ion", 1e-7)), 1e-14)
        s_nh3 = max(float(state.get("S_nh3", 0.0)), 0.0)
        s_in = max(float(state.get("S_IN", 1e-4)), 1e-12)

        # pH inhibition for acetoclastic methanogens (same Hill function as core I_11)
        k_ph_ac = float(params["K_pH_ac"])
        n_ac = float(params["n_ac"])
        i_ph_ac = (k_ph_ac ** n_ac) / (s_h_ion ** n_ac + k_ph_ac ** n_ac)

        # NH3 inhibition on acetoclastic methanogens (same as core)
        i_nh3 = float(params["K_I_nh3"]) / (float(params["K_I_nh3"]) + s_nh3)

        # Inorganic nitrogen limitation (same as core I_IN_lim)
        i_in_lim = 1.0 / (1.0 + float(params["K_S_IN"]) / s_in)

        # Combined inhibition for acetoclastic populations
        i_11 = i_ph_ac * i_nh3 * i_in_lim

        # pH inhibition for hydrogenotrophic methanogens (same Hill function as core I_12)
        k_ph_h2 = float(params["K_pH_h2"])
        n_h2 = float(params["n_h2"])
        i_ph_h2 = (k_ph_h2 ** n_h2) / (s_h_ion ** n_h2 + k_ph_h2 ** n_h2)

        # Combined inhibition for hydrogenotrophic populations
        i_12 = i_ph_h2 * i_in_lim

        return {
            "rho_E12_uptake_ac_1": (
                float(params["k_m_ac_1"])
                * s_ac / (float(params["K_S_ac_1"]) + s_ac)
                * x_ac_1 * i_11
            ),
            "rho_E12_decay_ac_1": float(params["k_dec_X_ac_mp"]) * x_ac_1,
            "rho_E12_uptake_ac_2": (
                float(params["k_m_ac_2"])
                * s_ac / (float(params["K_S_ac_2"]) + s_ac)
                * x_ac_2 * i_11
            ),
            "rho_E12_decay_ac_2": float(params["k_dec_X_ac_mp"]) * x_ac_2,
            "rho_E12_uptake_h2_1": (
                float(params["k_m_h2_1"])
                * s_h2 / (float(params["K_S_h2_1"]) + s_h2)
                * x_h2_1 * i_12
            ),
            "rho_E12_decay_h2_1": float(params["k_dec_X_h2_mp"]) * x_h2_1,
            "rho_E12_uptake_h2_2": (
                float(params["k_m_h2_2"])
                * s_h2 / (float(params["K_S_h2_2"]) + s_h2)
                * x_h2_2 * i_12
            ),
            "rho_E12_decay_h2_2": float(params["k_dec_X_h2_mp"]) * x_h2_2,
        }

    def _diagnostics(
        self,
        matrix: np.ndarray,
        assembly: FullModelAssembly,
        params: Mapping[str, float],
    ) -> dict[str, list[float]]:
        x_ac_1 = np.clip(matrix[:, assembly.full_state_index["X_ac_1"]], 0.0, None)
        x_ac_2 = np.clip(matrix[:, assembly.full_state_index["X_ac_2"]], 0.0, None)
        x_h2_1 = np.clip(matrix[:, assembly.full_state_index["X_h2_1"]], 0.0, None)
        x_h2_2 = np.clip(matrix[:, assembly.full_state_index["X_h2_2"]], 0.0, None)

        total_x_ac = x_ac_1 + x_ac_2
        total_x_h2 = x_h2_1 + x_h2_2
        frac_olig_ac = x_ac_1 / np.maximum(total_x_ac, 1e-9)
        frac_olig_h2 = x_h2_1 / np.maximum(total_x_h2, 1e-9)

        return {
            "X_ac_1": x_ac_1.astype(float).tolist(),
            "X_ac_2": x_ac_2.astype(float).tolist(),
            "X_h2_1": x_h2_1.astype(float).tolist(),
            "X_h2_2": x_h2_2.astype(float).tolist(),
            "total_X_ac": total_x_ac.astype(float).tolist(),
            "total_X_h2": total_x_h2.astype(float).tolist(),
            "fraction_oligotrophic_ac": frac_olig_ac.astype(float).tolist(),
            "fraction_oligotrophic_h2": frac_olig_h2.astype(float).tolist(),
        }


MULTI_POPULATION_EXTENSION = _MultiPopulationExtension()
