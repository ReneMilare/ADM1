"""E15 — Biometanação de Syngas (Syngas Biomethanation Extension).

Adds CO as an explicit substrate for anaerobic digestion, enabling simulation of
syngas (CO + H2 + CO2) biomethanation. CO dissolves from the gas phase, is
consumed by specialized CO-utilizing microorganisms (X_met_CO) via an enzymatic
water-gas shift reaction (CO + H2O → CO2 + H2), and the produced H2 is then
consumed by existing hydrogenotrophic methanogens.

Architecture:
  - S_CO   (liquid, kgCOD/m³): dissolved CO
  - S_gas_CO (gas, kgCOD/m³):  CO in the headspace
  - X_met_CO (liquid, kgCOD/m³): CO-utilizing homoacetogens/Carboxydotrophic methanogens

CO uptake pathway (dominant, per the reference paper):
    CO + H2O  →  CO2 + H2   (enzymatic WGS, catalyzed by CO dehydrogenase)
    4H2 + CO2 →  CH4 + 2H2O (hydrogenotrophic methanogenesis — existing ADM1 rho_12)
Net: 4CO + 2H2O → CH4 + 3CO2

Stoichiometry (per kgCOD S_CO consumed):
  S_CO:   -1
  S_h2:   +(1 - Y_met_CO)   [H2 produced from WGS, COD-balanced since COD(CO) = COD(H2) = 16 gO2/mol]
  S_IC:   +C_CO*(1-Y_met_CO) - Y_met_CO*C_bac  [C from CO → CO2 minus C to biomass]
  S_IN:   -Y_met_CO * N_bac
  X_met_CO: +Y_met_CO

  where C_CO = 0.0625 kmolC/kgCOD (1 mol C per 16 gCOD CO)

Gas-liquid CO transfer (Henry's law, analogous to H2):
  rho_transfer = k_La_CO * (S_CO - 16 * K_H_CO * p_gas_CO)
  p_gas_CO = S_gas_CO * R * T / 16  [bar; identical denominator to H2 since both have 16 gCOD/mol]

Note on gas dynamics:
  rhs.py applies venting -(q_gas/V_gas)*S_gas_CO for all extension gas states automatically
  (see FullCSTRRhs.__call__). The stoichiometry coefficient V_liq/V_gas for S_gas_CO converts
  the liquid-basis transfer rate to a gas-volume basis.

CO inhibition of acetoclastic methanogenesis:
  CO inhibits X_ac (rho_11) via competitive inhibition (Lecker et al. 2017 Eq. 4):
    I_CO_ac = K_I_CO / (K_I_CO + S_CO)
  Applied only when CO is present at meaningful concentrations.

Domain note:
  Default parameters are derived for mesophilic (35°C) CSTR biomethanation.
  Thermophilic conditions increase CO transfer rates but also shift community
  composition. At CO partial pressures > 0.5 bar, CO becomes inhibitory to most
  methanogens (Lecker et al. 2017 Table 1). Use X_met_CO initial inoculum > 0.01
  kgCOD/m³ or the simulation will not show CO consumption.

Reference:
    Lecker B, Illi L, Lemmer A, Oechsner H (2017). "Biological hydrogen
    methanation — A review." Bioresour Technol 245(Pt A):1220–1228.
    doi:10.1016/j.biortech.2017.08.176

    Wang W, Xie L, Chen J, Luo G, Zhou Q (2013). "Biogas production from
    codigestion of dairy manure and high-concentration whey." Bioresour Technol
    143:323–328. doi:10.1016/j.biortech.2013.06.011

    Guiot SR, Cimpoia R, Carayon G (2011). "Potential of wastewater-treating
    anaerobic granules for biomethanation of synthesis gas." Environ Sci Technol
    45(5):2006–2012. doi:10.1021/es102728b

    Reference for ADM1 extension and CO water-gas shift pathway:
    "Modification and extension of anaerobic digestion model No. 1 (ADM1) for
    syngas biomethanation simulation: From lab-scale to pilot-scale."
    (local PDF: documentation/Modification and extension of anaerobic digestion
    model No.1 (ADM1) for syngas biomethanation simulation...)
"""
from __future__ import annotations

from typing import Mapping

import numpy as np

