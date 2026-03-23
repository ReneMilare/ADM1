"""E9 — Elementos-Traço: Ni e Co como Micronutrientes (Trace Elements Extension).

Models nickel (Ni) and cobalt (Co) as essential micronutrients for anaerobic
digestion, implementing:
  1. Ni and Co as dissolved states tracking metal bioavailability
  2. Metal sulfide precipitation (NiS, CoS) when H₂S is present — requires E4 (srb)
  3. Dissolution of metal sulfide precipitates under undersaturation
  4. Monod-type limitation of acetoclastic and hydrogenotrophic methanogens when
     dissolved Ni/Co are below threshold concentrations

Fe(II) as micronutrient:
  Fe(II) is modeled as a FIXED FEED PARAMETER (S_Fe2_TE_feed), not a dynamic state,
  consistent with the E8 approach for Fe(III). This avoids initialization complexity
  while still enabling Fe-based limitation. For full Fe(II) dynamics (FeS/vivianite),
  use E8 (iron) extension — but note that E8 and trace_elements cannot be combined
  in v1 (validate_hook enforces this due to S_Fe2 state naming conflict).

States:
    S_Ni   (kmolNi/m³): dissolved Ni — substrate for methanogens (essential cofactor)
    S_Co   (kmolCo/m³): dissolved Co — corrinoid cofactor (Co = cobalt metal; distinct from CO gas)
    X_NiS  (kmolNi/m³): NiS precipitate (biologically unavailable)
    X_CoS  (kmolCo/m³): CoS precipitate (biologically unavailable)

Processes:
    rho_E9_NiS_precip / rho_E9_NiS_dissolv: NiS precipitation/dissolution
    rho_E9_CoS_precip / rho_E9_CoS_dissolv: CoS precipitation/dissolution

Precipitation chemistry:
    Me²⁺ + H₂S → MeS↓ + 2H⁺
    Rate: k_precip × max(IP - 1, 0) × S_Me  where IP = [Me][S²⁻] / Ksp
    Note: S_H2S state only present when E4 (srb) is active. Without E4, S_H2S = 0
    and precipitation rates return 0 (no sulfide → no precipitation). The stoichiometry
    referencing S_H2S is safely skipped by the assembly matrix builder when E4 is absent.

Biological limitation (Thanh et al. 2016 Eq. 7):
    I_Ni = S_Ni / (K_TE_Ni + S_Ni)
    I_Co = S_Co / (K_TE_Co + S_Co)
    Combined: I_TE_ac = I_Ni_ac × I_Co_ac  (applied to rho_11_uptake_acetate)
              I_TE_h2 = I_Ni_h2 × I_Co_h2  (applied to rho_12_uptake_hydrogen)
    Fe limitation: I_Fe = S_Fe2_TE_feed / (K_TE_Fe + S_Fe2_TE_feed)  (static, via parameter)

Combination rules:
  - E9 alone: all five processes active, S_Ni/S_Co dynamic
  - E4 + E9:  precipitation active (H₂S available)
  - E8 + E9:  NOT supported in v1 (validate_hook rejects — see note above)
  - E4 + E8 + E9: NOT supported in v1

Domain note:
  Default parameters target mesophilic CSTR at 35°C with typical municipal/agro
  substrate. Recalibrate K_TE thresholds when using industrial or trace-element-
  deficient substrates. Co limitation dominates in acetate-fed digesters; Ni
  limitation dominates in H₂-fed systems.

Reference:
    Thanh PM, Ketheesan B, Stuckey DC, Rasaratnam S (2016). "ADM1-based mechanistic
    model for the role of trace elements in anaerobic digestion processes." Chem Eng J
    291:106–117. doi:10.1016/j.cej.2016.01.055

    Roussel J, Bouyer D, Guibaud G, Baudu M (2012a). "ADM1 based mathematical model
    of trace element precipitation-dissolution in anaerobic digestion processes."
    Bioresour Technol 116:547–554. doi:10.1016/j.biortech.2012.03.063

    Roussel J, Bouyer D, Guibaud G, Baudu M (2012b). "ADM1 based mathematical model
    of trace element complexation in anaerobic digestion processes." Bioresour Technol
    125:301–310. doi:10.1016/j.biortech.2012.09.017

    Zandvoort MH, van Hullebusch ED, Fermoso FG, Lens PNL (2006). "Trace metals in
    anaerobic granular sludge reactors: bioavailability and dosing strategies." Eng
    Life Sci 6(3):293–301. doi:10.1002/elsc.200620129
"""
from __future__ import annotations

