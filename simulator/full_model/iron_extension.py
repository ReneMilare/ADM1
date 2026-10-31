"""E8 — Ferro: Redução de Fe(III) e Precipitação de FeS e Vivianita.

Models the iron cycle in anaerobic digesters, including:
  1. Biological/abiotic reduction of Fe(III) to Fe(II) via H2 and H2S
  2. Precipitation of iron sulfide (FeS — mackinawite/amorphous)
  3. Precipitation of vivianite (Fe₃(PO₄)₂·8H₂O)

Iron biochemistry is important for:
  - H2S removal (FeS precipitation lowers dissolved sulfide)
  - Phosphorus recovery via vivianite
  - Digester alkalinity buffering

DEPENDENCIES:
  - E4 (srb): provides S_H2S state (H2S produced by sulfate-reducing bacteria)
  - E7 (phosphorus): provides S_IP state (inorganic phosphorus for vivianite)
  Both must be active when E8 is used.

States added:
  S_Fe2:  Fe(II) dissolved     (kmolFe/m³)
  X_FeS:  FeS precipitate      (kmolFe/m³)
  X_VIV:  vivianite precipitate (kmol mineral/m³) — Fe₃(PO₄)₂
  X_S0:   elemental sulfur (kmolS/m³)

Note: S_Fe3 (Fe(III)) is treated as a fixed feed parameter (not an ODE state)
because Fe(III) is rapidly consumed and typically supplied via external dosing
or present as a constant feed concentration.

Process stoichiometry units: rates are in kmolFe/m³/d unless noted.

Reference:
    Batstone DJ, Keller J, Angelidaki I et al. (2002). "The IWA Anaerobic Digestion
    Model No 1 (ADM1)." Water Sci Technol 45(10):65–73.

    Dinh HT, Kuever J, Mussmann M, Hassel AW, Stratmann M, Widdel F (2004).
    "Iron corrosion by novel anaerobic microorganisms." Nature 427(6977):829–832.
    doi:10.1038/nature02321

    Wilfert P, Kumar PS, Korving L, Witkamp GJ, van Loosdrecht MCM (2015).
    "The relevance of phosphorus and iron chemistry to the recovery of phosphorus
    from wastewater: a review." Environ Sci Technol 49(16):9400–9414.
    doi:10.1021/acs.est.5b00150

    Lizarralde I, Fernandez-Arévalo T, Brouckaert C, Vanrolleghem P, Ikumi DS,
    Ekama GA, Ayesa E, Grau P (2015). "A new general systematic methodology for
    incorporating physicochemical transformations into multi-phase wastewater
    treatment process models." Water Research 74:239–256.
    doi:10.1016/j.watres.2015.01.031
"""
from __future__ import annotations

from typing import Mapping

import numpy as np

from simulator.full_model.assembly import FullModelAssembly
from simulator.full_model.catalog_types import ParameterDefinition, ProcessDefinition, StateDefinition
from simulator.full_model.extensions import FullModelExtensionContribution
from simulator.full_model.units import DAY_INV, DIMENSIONLESS, KG_COD_M3, KMOL_M3

_SRC = (
    "Wilfert et al. (2015) Environ Sci Technol 49:9400–9414 doi:10.1021/acs.est.5b00150; "
    "Lizarralde et al. (2015) Water Res 74:239–256 doi:10.1016/j.watres.2015.01.031; "
    "Batstone et al. (2002) ADM1 IWA, Water Sci Technol 45(10):65–73"
)
_KMOL_FE_M3 = "kmolFe/m3"
_KMOL_S_M3 = "kmolS/m3"


