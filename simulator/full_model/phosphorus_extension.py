"""E7 — Fósforo: Especiação e Precipitação (Phosphorus Extension).

Adds dissolved inorganic phosphorus (S_IP) as a tracked state and models two
precipitation reactions relevant to anaerobic digesters:
  1. Struvite (MgNH₄PO₄·6H₂O): Mg²⁺ + NH₄⁺ + PO₄³⁻ → struvite
  2. Calcite (CaCO₃): Ca²⁺ + CO₃²⁻ → CaCO₃

Mg²⁺ and Ca²⁺ concentrations are treated as fixed operational parameters
(not ODE states) since they are typically controlled or slowly changing compared
to digester dynamics. This is consistent with most operational models.

Phosphate speciation (pKa2=7.20, pKa3=12.34 at 35°C):
  H2PO4⁻  (dominant below pH 7.2)
  HPO4²⁻  (dominant above pH 7.2)
  PO4³⁻   (negligible below pH 12)

The phosphate species contribute to the charge-balance equation solved by the
Newton-Raphson pH solver in acid_base.py. The contribution is added automatically
when S_IP > 0 in the dynamic state vector — no modification to acid_base.py call
sites is required.

States:
  S_IP:   dissolved inorganic phosphorus total (kmolP/m³)
  X_MAP:  struvite precipitate (kmolP/m³) — MgNH₄PO₄
  X_CaCO3: calcite precipitate (kmolC/m³) — CaCO₃

Processes:
  rho_E7_MAP_precip:    struvite precipitation kinetics (1st order in S_IP)
  rho_E7_MAP_dissolv:   struvite dissolution (1st order in X_MAP)
  rho_E7_CaCO3_precip:  calcite precipitation (1st order in S_IC)
  rho_E7_CaCO3_dissolv: calcite dissolution (1st order in X_CaCO3)

Reference:
    Barat R, Montoya T, Seco A, Ferrer J (2011). "Modelling biological and
    chemically induced precipitation of calcium phosphate in enhanced biological
    phosphorus removal systems." Water Research 45(12):3744–3752.
    doi:10.1016/j.watres.2011.04.028

    Batstone DJ, Amerlinck Y, Ekama G, Goel R, Grau P, Johnson B, Kaya I,
    Steyer JP, Tait S, Takács I, Vanrolleghem PA, Brouckaert CJ, Volcke E (2012).
    "Towards a generalized physicochemical framework." Water Sci Technol
    66(6):1147–1161. doi:10.2166/wst.2012.300

    Musvoto EV, Wentzel MC, Loewenthal RE, Ekama GA (2000). "Integrated
    chemical-physical processes modelling — I. Development of a kinetic-based
    model for mixed weak acid/base systems." Water Research 34(6):1857–1867.
    doi:10.1016/S0043-1354(99)00334-6
"""
from __future__ import annotations

from typing import Mapping

import numpy as np

from simulator.full_model.assembly import FullModelAssembly
from simulator.full_model.catalog_types import ParameterDefinition, ProcessDefinition, StateDefinition
from simulator.full_model.extensions import FullModelExtensionContribution
from simulator.full_model.units import DAY_INV, DIMENSIONLESS, KMOL_M3

_SRC = (
    "Barat et al. (2011) Water Res 45:3744–3752 doi:10.1016/j.watres.2011.04.028; "
    "Batstone et al. (2012) Water Sci Technol 66:1147–1161 doi:10.2166/wst.2012.300; "
    "Musvoto et al. (2000) Water Res 34:1857–1867 doi:10.1016/S0043-1354(99)00334-6"
)
_KMOL_P_M3 = "kmolP/m3"
_KMOL_C_M3 = "kmolC/m3"