from typing import Mapping

import numpy as np

from simulator.full_model.assembly import FullModelAssembly
from simulator.full_model.catalog_types import ParameterDefinition, ProcessDefinition, StateDefinition
from simulator.full_model.extensions import FullModelExtensionContribution
from simulator.full_model.units import DAY_INV

_SRC = (
    "Thanh et al. (2016) Chem Eng J 291:106–117 doi:10.1016/j.cej.2016.01.055; "
    "Roussel et al. (2012a) Bioresour Technol 116:547–554 doi:10.1016/j.biortech.2012.03.063; "
    "Roussel et al. (2012b) Bioresour Technol 125:301–310 doi:10.1016/j.biortech.2012.09.017; "
    "Zandvoort et al. (2006) Eng Life Sci 6:293–301 doi:10.1002/elsc.200620129"
)
_KMOL_NI_M3 = "kmolNi/m3"
_KMOL_COB_M3 = "kmolCo/m3"    # Co = cobalt (element symbol Co, distinct from CO = carbon monoxide)


class _TraceElementsExtension:
    name = "trace_elements"
    description = (
        "E9: Ni e Co como micronutrientes — precipitação NiS/CoS (requer E4 srb), dissolução, "
        "e limitação de crescimento de X_ac/X_h2 por deficiência de traço (Thanh 2016)."
    )

    def contribute(self) -> FullModelExtensionContribution:
        states = (
            StateDefinition(
                name="S_Ni",
                description="Ni dissolvido (kmolNi/m³) — cofator essencial para metanogênese (F430, hidrogenases).",
                unit=_KMOL_NI_M3,
                phase="liquid",
                domain="soluble",
                role="dynamic",
                cod_role="non_cod",
                elemental_proxy=None,
                source=_SRC,
                notes=(
                    "Required for: F430 cofactor (acetoclastic Ni), [NiFe]-hydrogenases (H2 metabolism). "
                    "Optimal range: 0.5–5 µmol/L = 5e-7 – 5e-6 kmolNi/m³. "
                    "Precipitates as NiS when S_H2S > 0 (E4 active). "
                    "Set S_Ni in influent_state_overrides = S_Ni_feed. Default influent = 0."
                ),
            ),
            StateDefinition(
                name="S_Co",
                description="Co dissolvido (kmolCo/m³) — cofator corrinoide essencial para metanogênese. (Co = cobalt, ≠ CO gas)",
                unit=_KMOL_COB_M3,
                phase="liquid",
                domain="soluble",
                role="dynamic",
                cod_role="non_cod",
                elemental_proxy=None,
                source=_SRC,
                notes=(
                    "NOTE: state name S_Co = cobalt metal. S_CO (uppercase O) = carbon monoxide (syngas extension). "
                    "Required for: corrinoid cofactors (methyl transfer in acetogens/methanogens). "
                    "Optimal range: 0.1–2 µmol/L = 1e-7 – 2e-6 kmolCo/m³. "
                    "Precipitates as CoS when S_H2S > 0. More insoluble than NiS (Ksp_CoS << Ksp_NiS)."
                ),
            ),
            StateDefinition(
                name="X_NiS",
                description="Sulfeto de níquel precipitado (kmolNi/m³).",
                unit=_KMOL_NI_M3,
                phase="solid",
                domain="precipitate",
                role="dynamic",
                cod_role="non_cod",
                elemental_proxy=None,
                source=_SRC,
                notes="Amorphous NiS. Ksp_NiS = 3e-19 (kmol/m³)². Not bioavailable.",
            ),
            StateDefinition(
                name="X_CoS",
                description="Sulfeto de cobalto precipitado (kmolCo/m³).",
                unit=_KMOL_COB_M3,
                phase="solid",
                domain="precipitate",
                role="dynamic",
                cod_role="non_cod",
                elemental_proxy=None,
                source=_SRC,
                notes="Amorphous CoS. Ksp_CoS = 5e-22 (kmol/m³)². Not bioavailable.",
            ),
        )

        processes = (
            ProcessDefinition(
                name="rho_E9_NiS_precip",
                vendor_symbol="Rho_E9_1",
                family="biochemical",
                description="Precipitação de NiS: Ni²⁺ + H₂S → NiS↓ + 2H⁺.",
                rate_expression="computed_by_extension",
                affected_states=("S_Ni", "S_H2S", "X_NiS"),
                parameters=("k_precip_NiS", "Ksp_NiS"),
                inhibitions=(),
                source=_SRC,
                notes="S_H2S only available when E4 (srb) is active. Rate = 0 without E4.",
            ),
            ProcessDefinition(
                name="rho_E9_NiS_dissolv",
                vendor_symbol="Rho_E9_2",
                family="biochemical",
                description="Dissolução de NiS → Ni²⁺ + H₂S.",
                rate_expression="computed_by_extension",
                affected_states=("S_Ni", "S_H2S", "X_NiS"),
                parameters=("k_dissolv_NiS", "Ksp_NiS"),
                inhibitions=(),
                source=_SRC,
            ),
            ProcessDefinition(
                name="rho_E9_CoS_precip",
                vendor_symbol="Rho_E9_3",
                family="biochemical",
                description="Precipitação de CoS: Co²⁺ + H₂S → CoS↓ + 2H⁺.",
                rate_expression="computed_by_extension",
                affected_states=("S_Co", "S_H2S", "X_CoS"),
                parameters=("k_precip_CoS", "Ksp_CoS"),
                inhibitions=(),
                source=_SRC,
                notes="S_H2S only available when E4 (srb) is active. Rate = 0 without E4.",
            ),
            ProcessDefinition(
                name="rho_E9_CoS_dissolv",
                vendor_symbol="Rho_E9_4",
                family="biochemical",
                description="Dissolução de CoS → Co²⁺ + H₂S.",
                rate_expression="computed_by_extension",
                affected_states=("S_Co", "S_H2S", "X_CoS"),
                parameters=("k_dissolv_CoS", "Ksp_CoS"),
                inhibitions=(),
                source=_SRC,
            ),
        )

        parameters = (
            ParameterDefinition(
                name="S_Ni_feed",
                value=2e-6,
                unit=_KMOL_NI_M3,
                group="operating",
                classification="provisional",
                description="Concentração de Ni no afluente (kmolNi/m³) — parâmetro de referência.",
                source=_SRC,
                notes=(
                    "Used for documentation. To set actual influent Ni, use influent_state_overrides={'S_Ni': value}. "
                    "2e-6 kmolNi/m³ ≈ 0.12 mg/L Ni. Thanh 2016: optimal ≈ 1–5 µmol/L."
                ),
            ),
            ParameterDefinition(
                name="S_Co_feed",
                value=5e-7,
                unit=_KMOL_COB_M3,
                group="operating",
                classification="provisional",
                description="Concentração de Co no afluente (kmolCo/m³) — parâmetro de referência.",
                source=_SRC,
                notes=(
                    "5e-7 kmolCo/m³ ≈ 0.03 mg/L Co. Thanh 2016: optimal ≈ 0.5–2 µmol/L. "
                    "To set actual influent Co, use influent_state_overrides={'S_Co': value}."
                ),
            ),
            ParameterDefinition(
                name="S_Fe2_TE_feed",
                value=5e-5,
                unit="kmolFe/m3",
                group="operating",
                classification="provisional",
                description="Concentração de Fe(II) no afluente (kmolFe/m³) — parâmetro fixo para limitação.",
                source=_SRC,
                notes=(
                    "Fe(II) is treated as a constant feed parameter (not an ODE state) in E9. "
                    "5e-5 kmolFe/m³ ≈ 2.8 mg/L Fe²⁺. Used in inhibition hook for Fe limitation. "
                    "For full Fe dynamics, use E8 (iron) extension instead (not compatible with E9 in v1)."
                ),
            ),
            ParameterDefinition(
                name="Ksp_NiS",
                value=3e-19,
                unit="(kmol/m3)^2",
                group="physicochemical",
                classification="canonical",
                description="Produto de solubilidade do NiS amorfo: [Ni²⁺][S²⁻].",
                source=_SRC,
                notes="Roussel 2012a Table 1: Ksp_NiS = 3e-19 M² for amorphous NiS.",
            ),
            ParameterDefinition(
                name="k_precip_NiS",
                value=100.0,
                unit=DAY_INV,
                group="biochemical",
                classification="provisional",
                description="Constante cinética de precipitação de NiS (d⁻¹).",
                source=_SRC,
                notes="Fast kinetics consistent with low Ksp_NiS (Roussel 2012a).",
            ),
            ParameterDefinition(
                name="k_dissolv_NiS",
                value=0.5,
                unit=DAY_INV,
                group="biochemical",
                classification="provisional",
                description="Constante cinética de dissolução de NiS (d⁻¹).",
                source=_SRC,
            ),
            ParameterDefinition(
                name="Ksp_CoS",
                value=5e-22,
                unit="(kmol/m3)^2",
                group="physicochemical",
                classification="canonical",
                description="Produto de solubilidade do CoS amorfo: [Co²⁺][S²⁻].",
                source=_SRC,
                notes="Roussel 2012a Table 1: Ksp_CoS ≈ 5e-22 M². More insoluble than NiS.",
            ),
            ParameterDefinition(
                name="k_precip_CoS",
                value=100.0,
                unit=DAY_INV,
                group="biochemical",
                classification="provisional",
                description="Constante cinética de precipitação de CoS (d⁻¹).",
                source=_SRC,
            ),
            ParameterDefinition(
                name="k_dissolv_CoS",
                value=0.5,
                unit=DAY_INV,
                group="biochemical",
                classification="provisional",
                description="Constante cinética de dissolução de CoS (d⁻¹).",
                source=_SRC,
            ),
            ParameterDefinition(
                name="K_TE_Ni_ac",
                value=5e-7,
                unit=_KMOL_NI_M3,
                group="biochemical",
                classification="provisional",
                description="Meia-saturação de Ni para crescimento de X_ac (kmolNi/m³).",
                source=_SRC,
                notes=(
                    "Thanh 2016 Table 2: K_Ni for acetogens ≈ 2–8 µmol/L (conservative 0.5 µmol/L here). "
                    "Limitation: I_Ni_ac = S_Ni / (K_TE_Ni_ac + S_Ni). Full inhibition at S_Ni → 0."
                ),
            ),
            ParameterDefinition(
                name="K_TE_Ni_h2",
                value=5e-7,
                unit=_KMOL_NI_M3,
                group="biochemical",
                classification="provisional",
                description="Meia-saturação de Ni para crescimento de X_h2 (kmolNi/m³).",
                source=_SRC,
                notes="Hydrogenase [NiFe] requires Ni; similar threshold to X_ac (Thanh 2016).",
            ),
            ParameterDefinition(
                name="K_TE_Co_ac",
                value=1e-7,
                unit=_KMOL_COB_M3,
                group="biochemical",
                classification="provisional",
                description="Meia-saturação de Co para crescimento de X_ac (kmolCo/m³).",
                source=_SRC,
                notes=(
                    "Thanh 2016: K_Co for acetogens ≈ 0.1–0.5 µmol/L. "
                    "Methanogens are very efficient Co scavengers (corrinoid synthesis)."
                ),
            ),
            ParameterDefinition(
                name="K_TE_Co_h2",
                value=1e-7,
                unit=_KMOL_COB_M3,
                group="biochemical",
                classification="provisional",
                description="Meia-saturação de Co para crescimento de X_h2 (kmolCo/m³).",
                source=_SRC,
            ),
            ParameterDefinition(
                name="K_TE_Fe_ac",
                value=1e-6,
                unit="kmolFe/m3",
                group="biochemical",
                classification="provisional",
                description="Meia-saturação de Fe(II) para crescimento de X_ac (kmolFe/m³).",
                source=_SRC,
                notes=(
                    "Thanh 2016: Fe required for ferredoxin and cytochromes in acetogens. "
                    "K_TE_Fe ≈ 1–10 µmol/L = 1e-6 – 1e-5 kmolFe/m³."
                ),
            ),
        )

        # Stoichiometry notes:
        #   All rates in kmolMe/m³/d.
        #   rho_E9_NiS_precip: Ni²⁺ + H₂S → NiS + 2H⁺
        #     S_Ni: -1 (kmolNi consumed)
        #     X_NiS: +1 (kmolNi precipitated)
        #
        #   NOTE on H₂S balance (v1 simplification):
        #   S_H2S is NOT referenced here because it only exists when E4 (srb) is active,
        #   and the assembly validator rejects stoichiometry rows referencing absent states.
        #   Consequence: H₂S consumption by NiS/CoS precipitation is not tracked in S_H2S
        #   (≈ 1–5 µmol/L Ni/Co << typical S_H2S of 0.1–5 mmol/L → < 5% error in H₂S balance).
        #   v2 target: add conditional stoichiometry patch when E4 + E9 are co-active.
        biochemical_stoichiometry_rows = {
            "rho_E9_NiS_precip": {
                "S_Ni": "-1",
                "X_NiS": "1",
            },
            "rho_E9_NiS_dissolv": {
                "S_Ni": "1",
                "X_NiS": "-1",
            },
            "rho_E9_CoS_precip": {
                "S_Co": "-1",
                "X_CoS": "1",
            },
            "rho_E9_CoS_dissolv": {
                "S_Co": "1",
                "X_CoS": "-1",
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
            validate_hook=self._validate,
        )

    def _rates(self, state: Mapping[str, float], params: Mapping[str, float]) -> dict[str, float]:
        s_ni = max(float(state.get("S_Ni", 0.0)), 0.0)
        s_cob = max(float(state.get("S_Co", 0.0)), 0.0)  # cobalt (Co ≠ CO)
        x_nis = max(float(state.get("X_NiS", 0.0)), 0.0)
        x_cos = max(float(state.get("X_CoS", 0.0)), 0.0)
        # S_H2S from E4 (srb); 0 if not present → no sulfide precipitation
        s_h2s = max(float(state.get("S_H2S", 0.0)), 0.0)

        # --- NiS precipitation/dissolution (IP = [Ni][S²⁻] / Ksp_NiS) ---
        ip_nis = (s_ni * s_h2s) / max(float(params["Ksp_NiS"]), 1e-50)
        rho_nis_p = float(params["k_precip_NiS"]) * max(ip_nis - 1.0, 0.0) * s_ni
        rho_nis_d = float(params["k_dissolv_NiS"]) * max(1.0 - ip_nis, 0.0) * x_nis

        # --- CoS precipitation/dissolution ---
        ip_cos = (s_cob * s_h2s) / max(float(params["Ksp_CoS"]), 1e-50)
        rho_cos_p = float(params["k_precip_CoS"]) * max(ip_cos - 1.0, 0.0) * s_cob
        rho_cos_d = float(params["k_dissolv_CoS"]) * max(1.0 - ip_cos, 0.0) * x_cos

        return {
            "rho_E9_NiS_precip": rho_nis_p,
            "rho_E9_NiS_dissolv": rho_nis_d,
            "rho_E9_CoS_precip": rho_cos_p,
            "rho_E9_CoS_dissolv": rho_cos_d,
        }

    def _inhibition(self, state: Mapping[str, float], params: Mapping[str, float]) -> dict[str, float]:
        """Monod-type trace element limitation on acetoclastic and hydrogenotrophic methanogens.

        Thanh et al. 2016 (Chem Eng J 291:106–117) — Eq. 7:
            I_TE = S_TE / (K_TE + S_TE)

        All three metals (Ni, Co, Fe) are combined multiplicatively per process.
        Fe is a fixed parameter (S_Fe2_TE_feed); Ni and Co are dynamic states.
        """
        s_ni = max(float(state.get("S_Ni", 0.0)), 0.0)
        s_cob = max(float(state.get("S_Co", 0.0)), 0.0)  # cobalt
        s_fe2 = float(params.get("S_Fe2_TE_feed", 5e-5))

        k_ni_ac = float(params.get("K_TE_Ni_ac", 5e-7))
        k_ni_h2 = float(params.get("K_TE_Ni_h2", 5e-7))
        k_co_ac = float(params.get("K_TE_Co_ac", 1e-7))
        k_co_h2 = float(params.get("K_TE_Co_h2", 1e-7))
        k_fe_ac = float(params.get("K_TE_Fe_ac", 1e-6))

        # Ni limitation
        i_ni_ac = s_ni / (k_ni_ac + s_ni + 1e-30)
        i_ni_h2 = s_ni / (k_ni_h2 + s_ni + 1e-30)
        # Co (cobalt) limitation
        i_co_ac = s_cob / (k_co_ac + s_cob + 1e-30)
        i_co_h2 = s_cob / (k_co_h2 + s_cob + 1e-30)
        # Fe limitation (static parameter)
        i_fe_ac = s_fe2 / (k_fe_ac + s_fe2 + 1e-30)

        return {
            "rho_11_uptake_acetate": i_ni_ac * i_co_ac * i_fe_ac,
            "rho_12_uptake_hydrogen": i_ni_h2 * i_co_h2,
        }

    def _diagnostics(
        self,
        matrix: np.ndarray,
        assembly: FullModelAssembly,
        params: Mapping[str, float],
    ) -> dict[str, list[float]]:
        s_ni = np.clip(matrix[:, assembly.full_state_index["S_Ni"]], 0.0, None)
        s_cob = np.clip(matrix[:, assembly.full_state_index["S_Co"]], 0.0, None)
        x_nis = np.clip(matrix[:, assembly.full_state_index["X_NiS"]], 0.0, None)
        x_cos = np.clip(matrix[:, assembly.full_state_index["X_CoS"]], 0.0, None)

        # Bioavailability fractions
        ni_total = s_ni + x_nis
        co_total = s_cob + x_cos
        ni_avail = np.where(ni_total > 1e-20, s_ni / ni_total, 1.0)
        co_avail = np.where(co_total > 1e-20, s_cob / co_total, 1.0)

        # Limitation factor for X_ac
        k_ni_ac = float(params.get("K_TE_Ni_ac", 5e-7))
        k_co_ac = float(params.get("K_TE_Co_ac", 1e-7))
        k_fe_ac = float(params.get("K_TE_Fe_ac", 1e-6))
        s_fe2 = float(params.get("S_Fe2_TE_feed", 5e-5))
        i_ni_ac = s_ni / (k_ni_ac + s_ni + 1e-30)
        i_co_ac = s_cob / (k_co_ac + s_cob + 1e-30)
        i_fe_ac = s_fe2 / (k_fe_ac + s_fe2 + 1e-30)
        combined_lim_ac = i_ni_ac * i_co_ac * i_fe_ac

        # Saturation indices (only meaningful if E4 active)
        if "S_H2S" in assembly.full_state_index:
            s_h2s = np.clip(matrix[:, assembly.full_state_index["S_H2S"]], 0.0, None)
        else:
            s_h2s = np.zeros(len(s_ni))
        ip_nis = (s_ni * s_h2s) / max(float(params["Ksp_NiS"]), 1e-50)
        ip_cos = (s_cob * s_h2s) / max(float(params["Ksp_CoS"]), 1e-50)

        return {
            "S_Ni": s_ni.astype(float).tolist(),
            "S_Co_metal": s_cob.astype(float).tolist(),
            "X_NiS": x_nis.astype(float).tolist(),
            "X_CoS": x_cos.astype(float).tolist(),
            "Ni_bioavailability": ni_avail.astype(float).tolist(),
            "Co_bioavailability": co_avail.astype(float).tolist(),
            "TE_limitation_X_ac": combined_lim_ac.astype(float).tolist(),
            "IP_NiS": np.clip(ip_nis, 0.0, None).astype(float).tolist(),
            "IP_CoS": np.clip(ip_cos, 0.0, None).astype(float).tolist(),
        }

    def _validate(self, assembly: FullModelAssembly) -> None:
        """E9 cannot be combined with E8 (iron) in v1 — both would need S_Fe2 state."""
        if "iron" in set(assembly.active_extensions):
            raise ValueError(
                "E9 (trace_elements) não é compatível com E8 (iron) em v1: "
                "E8 adiciona S_Fe2 (ciclo completo do ferro). "
                "Use E9 sozinho para limitação por Ni/Co/Fe, ou E8 para dinâmica completa de Fe. "
                "Combinação E8+E9 está planejada para v2."
            )


TRACE_ELEMENTS_EXTENSION = _TraceElementsExtension()