from simulator.full_model.assembly import FullModelAssembly
from simulator.full_model.catalog_types import ParameterDefinition, ProcessDefinition, StateDefinition
from simulator.full_model.extensions import FullModelExtensionContribution
from simulator.full_model.units import DAY_INV, DIMENSIONLESS, KG_COD_M3

_SRC = (
    "Lecker et al. (2017) Bioresour Technol 245:1220–1228 doi:10.1016/j.biortech.2017.08.176; "
    "Guiot et al. (2011) Environ Sci Technol 45:2006–2012 doi:10.1021/es102728b; "
    "Wang et al. (2013) Bioresour Technol 143:323–328 doi:10.1016/j.biortech.2013.06.011"
)
_KMOL_M3 = "kmol/m3"


class _SyngasExtension:
    name = "syngas"
    description = (
        "E15: biometanação de syngas — CO dissoluto + X_met_CO (WGS enzimático) → H2 → CH4. "
        "Gas-liquid transfer com Lei de Henry, inibição de CO em acetoclástica (Lecker 2017)."
    )

    def contribute(self) -> FullModelExtensionContribution:
        states = (
            StateDefinition(
                name="S_CO",
                description="CO dissolvido (substrato para X_met_CO via WGS enzimática).",
                unit=KG_COD_M3,
                phase="liquid",
                domain="soluble",
                role="dynamic",
                cod_role="cod",
                elemental_proxy=None,
                source=_SRC,
                notes=(
                    "kgCOD/m³. 1 mol CO = 28 g, COD = 16 gO2/mol (same as H2). "
                    "Typical dissolved CO: 0.0001–0.002 kgCOD/m³ at biomethanation conditions. "
                    "Gas-liquid transfer driven by Henry's law (K_H_CO ≈ 8e-4 kmol/m³/bar at 35°C)."
                ),
            ),
            StateDefinition(
                name="S_gas_CO",
                description="CO na fase gasosa (headspace/syngas bubble).",
                unit=KG_COD_M3,
                phase="gas",
                domain="soluble",
                role="dynamic",
                cod_role="cod",
                elemental_proxy=None,
                source=_SRC,
                notes=(
                    "kgCOD/m³_gas. Drives dissolution into S_CO. "
                    "p_gas_CO = S_gas_CO * R * T / 16 [bar]. "
                    "Venting applied by rhs.py (q_gas/V_gas * S_gas_CO). "
                    "Typical syngas: 20–30% CO v/v."
                ),
            ),
            StateDefinition(
                name="X_met_CO",
                description="Biomassa de micro-organismos carbóxidotróficos (utilizam CO via WGS).",
                unit=KG_COD_M3,
                phase="solid",
                domain="active_biomass",
                role="dynamic",
                cod_role="cod",
                elemental_proxy="C_bac",
                source=_SRC,
                notes=(
                    "CO-utilizing anaerobes (Carboxydothermus hydrogenoformans-like). "
                    "Require inoculum ≥ 0.01 kgCOD/m³. Decay → X_xc."
                ),
            ),
        )

        processes = (
            ProcessDefinition(
                name="rho_E15_CO_uptake",
                vendor_symbol="Rho_E15_1",
                family="biochemical",
                description="Oxidação biológica de CO via WGS enzimática: CO + H2O → CO2 + H2 (+ biomassa).",
                rate_expression="computed_by_extension",
                affected_states=("S_CO", "S_h2", "S_IC", "S_IN", "X_met_CO"),
                parameters=("k_m_met_CO", "K_S_CO", "Y_met_CO"),
                inhibitions=("I_pH_h2",),
                source=_SRC,
                notes=(
                    "Monod kinetics in S_CO × X_met_CO × I_pH × I_IN. "
                    "Product H2 enters ADM1 pool and is consumed by X_h2 (rho_12). "
                    "Net: CO → H2 (catabolism, Y_met_CO ≈ 0.034)."
                ),
            ),
            ProcessDefinition(
                name="rho_E15_decay_X_met_CO",
                vendor_symbol="Rho_E15_2",
                family="biochemical",
                description="Decaimento de X_met_CO → X_xc.",
                rate_expression="computed_by_extension",
                affected_states=("X_xc", "X_met_CO", "S_IC", "S_IN"),
                parameters=("k_dec_X_met_CO",),
                inhibitions=(),
                source=_SRC,
            ),
            ProcessDefinition(
                name="rho_E15_CO_transfer",
                vendor_symbol="Rho_E15_gas",
                family="biochemical",
                description="Transferência gás-líquido de CO (dissolução do syngas): S_gas_CO ↔ S_CO.",
                rate_expression="computed_by_extension",
                affected_states=("S_CO", "S_gas_CO"),
                parameters=("k_La_CO", "K_H_CO"),
                inhibitions=(),
                source=_SRC,
                notes="rho > 0 = net flux from liquid to gas (degassing). rho < 0 = dissolution.",
            ),
        )

        parameters = (
            ParameterDefinition(
                name="k_m_met_CO",
                value=2.6,
                unit=DAY_INV,
                group="biochemical",
                classification="calibrated",
                description="Taxa máxima específica de consumo de CO por X_met_CO (d⁻¹).",
                source=_SRC,
                notes=(
                    "Guiot et al. 2011: µ_max ≈ 2.6 d⁻¹ for granular CO-utilizing consortia at 35°C. "
                    "Range 1–5 d⁻¹ depending on community and temperature."
                ),
            ),
            ParameterDefinition(
                name="K_S_CO",
                value=0.014,
                unit=KG_COD_M3,
                group="biochemical",
                classification="calibrated",
                description="Constante de meia-saturação para CO dissolvido (kgCOD/m³).",
                source=_SRC,
                notes=(
                    "0.014 kgCOD/m³ ≈ 0.5 mM CO = 14 mg/L CO. "
                    "Lecker 2017: K_S_CO ≈ 0.3–0.8 mM for known CO-utilizing acetogens. "
                    "1 mmol CO = 28 mg CO = 28/16 gCOD = 1.75 gCOD → 0.5 mM = 0.875 gCOD/m³ ≈ 0.00875 kgCOD/m³."
                ),
            ),
            ParameterDefinition(
                name="Y_met_CO",
                value=0.034,
                unit=DIMENSIONLESS,
                group="stoichiometric",
                classification="calibrated",
                description="Rendimento de biomassa de X_met_CO (kgCOD_X / kgCOD_CO).",
                source=_SRC,
                notes=(
                    "Low yield analogous to Y_h2 (0.06 in ADM1). "
                    "Guiot 2011: yield ≈ 0.03–0.05 gVSS/gCOD → ~0.034 kgCOD/kgCOD (factor 1.42 VSS→COD)."
                ),
            ),
            ParameterDefinition(
                name="k_dec_X_met_CO",
                value=0.02,
                unit=DAY_INV,
                group="biochemical",
                classification="calibrated",
                description="Taxa de decaimento de X_met_CO (d⁻¹).",
                source=_SRC,
                notes="Analogous to k_dec_X_h2 = 0.02 d⁻¹ in ADM1 (Batstone et al. 2002 Table 1).",
            ),
            ParameterDefinition(
                name="K_H_CO",
                value=8.0e-4,
                unit="kmol/m3/bar",
                group="physicochemical",
                classification="calibrated",
                description="Constante de Henry para CO (kmol/m³/bar a 35°C).",
                source=_SRC,
                notes=(
                    "K_H_CO(25°C) ≈ 9.7e-4 mol/(L·atm) = 9.58e-4 kmol/(m³·bar). "
                    "At 35°C: ΔH_sol(CO) ≈ -13.7 kJ/mol → K_H(35°C) ≈ 8.0e-4 kmol/(m³·bar). "
                    "CO is only slightly more soluble than H2 (K_H_h2 ≈ 7.8e-4 at 35°C)."
                ),
            ),
            ParameterDefinition(
                name="k_La_CO",
                value=200.0,
                unit=DAY_INV,
                group="physicochemical",
                classification="calibrated",
                description="Coeficiente volumétrico de transferência de massa para CO (d⁻¹).",
                source=_SRC,
                notes="Same order of magnitude as k_La for H2/CH4/CO2 (200 d⁻¹ in ADM1 BSM2).",
            ),
            ParameterDefinition(
                name="K_I_CO",
                value=1.4e-3,
                unit=KG_COD_M3,
                group="biochemical",
                classification="calibrated",
                description="Constante de inibição de CO sobre metanogênese acetoclástica (kgCOD/m³).",
                source=_SRC,
                notes=(
                    "CO at ≥ 0.05 mM (~0.05 × 1.75 gCOD/m³ ≈ 0.09 gCOD/m³) inhibits X_ac. "
                    "Lecker 2017: K_I_CO ≈ 0.05 mM CO = 0.05e-3 × 16000/28 kgCOD/m³ ≈ 0.029 gCOD/m³. "
                    "Using more conservative value: 1.4e-3 kgCOD/m³ ≈ 0.05 mM. "
                    "Applied as Monod-type competitive inhibition: I_CO = K_I_CO / (K_I_CO + S_CO). "
                    "Note: inhibition is minor at typical dissolved CO concentrations in biomethanation."
                ),
            ),
        )

        # Stoichiometry notes:
        #   rho_E15_CO_uptake: S_CO (1 kgCOD) → products
        #     S_CO: -1 (substrate consumed)
        #     S_h2: +(1-Y_met_CO) (H2 produced via WGS; COD-balanced since CO and H2 share 16 gCOD/mol)
        #     S_IC: carbon balance: CO provides 1 C per mol = 0.0625 kmolC/kgCOD
        #           catabolized fraction (1-Y) CO carbon → CO2 → S_IC
        #           anabolic fraction Y × C_bac → X_met_CO
        #           Δ S_IC = +0.0625 × (1-Y) - Y × C_bac
        #           Simplified: +(0.0625 - Y_met_CO * (0.0625 + C_bac))
        #           = 0.0625 * (1 - Y_met_CO) - Y_met_CO * C_bac
        #     S_IN: -Y_met_CO * N_bac (nitrogen for biomass growth)
        #     X_met_CO: +Y_met_CO
        #
        #   rho_E15_decay_X_met_CO: X_met_CO → X_xc (identical to other ADM1 biomass decays)
        #
        #   rho_E15_CO_transfer: CO gas-liquid (net transfer from liquid to gas when S_CO supersaturated)
        #     S_CO: -1 (rate × -1 removes dissolved CO when transferring to gas)
        #     S_gas_CO: +V_liq/V_gas (scales liquid-basis rate to gas-volume basis)
        #     rhs.py adds venting: -(q_gas/V_gas)*S_gas_CO for all extension gas states
        biochemical_stoichiometry_rows = {
            "rho_E15_CO_uptake": {
                "S_CO": "-1",
                "S_h2": "1 - Y_met_CO",
                # S_IC: C from CO (0.0625 kmolC/kgCOD) catabolism → CO2, minus C to biomass
                "S_IC": "0.0625 * (1.0 - Y_met_CO) - Y_met_CO * C_bac",
                "S_IN": "-Y_met_CO * N_bac",
                "X_met_CO": "Y_met_CO",
            },
            "rho_E15_decay_X_met_CO": {
                "X_xc": "1",
                "X_met_CO": "-1",
                "S_IC": "-s_13",
                "S_IN": "N_bac - N_xc",
            },
            "rho_E15_CO_transfer": {
                "S_CO": "-1",
                "S_gas_CO": "V_liq / V_gas",
            },
        }

        return FullModelExtensionContribution(
            states=states,
            processes=processes,
            parameters=parameters,
            biochemical_stoichiometry_rows=biochemical_stoichiometry_rows,
            rate_function=self._rates,
            diagnostics_hook=self._diagnostics,
            inhibition_hook=self._inhibition,
        )

    def _rates(self, state: Mapping[str, float], params: Mapping[str, float]) -> dict[str, float]:
        s_co = max(float(state.get("S_CO", 0.0)), 0.0)
        s_gas_co = max(float(state.get("S_gas_CO", 0.0)), 0.0)
        x_met_co = max(float(state.get("X_met_CO", 0.0)), 0.0)
        s_h_ion = max(float(state.get("S_H_ion", 1e-7)), 1e-14)
        s_in = max(float(state.get("S_IN", 1e-4)), 1e-12)

        # pH inhibition (same shape as hydrogenotrophic methanogens, analogous organisms)
        i_ph_h2 = (params["K_pH_h2"] ** params["n_h2"]) / (s_h_ion ** params["n_h2"] + params["K_pH_h2"] ** params["n_h2"])
        # Nitrogen limitation
        i_in_lim = 1.0 / (1.0 + params["K_S_IN"] / s_in)

        # Monod kinetics for CO uptake
        rho_co_uptake = (
            float(params["k_m_met_CO"])
            * s_co / (float(params["K_S_CO"]) + s_co)
            * x_met_co
            * i_ph_h2
            * i_in_lim
        )
        rho_dec_met_co = float(params["k_dec_X_met_CO"]) * x_met_co

        # Gas-liquid CO transfer (Henry's law, same convention as rho_t8 for H2 in gas_transfer.py)
        r_gas = float(params.get("R", 8.314e-2))  # bar·m³/(kmol·K)
        t_op = float(params.get("T_op", 308.15))
        p_gas_co = s_gas_co * r_gas * t_op / 16.0  # bar (analogous to p_gas_h2)
        k_h_co = float(params.get("K_H_CO", 8.0e-4))
        rho_co_transfer = float(params["k_La_CO"]) * (s_co - 16.0 * k_h_co * p_gas_co)

        return {
            "rho_E15_CO_uptake": rho_co_uptake,
            "rho_E15_decay_X_met_CO": rho_dec_met_co,
            "rho_E15_CO_transfer": rho_co_transfer,
        }

    def _inhibition(self, state: Mapping[str, float], params: Mapping[str, float]) -> dict[str, float]:
        """CO competitive inhibition of acetoclastic methanogenesis (rho_11_uptake_acetate).

        Lecker 2017 Eq. 4 — Monod-type competitive inhibition:
            I_CO = K_I_CO / (K_I_CO + S_CO)
        Inhibition is modest at typical dissolved CO concentrations (< 0.01 kgCOD/m³)
        but significant at high partial pressures (> 0.3 bar CO).
        """
        s_co = max(float(state.get("S_CO", 0.0)), 0.0)
        k_i_co = float(params.get("K_I_CO", 1.4e-3))
        i_co = k_i_co / (k_i_co + s_co)
        return {"rho_11_uptake_acetate": i_co}

    def _diagnostics(
        self,
        matrix: np.ndarray,
        assembly: FullModelAssembly,
        params: Mapping[str, float],
    ) -> dict[str, list[float]]:
        s_co = np.clip(matrix[:, assembly.full_state_index["S_CO"]], 0.0, None)
        s_gas_co = np.clip(matrix[:, assembly.full_state_index["S_gas_CO"]], 0.0, None)
        x_met_co = np.clip(matrix[:, assembly.full_state_index["X_met_CO"]], 0.0, None)
        s_ch4 = np.clip(matrix[:, assembly.full_state_index["S_ch4"]], 0.0, None)

        # Partial pressure of CO in headspace (bar)
        r_gas = float(params.get("R", 8.314e-2))
        t_op = float(params.get("T_op", 308.15))
        p_gas_co = s_gas_co * r_gas * t_op / 16.0  # bar

        # CO conversion proxy: fraction consumed relative to influent
        s_co_0 = float(params.get("S_CO_influent_proxy", 0.0)) or (s_co[0] if s_co[0] > 1e-6 else 1.0)
        co_conversion = np.clip(1.0 - s_co / max(s_co_0, 1e-9), 0.0, 1.0)

        # CH4 yield from CO pathway (proxy: total CH4 at time t)
        s_gas_ch4 = np.clip(matrix[:, assembly.full_state_index["S_gas_ch4"]], 0.0, None)
        r_gas_arr = np.full(len(s_co), r_gas)
        p_gas_ch4 = s_gas_ch4 * r_gas_arr * t_op / 64.0  # bar

        return {
            "S_CO": s_co.astype(float).tolist(),
            "S_gas_CO": s_gas_co.astype(float).tolist(),
            "X_met_CO": x_met_co.astype(float).tolist(),
            "p_gas_CO_bar": p_gas_co.astype(float).tolist(),
            "CO_conversion": co_conversion.astype(float).tolist(),
            "p_gas_CH4_bar": p_gas_ch4.astype(float).tolist(),
        }


SYNGAS_EXTENSION = _SyngasExtension()