class _PhosphorusExtension:
    name = "phosphorus"
    description = (
        "E7: fósforo inorgânico dissolvido (S_IP), especiação fosfato no Newton de pH, "
        "precipitação de estruvita (X_MAP) e calcita (X_CaCO3)."
    )

    def contribute(self) -> FullModelExtensionContribution:
        states = (
            StateDefinition(
                name="S_IP",
                description="Fósforo inorgânico total dissolvido (H2PO4⁻ + HPO4²⁻ + PO4³⁻).",
                unit=_KMOL_P_M3,
                phase="liquid",
                domain="soluble",
                role="dynamic",
                cod_role="non_cod",
                elemental_proxy=None,
                source=_SRC,
                notes=(
                    "Speciation resolved implicitly via charge balance in acid_base.py. "
                    "Ka_H2PO4=6.31e-8 kmol/m³ (pKa2=7.20 at 35°C); "
                    "Ka_HPO4=4.57e-13 kmol/m³ (pKa3=12.34 at 35°C)."
                ),
            ),
            StateDefinition(
                name="X_MAP",
                description="Estruvita precipitada (MgNH₄PO₄·6H₂O).",
                unit=_KMOL_P_M3,
                phase="solid",
                domain="precipitate",
                role="dynamic",
                cod_role="non_cod",
                elemental_proxy=None,
                source=_SRC,
                notes="Ksp_MAP = 2.5e-13 (kmol/m³)³. Tracked in kmolP/m³ (1 mol struvite per mol P).",
            ),
            StateDefinition(
                name="X_CaCO3",
                description="Calcita precipitada (CaCO₃).",
                unit=_KMOL_C_M3,
                phase="solid",
                domain="precipitate",
                role="dynamic",
                cod_role="non_cod",
                elemental_proxy=None,
                source=_SRC,
                notes="Ksp_CaCO3 = 3.3e-9 (kmol/m³)². Tracked in kmolC/m³.",
            ),
        )

        processes = (
            ProcessDefinition(
                name="rho_E7_MAP_precip",
                vendor_symbol="Rho_E7_1",
                family="biochemical",
                description="Precipitação de estruvita: Mg²⁺ + NH₄⁺ + PO₄³⁻ → MgNH₄PO₄.",
                rate_expression="computed_by_extension",
                affected_states=("S_IP", "S_IN", "X_MAP"),
                parameters=("k_precip_MAP", "Ksp_MAP", "S_Mg", "Ka_H2PO4", "Ka_HPO4"),
                inhibitions=(),
                source=_SRC,
            ),
            ProcessDefinition(
                name="rho_E7_MAP_dissolv",
                vendor_symbol="Rho_E7_2",
                family="biochemical",
                description="Dissolução de estruvita: MgNH₄PO₄ → Mg²⁺ + NH₄⁺ + PO₄³⁻.",
                rate_expression="computed_by_extension",
                affected_states=("S_IP", "S_IN", "X_MAP"),
                parameters=("k_dissolv_MAP", "Ksp_MAP", "S_Mg", "Ka_H2PO4", "Ka_HPO4"),
                inhibitions=(),
                source=_SRC,
            ),
            ProcessDefinition(
                name="rho_E7_CaCO3_precip",
                vendor_symbol="Rho_E7_3",
                family="biochemical",
                description="Precipitação de calcita: Ca²⁺ + CO₃²⁻ → CaCO₃.",
                rate_expression="computed_by_extension",
                affected_states=("S_IC", "X_CaCO3"),
                parameters=("k_precip_CaCO3", "Ksp_CaCO3", "S_Ca"),
                inhibitions=(),
                source=_SRC,
            ),
            ProcessDefinition(
                name="rho_E7_CaCO3_dissolv",
                vendor_symbol="Rho_E7_4",
                family="biochemical",
                description="Dissolução de calcita: CaCO₃ → Ca²⁺ + CO₃²⁻.",
                rate_expression="computed_by_extension",
                affected_states=("S_IC", "X_CaCO3"),
                parameters=("k_dissolv_CaCO3", "Ksp_CaCO3", "S_Ca"),
                inhibitions=(),
                source=_SRC,
            ),
        )

        parameters = (
            ParameterDefinition(
                name="Ka_H2PO4",
                value=6.31e-8,
                unit=KMOL_M3,
                group="physicochemical",
                classification="canonical",
                description="Constante de dissociação H2PO4⁻/HPO4²⁻ (pKa2 = 7.20 a 35°C).",
                source=_SRC,
                notes="Ka2 of phosphoric acid at 35°C. Computed from pKa2=7.20: 10^(-7.20)=6.31e-8 M.",
            ),
            ParameterDefinition(
                name="Ka_HPO4",
                value=4.57e-13,
                unit=KMOL_M3,
                group="physicochemical",
                classification="canonical",
                description="Constante de dissociação HPO4²⁻/PO4³⁻ (pKa3 = 12.34 a 35°C).",
                source=_SRC,
                notes="Ka3 of phosphoric acid at 35°C. Computed from pKa3=12.34: 10^(-12.34)=4.57e-13 M.",
            ),
            ParameterDefinition(
                name="Ksp_MAP",
                value=2.5e-13,
                unit="(kmol/m3)^3",
                group="physicochemical",
                classification="canonical",
                description="Produto de solubilidade da estruvita (MgNH₄PO₄): [Mg²⁺][NH₄⁺][PO₄³⁻].",
                source=_SRC,
                notes="Ksp at 25°C ≈ 2.5e-13 M³ (Musvoto 2000). Used with PO4³⁻ species.",
            ),
            ParameterDefinition(
                name="k_precip_MAP",
                value=100.0,
                unit=DAY_INV,
                group="biochemical",
                classification="provisional",
                description="Constante cinética de precipitação de estruvita.",
                source=_SRC,
                notes="Provisional rate constant. Large value (fast kinetics) consistent with "
                      "struvite forming rapidly when IP > Ksp. Adjust during calibration.",
            ),
            ParameterDefinition(
                name="k_dissolv_MAP",
                value=0.5,
                unit=DAY_INV,
                group="biochemical",
                classification="provisional",
                description="Constante cinética de dissolução de estruvita.",
                source=_SRC,
                notes="Dissolution is slower than precipitation. Provisional value.",
            ),
            ParameterDefinition(
                name="S_Mg",
                value=0.004,
                unit=KMOL_M3,
                group="operating",
                classification="provisional",
                description="Concentração de Mg²⁺ no digestor (parâmetro operacional fixo).",
                source=_SRC,
                notes=(
                    "0.004 kmolMg/m³ ≈ 97 mg/L Mg²⁺. Typical municipal digester range: 50–150 mg/L. "
                    "Treated as a constant because Mg²⁺ dynamics are slow relative to P speciation."
                ),
            ),
            ParameterDefinition(
                name="Ksp_CaCO3",
                value=3.3e-9,
                unit="(kmol/m3)^2",
                group="physicochemical",
                classification="canonical",
                description="Produto de solubilidade da calcita (CaCO₃): [Ca²⁺][CO₃²⁻].",
                source=_SRC,
                notes="Ksp calcite at 35°C ≈ 3.3e-9 M². Musvoto et al. 2000.",
            ),
            ParameterDefinition(
                name="k_precip_CaCO3",
                value=50.0,
                unit=DAY_INV,
                group="biochemical",
                classification="provisional",
                description="Constante cinética de precipitação de calcita.",
                source=_SRC,
                notes="Provisional. CaCO₃ nucleation can be slow; adjust with operational data.",
            ),
            ParameterDefinition(
                name="k_dissolv_CaCO3",
                value=1.0,
                unit=DAY_INV,
                group="biochemical",
                classification="provisional",
                description="Constante cinética de dissolução de calcita.",
                source=_SRC,
            ),
            ParameterDefinition(
                name="S_Ca",
                value=0.005,
                unit=KMOL_M3,
                group="operating",
                classification="provisional",
                description="Concentração de Ca²⁺ no digestor (parâmetro operacional fixo).",
                source=_SRC,
                notes=(
                    "0.005 kmolCa/m³ ≈ 200 mg/L Ca²⁺. Typical municipal digester range 100–400 mg/L. "
                    "Treated as constant; Ca²⁺ dynamics slow relative to digester biochemistry."
                ),
            ),
        )

        # Stoichiometry:
        # rho_E7_MAP_precip: precipitates 1 kmolP from S_IP into X_MAP,
        #   consumes 1 kmolN from S_IN (NH4+ component of struvite).
        # rho_E7_MAP_dissolv: reverses precipitation.
        # rho_E7_CaCO3_precip: removes 1 kmolC from S_IC into X_CaCO3.
        # rho_E7_CaCO3_dissolv: reverses.
        # Note: stoichiometric coefficient for S_IN in MAP is -1.0 kmolN/kmolP
        # because 1 mol struvite contains 1 mol NH4+ (1 mol N).
        biochemical_stoichiometry_rows = {
            "rho_E7_MAP_precip": {
                "S_IP": "-1",    # consumes 1 kmolP/m³
                "X_MAP": "1",    # precipitates 1 kmolP/m³ as struvite
                "S_IN": "-1",    # consumes 1 kmolN/m³ (1 mol NH4+ per mol MgNH4PO4)
            },
            "rho_E7_MAP_dissolv": {
                "S_IP": "1",
                "X_MAP": "-1",
                "S_IN": "1",
            },
            "rho_E7_CaCO3_precip": {
                "S_IC": "-1",    # consumes 1 kmolC/m³
                "X_CaCO3": "1",
            },
            "rho_E7_CaCO3_dissolv": {
                "S_IC": "1",
                "X_CaCO3": "-1",
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
        s_ip = max(float(state.get("S_IP", 0.0)), 0.0)
        x_map = max(float(state.get("X_MAP", 0.0)), 0.0)
        x_caco3 = max(float(state.get("X_CaCO3", 0.0)), 0.0)
        s_ic = max(float(state.get("S_IC", 0.0)), 0.0)
        s_h_ion = max(float(state.get("S_H_ion", 1e-7)), 1e-14)
        s_in = max(float(state.get("S_IN", 0.0)), 0.0)

        # --- Phosphate speciation ---
        ka2 = float(params["Ka_H2PO4"])
        ka3 = float(params["Ka_HPO4"])
        denom_p = s_h_ion * s_h_ion + ka2 * s_h_ion + ka2 * ka3
        if denom_p <= 0.0:
            s_po4 = 0.0
        else:
            # PO4³⁻ fraction — controls struvite supersaturation
            s_po4 = s_ip * ka2 * ka3 / max(denom_p, 1e-30)

        # NH4+ from the inorganic nitrogen pool (use S_nh4_ion if available from acid-base)
        # S_nh4_ion is an algebraic state set by acid_base. Use it if present.
        s_nh4 = float(state.get("S_nh4_ion", 0.0))
        if s_nh4 <= 0.0:
            # Fallback: approximate NH4+ from S_IN (most N is NH4+ at digester pH)
            ka_in = float(params.get("K_a_IN", 1.4e-9))
            s_nh4 = s_in * s_h_ion / (ka_in + s_h_ion)

        # --- Struvite (MAP) supersaturation index ---
        # Ksp_MAP = [Mg²⁺][NH₄⁺][PO₄³⁻]
        s_mg = float(params["S_Mg"])
        ksp_map = float(params["Ksp_MAP"])
        ip_map = (s_mg * s_nh4 * s_po4) / max(ksp_map, 1e-30)

        rho_map_p = float(params["k_precip_MAP"]) * max(ip_map - 1.0, 0.0) * s_ip
        rho_map_d = float(params["k_dissolv_MAP"]) * max(1.0 - ip_map, 0.0) * x_map

        # --- Calcite (CaCO3) supersaturation index ---
        # CO3²⁻ from S_IC via simplified equilibrium:
        #   S_IC ≈ H2CO3* + HCO3⁻ → CO3²⁻ = Ka_hco3 * HCO3⁻ / [H+]
        #   HCO3⁻ = Ka_co2 * S_IC / (Ka_co2 + [H+])
        ka_co2 = float(params.get("K_a_co2", 4.47e-7))
        # pKa for CO3²⁻/HCO3⁻ ≈ 10.33 at 35°C → Ka_hco3 ≈ 4.68e-11 M
        ka_hco3 = 4.68e-11
        s_hco3 = ka_co2 * s_ic / max(ka_co2 + s_h_ion, 1e-30)
        s_co3 = ka_hco3 * s_hco3 / max(s_h_ion, 1e-14)

        s_ca = float(params["S_Ca"])
        ksp_caco3 = float(params["Ksp_CaCO3"])
        ip_caco3 = (s_ca * s_co3) / max(ksp_caco3, 1e-30)

        rho_caco3_p = float(params["k_precip_CaCO3"]) * max(ip_caco3 - 1.0, 0.0) * s_ic
        rho_caco3_d = float(params["k_dissolv_CaCO3"]) * max(1.0 - ip_caco3, 0.0) * x_caco3

        return {
            "rho_E7_MAP_precip": rho_map_p,
            "rho_E7_MAP_dissolv": rho_map_d,
            "rho_E7_CaCO3_precip": rho_caco3_p,
            "rho_E7_CaCO3_dissolv": rho_caco3_d,
        }

    def _diagnostics(
        self,
        matrix: np.ndarray,
        assembly: FullModelAssembly,
        params: Mapping[str, float],
    ) -> dict[str, list[float]]:
        s_ip = np.clip(matrix[:, assembly.full_state_index["S_IP"]], 0.0, None)
        x_map = np.clip(matrix[:, assembly.full_state_index["X_MAP"]], 0.0, None)
        x_caco3 = np.clip(matrix[:, assembly.full_state_index["X_CaCO3"]], 0.0, None)
        s_ic = np.clip(matrix[:, assembly.full_state_index["S_IC"]], 0.0, None)
        # S_H_ion and S_nh4_ion are algebraic states stored in the full state matrix
        s_h_ion = np.clip(matrix[:, assembly.full_state_index["S_H_ion"]], 1e-14, None)
        s_nh4 = np.clip(matrix[:, assembly.full_state_index["S_nh4_ion"]], 0.0, None)

        # --- Struvite (MAP) saturation index IP_MAP = [Mg²⁺][NH₄⁺][PO₄³⁻] / Ksp ---
        ka2 = float(params["Ka_H2PO4"])
        ka3 = float(params["Ka_HPO4"])
        denom_p = s_h_ion ** 2 + ka2 * s_h_ion + ka2 * ka3
        s_po4 = s_ip * ka2 * ka3 / np.maximum(denom_p, 1e-30)

        s_mg = float(params["S_Mg"])
        ksp_map = float(params["Ksp_MAP"])
        ip_map = s_mg * s_nh4 * s_po4 / max(ksp_map, 1e-30)

        # --- Calcite (CaCO3) saturation index IP_CaCO3 = [Ca²⁺][CO₃²⁻] / Ksp ---
        ka_co2 = float(params.get("K_a_co2", 4.47e-7))
        ka_hco3 = 4.68e-11  # pKa for HCO3-/CO3²⁻ at 35°C
        s_hco3 = ka_co2 * s_ic / np.maximum(ka_co2 + s_h_ion, 1e-30)
        s_co3 = ka_hco3 * s_hco3 / np.maximum(s_h_ion, 1e-14)

        s_ca = float(params["S_Ca"])
        ksp_caco3 = float(params["Ksp_CaCO3"])
        ip_caco3 = s_ca * s_co3 / max(ksp_caco3, 1e-30)

        return {
            "S_IP": s_ip.astype(float).tolist(),
            "X_MAP": x_map.astype(float).tolist(),
            "X_CaCO3": x_caco3.astype(float).tolist(),
            "P_precipitated_MAP_cumulative": x_map.astype(float).tolist(),
            "IP_MAP": np.clip(ip_map, 0.0, None).astype(float).tolist(),
            "IP_CaCO3": np.clip(ip_caco3, 0.0, None).astype(float).tolist(),
        }

    def _validate(self, assembly: FullModelAssembly) -> None:
        """Verify that S_IP is in the assembly state catalog (extension is active)."""
        if "S_IP" not in assembly.full_state_index:
            raise ValueError(
                "E7 (phosphorus) validate_hook: S_IP não encontrado no assembly. "
                "A extensão 'phosphorus' deve estar incluída em active_extensions."
            )


PHOSPHORUS_EXTENSION = _PhosphorusExtension()
