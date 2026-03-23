"""E20 — Digestão Anaeróbia de Microalgas (Microalgae Extension).

Represents the anaerobic digestion of microalgae in the ADM1 framework by
introducing a dedicated algal particulate composite (X_alg) that disintegrates
with a reduced rate due to cell-wall recalcitrance. Products follow algae-
specific fractionation, which typically has higher protein content (and therefore
more nitrogen release) than municipal sludge.

Design approach (Mairet et al. 2011, Batstone 2002):
  - X_alg is a new composite particulate analogous to X_xc but specific to
    microalgal biomass. It disintegrates first-order in X_alg.
  - The recalcitrance factor f_wall_alg (0–1) multiplies k_dis_alg to represent
    cell-wall resistance.  f_wall_alg = 1.0 means no recalcitrance (same as X_xc).
    f_wall_alg < 1 means partial resistance. Typical range: 0.4–0.9 depending on
    species and pre-treatment.
  - Products enter existing ADM1 pools (X_ch, X_pr, X_li, X_I, S_I) and are
    then hydrolysed/consumed by the core model processes without modification.
  - Nitrogen balance: S_IN released = i_N_alg − f_pr_alg × i_N_aa
    (net N in algae minus N tied up in protein fraction; remainder from
    carbohydrate/lipid/inert fractions is assumed negligible).
  - Carbon balance (S_IC) is tracked via the net C imbalance in disintegration.

States:
    X_alg (kgCOD/m³): algal composite particulate organic matter fed to the digester.

Processes:
    rho_E20_dis_alg: first-order disintegration of X_alg into X_ch, X_pr, X_li, X_I, S_I.

Fractionation (all dimensionless, kgCOD/kgCOD):
    f_ch_alg   protein/carbohydrate fraction → X_ch
    f_pr_alg   protein fraction → X_pr
    f_li_alg   lipid fraction → X_li
    f_xI_alg   insoluble inert fraction (cell wall, biogenic) → X_I
    f_sI_alg   soluble inert fraction → S_I
    Sum = 1 (enforced via validate_hook).

Typical species values (Mairet et al. 2011 Table 1):
    Chlorella vulgaris:  f_pr ≈ 0.50, f_ch ≈ 0.21, f_li ≈ 0.20, f_xI ≈ 0.07, f_sI ≈ 0.02
    Scenedesmus obliquus: f_pr ≈ 0.42, f_ch ≈ 0.30, f_li ≈ 0.18, f_xI ≈ 0.08, f_sI ≈ 0.02
    Spirulina (Arthrospira): f_pr ≈ 0.65, f_ch ≈ 0.17, f_li ≈ 0.07, f_xI ≈ 0.09, f_sI ≈ 0.02

Domain warning:
    Default parameters are calibrated for common freshwater microalgae
    (Chlorella / Scenedesmus) at mesophilic conditions. Marine or extremophile
    strains may differ significantly. Recalibrate k_dis_alg and fractionation
    when changing species or pre-treatment strategy.

Reference:
    Mairet F, Bernard O, Ras M, Lardon L, Steyer JP (2011). "Modeling anaerobic
    digestion of microalgae using ADM1." Bioresour Technol 102(13):6823–6829.
    doi:10.1016/j.biortech.2011.04.027

    Batstone DJ et al. (2002). "The IWA Anaerobic Digestion Model No 1 (ADM1)."
    Water Sci Technol 45(10):65–73.
"""
from __future__ import annotations

from typing import Mapping

import numpy as np

from simulator.full_model.assembly import FullModelAssembly
from simulator.full_model.catalog_types import ParameterDefinition, ProcessDefinition, StateDefinition
from simulator.full_model.extensions import FullModelExtensionContribution
from simulator.full_model.units import DAY_INV, DIMENSIONLESS, KG_COD_M3

_SRC = (
    "Mairet F et al. (2011) Bioresour Technol 102:6823–6829 doi:10.1016/j.biortech.2011.04.027; "
    "Batstone DJ et al. (2002) Water Sci Technol 45(10):65–73"
)