class _IronExtension:
    name = "iron"
    description = (
        "E8: ciclo do ferro — redução Fe(III)→Fe(II), precipitação FeS e vivianita. "
        "Requer E4 (srb) e E7 (phosphorus) ativos."
    )

    def contribute(self) -> FullModelExtensionContribution:
        states = (
            StateDefinition(
                name="S_Fe2",
                description="Ferro(II) dissolvido (Fe²⁺).",
                unit=_KMOL_FE_M3,
                phase="liquid",
                domain="soluble",
                role="dynamic",
                cod_role="non_cod",
                elemental_proxy=None,
                source=_SRC,
                notes="Produced by Fe(III) reduction; consumed by FeS and vivianite precipitation.",
            ),
            StateDefinition(
                name="X_FeS",
                description="Sulfeto ferroso precipitado (FeS — mackinawita/amorfo).",
                unit=_KMOL_FE_M3,
                phase="solid",
                domain="precipitate",
                role="dynamic",
                cod_role="non_cod",
                elemental_proxy=None,
                source=_SRC,
                notes="Ksp_FeS = 6.3e-18 (kmol/m³)². Primary sink for both Fe²⁺ and H2S.",
            ),
            StateDefinition(
                name="X_VIV",
                description="Vivianita precipitada (Fe₃(PO₄)₂·8H₂O).",
                unit="kmolVIV/m3",
                phase="solid",
                domain="precipitate",
                role="dynamic",
                cod_role="non_cod",
                elemental_proxy=None,
                source=_SRC,
                notes=(
                    "Tracked in kmol vivianite/m³. 1 mol vivianita = 3 mol Fe²⁺ + 2 mol PO4³⁻. "
                    "Ksp_VIV = 1e-36 (kmol/m³)⁵."
                ),
            ),
            StateDefinition(
                name="X_S0",
                description="Enxofre elementar particulado inerte (S⁰).",
                unit=_KMOL_S_M3,
                phase="solid",
                domain="precipitate",
                role="dynamic",
                cod_role="non_cod",
                elemental_proxy=None,
                source=_SRC,
                notes="Formed by Fe(III) reduction with sulfide.",
            ),
        )

        processes = (
            ProcessDefinition(
                name="rho_E8_Fe3_red_h2",
                vendor_symbol="Rho_E8_1",
                family="biochemical",
                description="Redução abiótica de Fe(III) via H₂: Fe³⁺ + ½H₂ → Fe²⁺ + H⁺.",
                rate_expression="computed_by_extension",
                affected_states=("S_Fe2", "S_h2"),
                parameters=("k_Fe3_red_h2", "K_S_Fe3_h2", "S_Fe3_feed"),
                inhibitions=(),
                source=_SRC,
            ),
            ProcessDefinition(
                name="rho_E8_Fe3_red_h2s",
                vendor_symbol="Rho_E8_2",
                family="biochemical",
                description="Redução abiótica de Fe(III) via H₂S: 2Fe³⁺ + H₂S → 2Fe²⁺ + S⁰ + 2H⁺.",
                rate_expression="computed_by_extension",
                affected_states=("S_Fe2", "S_H2S", "X_S0"),
                parameters=("k_Fe3_red_h2s", "S_Fe3_feed"),
                inhibitions=(),
                source=_SRC,
            ),
            ProcessDefinition(
                name="rho_E8_FeS_precip",
                vendor_symbol="Rho_E8_3",
                family="biochemical",
                description="Precipitação de FeS: Fe²⁺ + H₂S → FeS + 2H⁺.",
                rate_expression="computed_by_extension",
                affected_states=("S_Fe2", "S_H2S", "X_FeS"),
                parameters=("k_precip_FeS", "Ksp_FeS"),
                inhibitions=(),
                source=_SRC,
            ),
            ProcessDefinition(
                name="rho_E8_FeS_dissolv",
                vendor_symbol="Rho_E8_4",
                family="biochemical",
                description="Dissolução de FeS: FeS + 2H⁺ → Fe²⁺ + H₂S.",
                rate_expression="computed_by_extension",
                affected_states=("S_Fe2", "S_H2S", "X_FeS"),
                parameters=("k_dissolv_FeS", "Ksp_FeS"),
                inhibitions=(),
                source=_SRC,
            ),
            ProcessDefinition(
                name="rho_E8_VIV_precip",
                vendor_symbol="Rho_E8_5",
                family="biochemical",
                description="Precipitação de vivianita: 3Fe²⁺ + 2PO₄³⁻ → Fe₃(PO₄)₂.",
                rate_expression="computed_by_extension",
                affected_states=("S_Fe2", "S_IP", "X_VIV"),
                parameters=("k_precip_VIV", "Ksp_VIV", "Ka_H2PO4", "Ka_HPO4"),
                inhibitions=(),
                source=_SRC,
            ),
        )

        parameters = (
            ParameterDefinition(
                name="S_Fe3_feed",
                value=0.001,
                unit=_KMOL_FE_M3,
                group="operating",
                classification="provisional",
                description="Concentração de Fe(III) no afluente (parâmetro operacional fixo).",
                source=_SRC,
                notes=(
                    "0.001 kmolFe/m³ ≈ 55.8 mg/L Fe³⁺. Represents iron dosing or feed iron. "
                    "Treated as constant feed to avoid stiffness from fast Fe3 dynamics."
                ),
            ),
            ParameterDefinition(
                name="k_Fe3_red_h2",
                value=5.0,
                unit=DAY_INV,
                group="biochemical",
                classification="provisional",
                description="Constante cinética de redução de Fe(III) por H₂.",
                source=_SRC,
                notes="Abiotic reduction rate. Monod-type in S_h2 (K_S_Fe3_h2) and first-order in S_Fe3_feed.",
            ),
            ParameterDefinition(
                name="K_S_Fe3_h2",
                value=1e-5,
                unit=KG_COD_M3,
                group="biochemical",
                classification="provisional",
                description="Meia-saturação de H₂ para redução de Fe(III).",
                source=_SRC,
                notes="Low K_S: Fe3 reduction by H2 is efficient even at low H2 concentrations.",
            ),
            ParameterDefinition(
                name="k_Fe3_red_h2s",
                value=50.0,
                unit="m3/(kmolFe·d)",
                group="biochemical",
                classification="provisional",
                description="Constante cinética de redução de Fe(III) por H₂S (1ª ordem em H₂S).",
                source=_SRC,
                notes="Higher than k_Fe3_red_h2: H2S is a more effective reductant for Fe3.",
            ),
            ParameterDefinition(
                name="Ksp_FeS",
                value=6.3e-18,
                unit="(kmol/m3)^2",
                group="physicochemical",
                classification="canonical",
                description="Produto de solubilidade do FeS (mackinawita): [Fe²⁺][S²⁻].",
                source=_SRC,
                notes="Ksp for amorphous FeS ≈ 6.3e-18 M². Very insoluble → rapid precipitation.",
            ),
            ParameterDefinition(
                name="k_precip_FeS",
                value=200.0,
                unit=DAY_INV,
                group="biochemical",
                classification="provisional",
                description="Constante cinética de precipitação de FeS.",
                source=_SRC,
                notes="Fast precipitation kinetics consistent with Ksp_FeS being extremely low.",
            ),
            ParameterDefinition(
                name="k_dissolv_FeS",
                value=1.0,
                unit=DAY_INV,
                group="biochemical",
                classification="provisional",
                description="Constante cinética de dissolução de FeS.",
                source=_SRC,
            ),
            ParameterDefinition(
                name="Ksp_VIV",
                value=1e-36,
                unit="(kmol/m3)^5",
                group="physicochemical",
                classification="canonical",
                description="Produto de solubilidade da vivianita: [Fe²⁺]³[PO₄³⁻]².",
                source=_SRC,
                notes="Ksp vivianite ≈ 1e-36 M⁵ (Wilfert et al. 2015). Extremely insoluble.",
            ),
            ParameterDefinition(
                name="k_precip_VIV",
                value=50.0,
                unit=DAY_INV,
                group="biochemical",
                classification="provisional",
                description="Constante cinética de precipitação de vivianita.",
                source=_SRC,
            ),
        )

        # Stoichiometry notes:
        # rho_E8_Fe3_red_h2: Fe3 + 0.5 H2 → Fe2 + H+
        #   Rate in kmolFe/m³/d. Per kmolFe reduced: consumes 0.5 kmol H2.
        #   H2 in ADM1 is kgCOD/m³. 1 mol H2 = 2 g, COD(H2) = 2 × 8 gO2/g = 16 gCOD.
        #   So 1 kmol H2 = 16 kgCOD → 0.5 kmol H2 = 8 kgCOD.
        #   Therefore: S_h2 coefficient = -8.0 kgCOD per kmolFe reduced.
        #
        # rho_E8_Fe3_red_h2s: 2Fe3 + H2S → 2Fe2 + S0 + 2H+
        #   Per kmolFe reduced: 0.5 kmol H2S consumed.
        #   S_H2S unit in ADM1 = kmolS/m³.
        #
        # rho_E8_FeS_precip: Fe2 + H2S → FeS↓ + 2H+
        #   Per kmolFe precipitated: 1 kmolFe and 1 kmolS consumed.
        #
        # rho_E8_VIV_precip: 3Fe2 + 2PO4 → Fe3(PO4)2
        #   Rate rho_viv_p in kmolFe/m³/d.
        #   Per kmolFe consumed: 2/3 kmolP consumed, 1/3 kmol vivianita produced
        #   (since 3 Fe per mol vivianite).
        biochemical_stoichiometry_rows = {
            "rho_E8_Fe3_red_h2": {
                "S_Fe2": "1",      # 1 kmolFe²⁺ produced per kmolFe reduced
                "S_h2": "-8.0",    # 0.5 kmol H₂ = 8 kgCOD consumed per kmolFe
            },
            "rho_E8_Fe3_red_h2s": {
                "S_Fe2": "1",    # 1 kmolFe²⁺ produced
                "S_H2S": "-0.5", # 0.5 kmolS consumed per kmolFe (2Fe per mol H2S)
                "X_S0": "0.5",
            },
            "rho_E8_FeS_precip": {
                "S_Fe2": "-1",   # 1 kmolFe²⁺ consumed
                "S_H2S": "-1",   # 1 kmolS consumed (H2S as sulfide source)
                "X_FeS": "1",    # 1 kmolFe precipitated as FeS
            },
            "rho_E8_FeS_dissolv": {
                "S_Fe2": "1",
                "S_H2S": "1",
                "X_FeS": "-1",
            },
            "rho_E8_VIV_precip": {
                "S_Fe2": "-1",      # 1 kmolFe²⁺ consumed per unit rate
                "S_IP": "-2/3",  # 2/3 kmolP consumed (2 PO4 per 3 Fe)
                "X_VIV": "1/3",  # 1/3 kmol vivianita produced per kmolFe
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

    def _rates(
        self, state: Mapping[str, float], params: Mapping[str, float]
    ) -> dict[str, float]:
        s_fe2 = max(float(state.get("S_Fe2", 0.0)), 0.0)
        x_fes = max(float(state.get("X_FeS", 0.0)), 0.0)
        # S_H2S from E4 (srb extension); defaults to 0 if not present
        s_h2s = max(float(state.get("S_H2S", 0.0)), 0.0)
        # S_IP from E7 (phosphorus extension)
        s_ip = max(float(state.get("S_IP", 0.0)), 0.0)
        # S_h2 from ADM1 core
        s_h2 = max(float(state.get("S_h2", 0.0)), 1e-15)
        s_h_ion = max(float(state.get("S_H_ion", 1e-7)), 1e-14)

        # Fe(III) concentration is a fixed feed parameter
        s_fe3 = float(params["S_Fe3_feed"])

        # --- Fe(III) reduction by H2 (Monod in S_h2) ---
        rho_fe3_h2 = (
            float(params["k_Fe3_red_h2"])
            * s_fe3
            * s_h2 / (float(params["K_S_Fe3_h2"]) + s_h2)
        )

        # --- Fe(III) reduction by H2S (1st order in S_H2S) ---
        rho_fe3_h2s = float(params["k_Fe3_red_h2s"]) * s_fe3 * s_h2s

        # --- FeS precipitation/dissolution ---
        ip_fes = (s_fe2 * s_h2s) / max(float(params["Ksp_FeS"]), np.nextafter(0.0, 1.0))
        rho_fes_p = float(params["k_precip_FeS"]) * max(ip_fes - 1.0, 0.0) * s_fe2
        rho_fes_d = float(params["k_dissolv_FeS"]) * max(1.0 - ip_fes, 0.0) * x_fes

        # --- Vivianite precipitation ---
        # IP = [Fe²⁺]³ × [PO4³⁻]² / Ksp_VIV
        # PO4³⁻ speciation from S_IP (same constants as E7)
        ka2 = float(params.get("Ka_H2PO4", 6.31e-8))
        ka3 = float(params.get("Ka_HPO4", 4.57e-13))
        denom_p = s_h_ion * s_h_ion + ka2 * s_h_ion + ka2 * ka3
        s_po4 = s_ip * ka2 * ka3 / max(denom_p, 1e-30)

        ip_viv = (s_fe2 ** 3 * s_po4 ** 2) / max(float(params["Ksp_VIV"]), np.nextafter(0.0, 1.0))
        rho_viv_p = float(params["k_precip_VIV"]) * max(ip_viv - 1.0, 0.0) * s_fe2

        return {
            "rho_E8_Fe3_red_h2": rho_fe3_h2,
            "rho_E8_Fe3_red_h2s": rho_fe3_h2s,
            "rho_E8_FeS_precip": rho_fes_p,
            "rho_E8_FeS_dissolv": rho_fes_d,
            "rho_E8_VIV_precip": rho_viv_p,
        }

    def _diagnostics(
        self,
        matrix: np.ndarray,
        assembly: FullModelAssembly,
        params: Mapping[str, float],
    ) -> dict[str, list[float]]:
        s_fe2 = np.clip(matrix[:, assembly.full_state_index["S_Fe2"]], 0.0, None)
        x_fes = np.clip(matrix[:, assembly.full_state_index["X_FeS"]], 0.0, None)
        x_viv = np.clip(matrix[:, assembly.full_state_index["X_VIV"]], 0.0, None)
        # S_H2S from E4 (required dependency)
        s_h2s = np.clip(matrix[:, assembly.full_state_index["S_H2S"]], 0.0, None)
        # S_IP from E7 (required dependency)
        s_ip = np.clip(matrix[:, assembly.full_state_index["S_IP"]], 0.0, None)
        # S_H_ion is an algebraic state stored in the full state matrix
        s_h_ion = np.clip(matrix[:, assembly.full_state_index["S_H_ion"]], 1e-14, None)

        # --- FeS saturation index IP_FeS = [Fe²⁺][S²⁻] / Ksp_FeS ---
        # Note: S_H2S in ADM1 is total dissolved sulfide (H2S + HS- + S²-)
        # For Ksp_FeS we use total H2S as a proxy (conservative approximation)
        ksp_fes = float(params["Ksp_FeS"])
        ip_fes = (s_fe2 * s_h2s) / max(ksp_fes, np.nextafter(0.0, 1.0))

        # --- Vivianite saturation index IP_VIV = [Fe²⁺]³[PO₄³⁻]² / Ksp_VIV ---
        ka2 = float(params.get("Ka_H2PO4", 6.31e-8))
        ka3 = float(params.get("Ka_HPO4", 4.57e-13))
        denom_p = s_h_ion ** 2 + ka2 * s_h_ion + ka2 * ka3
        s_po4 = s_ip * ka2 * ka3 / np.maximum(denom_p, 1e-30)

        ksp_viv = float(params["Ksp_VIV"])
        ip_viv = (s_fe2 ** 3 * s_po4 ** 2) / max(ksp_viv, np.nextafter(0.0, 1.0))

        # Simple rate proxy: cumulative FeS formed (proxy for H2S removed)
        h2s_removed_by_fes = np.maximum(np.diff(x_fes, prepend=x_fes[0]), 0.0)

        return {
            "S_Fe2": s_fe2.astype(float).tolist(),
            "X_FeS": x_fes.astype(float).tolist(),
            "X_VIV": x_viv.astype(float).tolist(),
            "H2S_removed_by_FeS_cumulative": x_fes.astype(float).tolist(),
            "IP_FeS": np.clip(ip_fes, 0.0, None).astype(float).tolist(),
            "IP_VIV": np.clip(ip_viv, 0.0, None).astype(float).tolist(),
        }

    def _validate(self, assembly: FullModelAssembly) -> None:
        """Enforce that E4 (srb) and E7 (phosphorus) are active."""
        active = set(assembly.active_extensions)
        if "srb" not in active:
            raise ValueError(
                "E8 (iron) requer E4 (srb) ativo. "
                "Adicione 'srb' a active_extensions antes de 'iron'."
            )
        if "phosphorus" not in active:
            raise ValueError(
                "E8 (iron) requer E7 (phosphorus) ativo. "
                "Adicione 'phosphorus' a active_extensions antes de 'iron'."
            )


IRON_EXTENSION = _IronExtension()