class _MicroalgaeExtension:
    name = "microalgae"
    description = (
        "E20: digestão de microalgas — desintegração de X_alg com recalcitrância de parede celular, "
        "fracionamento de alta proteína e liberação de N inorgânico (Mairet et al. 2011)."
    )

    def contribute(self) -> FullModelExtensionContribution:
        states = (
            StateDefinition(
                name="X_alg",
                description="Biomassa algal composta (kgCOD/m³) — substrato particulado específico para microalgas.",
                unit=KG_COD_M3,
                phase="solid",
                domain="composite",
                role="dynamic",
                cod_role="cod",
                elemental_proxy="C_xc",
                source=_SRC,
                notes=(
                    "Analogous to X_xc but with algae-specific disintegration kinetics and fractionation. "
                    "Disintegrates at rate k_dis_alg × f_wall_alg (effective). Products go to X_ch, X_pr, "
                    "X_li, X_I, S_I — handled by existing ADM1 hydrolysis processes."
                ),
            ),
        )

        processes = (
            ProcessDefinition(
                name="rho_E20_dis_alg",
                vendor_symbol="Rho_E20_1",
                family="biochemical",
                description=(
                    "Desintegração de microalgas: X_alg → X_ch + X_pr + X_li + X_I + S_I + S_IN + S_IC. "
                    "Taxa reduzida pela recalcitrância da parede celular (f_wall_alg)."
                ),
                rate_expression="computed_by_extension",
                affected_states=("X_alg", "X_ch", "X_pr", "X_li", "X_I", "S_I", "S_IN", "S_IC"),
                parameters=("k_dis_alg", "f_wall_alg", "f_ch_alg", "f_pr_alg", "f_li_alg", "f_xI_alg", "f_sI_alg", "i_N_alg"),
                inhibitions=(),
                source=_SRC,
                notes="Rate = k_dis_alg × f_wall_alg × X_alg. f_wall_alg < 1 for recalcitrant cell walls.",
            ),
        )

        parameters = (
            ParameterDefinition(
                name="k_dis_alg",
                value=0.25,
                unit=DAY_INV,
                group="biochemical",
                classification="calibrated",
                description="Taxa de desintegração de X_alg sem recalcitrância (d⁻¹).",
                source=_SRC,
                notes=(
                    "Mairet et al. 2011 reports k_dis values in the range 0.1–0.5 d⁻¹ depending on species "
                    "and pre-treatment. Default 0.25 d⁻¹ corresponds to untreated Chlorella at 35°C. "
                    "Thermal/enzymatic pre-treatment can increase effective rate 2–5×."
                ),
            ),
            ParameterDefinition(
                name="f_wall_alg",
                value=0.7,
                unit=DIMENSIONLESS,
                group="biochemical",
                classification="calibrated",
                description="Fator de recalcitrância da parede celular (0–1). Multiplica k_dis_alg.",
                source=_SRC,
                notes=(
                    "f_wall_alg = 1.0 → no recalcitrance (fully accessible). "
                    "f_wall_alg ≈ 0.4–0.7 for untreated Chlorella/Scenedesmus with cellulose walls. "
                    "f_wall_alg ≈ 0.8–0.95 after thermal pre-treatment (>70°C). "
                    "Spirulina (no cellulose wall) ≈ 0.85. Range: [0.1, 1.0]."
                ),
            ),
            ParameterDefinition(
                name="f_ch_alg",
                value=0.21,
                unit=DIMENSIONLESS,
                group="stoichiometric",
                classification="calibrated",
                description="Fração de carboidratos em X_alg (kgCOD/kgCOD) → X_ch.",
                source=_SRC,
                notes="Mairet 2011 Table 1: Chlorella ≈ 0.21. Typical range 0.15–0.35.",
            ),
            ParameterDefinition(
                name="f_pr_alg",
                value=0.50,
                unit=DIMENSIONLESS,
                group="stoichiometric",
                classification="calibrated",
                description="Fração proteica em X_alg (kgCOD/kgCOD) → X_pr.",
                source=_SRC,
                notes=(
                    "Mairet 2011 Table 1: Chlorella ≈ 0.50. Spirulina ≈ 0.65. Range 0.35–0.65. "
                    "Higher protein → more S_IN released per kgCOD substrate."
                ),
            ),
            ParameterDefinition(
                name="f_li_alg",
                value=0.20,
                unit=DIMENSIONLESS,
                group="stoichiometric",
                classification="calibrated",
                description="Fração lipídica em X_alg (kgCOD/kgCOD) → X_li.",
                source=_SRC,
                notes="Mairet 2011: Chlorella ≈ 0.20. Range 0.05–0.40 depending on growth conditions.",
            ),
            ParameterDefinition(
                name="f_xI_alg",
                value=0.07,
                unit=DIMENSIONLESS,
                group="stoichiometric",
                classification="calibrated",
                description="Fração inerte insolúvel em X_alg (kgCOD/kgCOD) → X_I (parede celular biogênica).",
                source=_SRC,
                notes="Mairet 2011: Chlorella ≈ 0.07. Includes cell wall residues and biogenic inerts.",
            ),
            ParameterDefinition(
                name="f_sI_alg",
                value=0.02,
                unit=DIMENSIONLESS,
                group="stoichiometric",
                classification="calibrated",
                description="Fração inerte solúvel em X_alg (kgCOD/kgCOD) → S_I.",
                source=_SRC,
                notes=(
                    "Mairet 2011: Chlorella ≈ 0.02. Small but non-zero. "
                    "Sum check: f_ch + f_pr + f_li + f_xI + f_sI must equal 1.0 (±1e-3)."
                ),
            ),
            ParameterDefinition(
                name="i_N_alg",
                value=0.06,
                unit="kgN/kgCOD",
                group="stoichiometric",
                classification="calibrated",
                description="Conteúdo de N em X_alg (kgN/kgCOD).",
                source=_SRC,
                notes=(
                    "Mairet 2011: i_N_alg ≈ 0.055–0.065 kgN/kgCOD for high-protein microalgae. "
                    "ADM1 default i_N_xc = 0.00268 kgN/kgCOD (municipal sludge). "
                    "Microalgae have ~20× higher N content, leading to significant S_IN release."
                ),
            ),
        )

        # Stoichiometry notes:
        #   rho_E20_dis_alg: X_alg (1 kgCOD) → products
        #     X_ch: + f_ch_alg kgCOD
        #     X_pr: + f_pr_alg kgCOD
        #     X_li: + f_li_alg kgCOD
        #     X_I:  + f_xI_alg kgCOD
        #     S_I:  + f_sI_alg kgCOD
        #     S_IN: net N balance. N in X_alg = i_N_alg.
        #           N in X_pr = f_pr_alg × i_N_aa (i_N_aa = 0.007 kgN/kgCOD, ADM1 default)
        #           N in X_I = f_xI_alg × N_I (N_I = 0.002 kgN/kgCOD, ADM1 default)
        #           N in S_I = f_sI_alg × N_I
        #           S_IN released = i_N_alg - f_pr_alg × N_aa - f_xI_alg × N_I - f_sI_alg × N_I
        #     S_IC: carbon balance — computed in rate_function (parameter-dependent)
        #   The stoichiometry here uses symbolic parameter names resolved at runtime.
        biochemical_stoichiometry_rows = {
            "rho_E20_dis_alg": {
                "X_alg": "-1",
                "X_ch": "f_ch_alg",
                "X_pr": "f_pr_alg",
                "X_li": "f_li_alg",
                "X_I": "f_xI_alg",
                "S_I": "f_sI_alg",
                # S_IN: N released = N in algae - N in protein products - N in inert products
                "S_IN": "i_N_alg - f_pr_alg * N_aa - (f_xI_alg + f_sI_alg) * N_I",
                # S_IC: C balance (C in X_alg - C going to products via known fractions)
                # Using algal C content analogous to C_xc, and product C content from standard ADM1
                "S_IC": "-(C_xc - f_ch_alg * C_ch - f_pr_alg * C_pr - f_li_alg * C_li - (f_xI_alg + f_sI_alg) * C_xI)",
            },
        }

        return FullModelExtensionContribution(
            states=states,
            processes=processes,
            parameters=parameters,
            biochemical_stoichiometry_rows=biochemical_stoichiometry_rows,
            rate_function=self._rates,
            diagnostics_hook=self._diagnostics,
            validate_hook=self._validate,
        )

    def _rates(self, state: Mapping[str, float], params: Mapping[str, float]) -> dict[str, float]:
        x_alg = max(float(state.get("X_alg", 0.0)), 0.0)
        k_dis = float(params["k_dis_alg"])
        f_wall = float(params["f_wall_alg"])
        # Effective disintegration rate with cell-wall recalcitrance factor
        rho_dis_alg = k_dis * f_wall * x_alg
        return {"rho_E20_dis_alg": rho_dis_alg}

    def _diagnostics(
        self,
        matrix: np.ndarray,
        assembly: FullModelAssembly,
        params: Mapping[str, float],
    ) -> dict[str, list[float]]:
        x_alg = np.clip(matrix[:, assembly.full_state_index["X_alg"]], 0.0, None)
        x_pr = np.clip(matrix[:, assembly.full_state_index["X_pr"]], 0.0, None)
        s_in = np.clip(matrix[:, assembly.full_state_index["S_IN"]], 0.0, None)

        # Effective hydrolysis indicator: fraction of X_alg degraded over simulation
        x_alg_0 = x_alg[0] if x_alg[0] > 1e-12 else 1.0
        alg_conversion = np.clip(1.0 - x_alg / x_alg_0, 0.0, 1.0)

        # Effective disintegration rate at each timestep
        k_eff = float(params["k_dis_alg"]) * float(params["f_wall_alg"])
        k_eff_series = np.full(len(x_alg), k_eff)

        return {
            "X_alg": x_alg.astype(float).tolist(),
            "X_alg_conversion": alg_conversion.astype(float).tolist(),
            "k_dis_alg_effective": k_eff_series.astype(float).tolist(),
            "X_pr_from_algae_proxy": x_pr.astype(float).tolist(),
            "S_IN": s_in.astype(float).tolist(),
        }

    def _validate(self, assembly: FullModelAssembly) -> None:
        """Check that algal fractions sum to 1.0 ± 1e-3."""
        defaults = {p.name: p.value for p in assembly.parameter_catalog}
        f_sum = sum(
            defaults.get(k, 0.0)
            for k in ("f_ch_alg", "f_pr_alg", "f_li_alg", "f_xI_alg", "f_sI_alg")
        )
        if abs(f_sum - 1.0) > 1e-3:
            raise ValueError(
                f"E20 (microalgae): frações algais somam {f_sum:.4f} ≠ 1.0. "
                "Verifique f_ch_alg + f_pr_alg + f_li_alg + f_xI_alg + f_sI_alg = 1."
            )


MICROALGAE_EXTENSION = _MicroalgaeExtension()
