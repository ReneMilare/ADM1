"""E9 - Elementos-traço (Ni, Co, Fe) com precipitação/dissolução e bioavailability proxy.

This corrective implementation extends the original v1 so that:
- Ni and Co limitation uses free-metal proxies rather than total dissolved metal.
- Fe(II) is tracked as a dynamic state ``S_Fe2_te`` within E9.
- FeS and FeCO3 precipitation/dissolution are represented explicitly.
- Sulfide consumption is written to stoichiometry only when E4 (srb) is active.
- E8 (iron) remains incompatible to avoid overlapping iron chemistries.

The local literature base is broader than what is implemented here. The full papers model
multiple phosphates, carbonates, sulfides and explicit complexed species. This project keeps a
reduced but literature-aligned subset focused on the corrective plan:
- Maharaj et al. (2018): precipitation/dissolution of Ni, Co, Fe carbonates/sulfides.
- Maharaj et al. (2019): complexation increases soluble/bioavailable TE fractions.
- Thanh et al. (2016): methanogens are the most TE-sensitive groups; Ni/Co/Fe limitation affects
  acetoclastic and hydrogenotrophic methanogenesis.
"""
from __future__ import annotations

from typing import Mapping

import numpy as np

from simulator.full_model.assembly import FullModelAssembly
from simulator.full_model.catalog_types import ParameterDefinition, ProcessDefinition, StateDefinition
from simulator.full_model.extensions import FullModelExtensionContribution
from simulator.full_model.units import DAY_INV, DIMENSIONLESS, KG_COD_M3, KMOL_M3

_SRC = (
    "Maharaj et al. (2018) Bioresour Technol 267:666-676 doi:10.1016/j.biortech.2018.06.099; "
    "Maharaj et al. (2019) Bioresour Technol 287:121472 doi:10.1016/j.biortech.2018.12.064; "
    "Thanh et al. (2016) Chem Eng J 307:1149-1161 doi:10.1016/j.cej.2016.08.088; "
    "Thanh et al. (2015) Biotechnol Adv 34:122-136 doi:10.1016/j.biotechadv.2015.12.006"
)
_KMOL_NI_M3 = "kmolNi/m3"
_KMOL_CO_M3 = "kmolCo/m3"
_KMOL_FE_M3 = "kmolFe/m3"


class _TraceElementsExtension:
    name = "trace_elements"
    description = (
        "E9: Ni/Co/Fe com bioavailability proxy, precipitação/dissolução de sulfetos e FeCO3, "
        "e limitação de X_ac/X_h2 por metais-traço livres."
    )

    def contribute(self) -> FullModelExtensionContribution:
        states = (
            StateDefinition(
                name="S_Ni",
                description="Níquel dissolvido total (livre + complexado) em fase líquida.",
                unit=_KMOL_NI_M3,
                phase="liquid",
                domain="soluble",
                role="dynamic",
                cod_role="non_cod",
                elemental_proxy=None,
                source=_SRC,
                notes="O termo livre é estimado via proxy de complexação com S_DOM_TE.",
            ),
            StateDefinition(
                name="S_Co",
                description="Cobalto dissolvido total (livre + complexado) em fase líquida.",
                unit=_KMOL_CO_M3,
                phase="liquid",
                domain="soluble",
                role="dynamic",
                cod_role="non_cod",
                elemental_proxy=None,
                source=_SRC,
                notes="Co = cobalt metal. Não confundir com S_CO da extensão syngas.",
            ),
            StateDefinition(
                name="S_Fe2_te",
                description="Fe(II) dissolvido associado à extensão E9.",
                unit=_KMOL_FE_M3,
                phase="liquid",
                domain="soluble",
                role="dynamic",
                cod_role="non_cod",
                elemental_proxy=None,
                source=_SRC,
                notes="Estado próprio de E9 para evitar conflito de nomenclatura com E8.",
            ),
            StateDefinition(
                name="X_NiS",
                description="NiS precipitado (fase sólida, indisponível biologicamente).",
                unit=_KMOL_NI_M3,
                phase="solid",
                domain="precipitate",
                role="dynamic",
                cod_role="non_cod",
                elemental_proxy=None,
                source=_SRC,
                notes="Sulfeto de Ni; precipitação governada por S_Ni livre e sulfeto dissolvido.",
            ),
            StateDefinition(
                name="X_CoS",
                description="CoS precipitado (fase sólida, indisponível biologicamente).",
                unit=_KMOL_CO_M3,
                phase="solid",
                domain="precipitate",
                role="dynamic",
                cod_role="non_cod",
                elemental_proxy=None,
                source=_SRC,
            ),
            StateDefinition(
                name="X_FeS_te",
                description="FeS precipitado dentro da extensão E9.",
                unit=_KMOL_FE_M3,
                phase="solid",
                domain="precipitate",
                role="dynamic",
                cod_role="non_cod",
                elemental_proxy=None,
                source=_SRC,
                notes="Representa o sumidouro principal de Fe na presença de sulfeto; distinto de X_FeS da E8.",
            ),
            StateDefinition(
                name="X_FeCO3",
                description="FeCO3 precipitado (siderita) dentro da extensão E9.",
                unit=_KMOL_FE_M3,
                phase="solid",
                domain="precipitate",
                role="dynamic",
                cod_role="non_cod",
                elemental_proxy=None,
                source=_SRC,
                notes="Representa a rota carbonatada dominante do ferro quando há supersaturação com carbonato.",
            ),
        )

        processes = (
            ProcessDefinition(
                name="rho_E9_NiS_precip",
                vendor_symbol="Rho_E9_1",
                family="biochemical",
                description="Precipitação de NiS.",
                rate_expression="computed_by_extension",
                affected_states=("S_Ni", "S_H2S", "X_NiS"),
                parameters=("k_precip_NiS", "Ksp_NiS", "K_c_Ni", "S_DOM_TE"),
                inhibitions=(),
                source=_SRC,
            ),
            ProcessDefinition(
                name="rho_E9_NiS_dissolv",
                vendor_symbol="Rho_E9_2",
                family="biochemical",
                description="Dissolução de NiS.",
                rate_expression="computed_by_extension",
                affected_states=("S_Ni", "S_H2S", "X_NiS"),
                parameters=("k_dissolv_NiS", "Ksp_NiS", "K_c_Ni", "S_DOM_TE"),
                inhibitions=(),
                source=_SRC,
            ),
            ProcessDefinition(
                name="rho_E9_CoS_precip",
                vendor_symbol="Rho_E9_3",
                family="biochemical",
                description="Precipitação de CoS.",
                rate_expression="computed_by_extension",
                affected_states=("S_Co", "S_H2S", "X_CoS"),
                parameters=("k_precip_CoS", "Ksp_CoS", "K_c_Co", "S_DOM_TE"),
                inhibitions=(),
                source=_SRC,
            ),
            ProcessDefinition(
                name="rho_E9_CoS_dissolv",
                vendor_symbol="Rho_E9_4",
                family="biochemical",
                description="Dissolução de CoS.",
                rate_expression="computed_by_extension",
                affected_states=("S_Co", "S_H2S", "X_CoS"),
                parameters=("k_dissolv_CoS", "Ksp_CoS", "K_c_Co", "S_DOM_TE"),
                inhibitions=(),
                source=_SRC,
            ),
            ProcessDefinition(
                name="rho_E9_FeS_precip",
                vendor_symbol="Rho_E9_5",
                family="biochemical",
                description="Precipitação de FeS dentro de E9.",
                rate_expression="computed_by_extension",
                affected_states=("S_Fe2_te", "S_H2S", "X_FeS_te"),
                parameters=("k_precip_FeS_te", "Ksp_FeS_te"),
                inhibitions=(),
                source=_SRC,
            ),
            ProcessDefinition(
                name="rho_E9_FeS_dissolv",
                vendor_symbol="Rho_E9_6",
                family="biochemical",
                description="Dissolução de FeS dentro de E9.",
                rate_expression="computed_by_extension",
                affected_states=("S_Fe2_te", "S_H2S", "X_FeS_te"),
                parameters=("k_dissolv_FeS_te", "Ksp_FeS_te"),
                inhibitions=(),
                source=_SRC,
            ),
            ProcessDefinition(
                name="rho_E9_FeCO3_precip",
                vendor_symbol="Rho_E9_7",
                family="biochemical",
                description="Precipitação de FeCO3 (siderita).",
                rate_expression="computed_by_extension",
                affected_states=("S_Fe2_te", "S_IC", "X_FeCO3"),
                parameters=("k_precip_FeCO3", "Ksp_FeCO3", "K_a_co2"),
                inhibitions=(),
                source=_SRC,
            ),
            ProcessDefinition(
                name="rho_E9_FeCO3_dissolv",
                vendor_symbol="Rho_E9_8",
                family="biochemical",
                description="Dissolução de FeCO3 (siderita).",
                rate_expression="computed_by_extension",
                affected_states=("S_Fe2_te", "S_IC", "X_FeCO3"),
                parameters=("k_dissolv_FeCO3", "Ksp_FeCO3", "K_a_co2"),
                inhibitions=(),
                source=_SRC,
            ),
        )

        parameters = (
            ParameterDefinition(
                name="S_Ni_feed",
                value=2.0e-6,
                unit=_KMOL_NI_M3,
                group="operating",
                classification="provisional",
                description="Referência de Ni no afluente.",
                source=_SRC,
                notes="O afluente real é configurado via influent_state_overrides em S_Ni.",
            ),
            ParameterDefinition(
                name="S_Co_feed",
                value=5.0e-7,
                unit=_KMOL_CO_M3,
                group="operating",
                classification="provisional",
                description="Referência de Co no afluente.",
                source=_SRC,
                notes="O afluente real é configurado via influent_state_overrides em S_Co.",
            ),
            ParameterDefinition(
                name="S_Fe2_te_feed",
                value=1.0e-5,
                unit=_KMOL_FE_M3,
                group="operating",
                classification="provisional",
                description="Referência de Fe(II) no afluente da E9.",
                source=_SRC,
                notes="O afluente real é configurado via influent_state_overrides em S_Fe2_te.",
            ),
            ParameterDefinition(
                name="S_DOM_TE",
                value=0.0,
                unit=KG_COD_M3,
                group="operating",
                classification="provisional",
                description="Proxy operacional de ligantes orgânicos solúveis que complexam Ni/Co.",
                source=_SRC,
                notes="0.0 desativa o proxy; use valores > 0 para simular maior complexação e retenção em fase líquida.",
            ),
            ParameterDefinition(
                name="K_c_Ni",
                value=27.54,
                unit="m3/kgCOD",
                group="physicochemical",
                classification="provisional",
                description="Constante proxy de complexação de Ni com ligantes orgânicos em equivalentes de acetato.",
                source=_SRC,
                notes="Âncora em Maharaj et al. (2019) Table 1: logK(Ni-Ac)=1.44, logo K≈10^1.44=27.54. Nesta v1 o valor é usado como proxy operacional em equivalentes de acetato para modular a fração livre via K_c_Ni * S_DOM_TE.",
            ),
            ParameterDefinition(
                name="K_c_Co",
                value=23.99,
                unit="m3/kgCOD",
                group="physicochemical",
                classification="provisional",
                description="Constante proxy de complexação de Co com ligantes orgânicos em equivalentes de acetato.",
                source=_SRC,
                notes="Âncora em Maharaj et al. (2019) Table 1: logK(Co-Ac)=1.38, logo K≈10^1.38=23.99. Nesta v1 o valor é usado como proxy operacional em equivalentes de acetato para modular a fração livre via K_c_Co * S_DOM_TE.",
            ),
            ParameterDefinition(
                name="Ksp_NiS",
                value=2.0e-21,
                unit="(kmol/m3)^2",
                group="physicochemical",
                classification="canonical",
                description="Produto de solubilidade do NiS amorfo.",
                source=_SRC,
                notes="pKsp ≈ 20.7 no paper local de precipitação/dissolução.",
            ),
            ParameterDefinition(
                name="Ksp_CoS",
                value=5.0e-21,
                unit="(kmol/m3)^2",
                group="physicochemical",
                classification="canonical",
                description="Produto de solubilidade do CoS amorfo.",
                source=_SRC,
                notes="pKsp ≈ 20.3 no paper local de precipitação/dissolução.",
            ),
            ParameterDefinition(
                name="Ksp_FeS_te",
                value=1.0e-18,
                unit="(kmol/m3)^2",
                group="physicochemical",
                classification="canonical",
                description="Produto de solubilidade do FeS amorfo usado em E9.",
                source=_SRC,
                notes="pKsp ≈ 18.0 no paper local de precipitação/dissolução.",
            ),
            ParameterDefinition(
                name="Ksp_FeCO3",
                value=2.57e-11,
                unit="(kmol/m3)^2",
                group="physicochemical",
                classification="canonical",
                description="Produto de solubilidade do FeCO3 (siderita).",
                source=_SRC,
                notes="pKsp ≈ 10.59 no paper local de precipitação/dissolução.",
            ),
            ParameterDefinition(
                name="k_precip_NiS",
                value=100.0,
                unit=DAY_INV,
                group="biochemical",
                classification="provisional",
                description="Cinética efetiva de precipitação de NiS.",
                source=_SRC,
            ),
            ParameterDefinition(
                name="k_dissolv_NiS",
                value=0.5,
                unit=DAY_INV,
                group="biochemical",
                classification="provisional",
                description="Cinética efetiva de dissolução de NiS.",
                source=_SRC,
            ),
            ParameterDefinition(
                name="k_precip_CoS",
                value=80.0,
                unit=DAY_INV,
                group="biochemical",
                classification="provisional",
                description="Cinética efetiva de precipitação de CoS.",
                source=_SRC,
                notes="Mantida levemente abaixo de NiS para refletir a solubilidade um pouco maior de CoS no paper local.",
            ),
            ParameterDefinition(
                name="k_dissolv_CoS",
                value=0.5,
                unit=DAY_INV,
                group="biochemical",
                classification="provisional",
                description="Cinética efetiva de dissolução de CoS.",
                source=_SRC,
            ),
            ParameterDefinition(
                name="k_precip_FeS_te",
                value=200.0,
                unit=DAY_INV,
                group="biochemical",
                classification="provisional",
                description="Cinética efetiva de precipitação de FeS em E9.",
                source=_SRC,
                notes="FeS é o sumidouro sulfetado dominante de Fe e um importante mitigador de H2S.",
            ),
            ParameterDefinition(
                name="k_dissolv_FeS_te",
                value=1.0,
                unit=DAY_INV,
                group="biochemical",
                classification="provisional",
                description="Cinética efetiva de dissolução de FeS em E9.",
                source=_SRC,
            ),
            ParameterDefinition(
                name="k_precip_FeCO3",
                value=25.0,
                unit=DAY_INV,
                group="biochemical",
                classification="provisional",
                description="Cinética efetiva de precipitação de FeCO3.",
                source=_SRC,
            ),
            ParameterDefinition(
                name="k_dissolv_FeCO3",
                value=0.2,
                unit=DAY_INV,
                group="biochemical",
                classification="provisional",
                description="Cinética efetiva de dissolução de FeCO3.",
                source=_SRC,
            ),
            ParameterDefinition(
                name="K_TE_Ni_ac",
                value=5.0e-7,
                unit=_KMOL_NI_M3,
                group="biochemical",
                classification="provisional",
                description="Meia-saturação de Ni livre para acetoclásticos.",
                source=_SRC,
            ),
            ParameterDefinition(
                name="K_TE_Ni_h2",
                value=5.0e-7,
                unit=_KMOL_NI_M3,
                group="biochemical",
                classification="provisional",
                description="Meia-saturação de Ni livre para hidrogenotróficos.",
                source=_SRC,
            ),
            ParameterDefinition(
                name="K_TE_Co_ac",
                value=1.0e-7,
                unit=_KMOL_CO_M3,
                group="biochemical",
                classification="provisional",
                description="Meia-saturação de Co livre para acetoclásticos.",
                source=_SRC,
            ),
            ParameterDefinition(
                name="K_TE_Co_h2",
                value=1.0e-7,
                unit=_KMOL_CO_M3,
                group="biochemical",
                classification="provisional",
                description="Meia-saturação de Co livre para hidrogenotróficos.",
                source=_SRC,
            ),
            ParameterDefinition(
                name="K_TE_Fe_ac",
                value=1.0e-6,
                unit=_KMOL_FE_M3,
                group="biochemical",
                classification="provisional",
                description="Meia-saturação de Fe(II) para acetoclásticos.",
                source=_SRC,
            ),
            ParameterDefinition(
                name="K_TE_Fe_h2",
                value=1.0e-6,
                unit=_KMOL_FE_M3,
                group="biochemical",
                classification="provisional",
                description="Meia-saturação de Fe(II) para hidrogenotróficos.",
                source=_SRC,
            ),
        )

        biochemical_stoichiometry_rows = {
            "rho_E9_NiS_precip": {"S_Ni": "-1", "X_NiS": "1"},
            "rho_E9_NiS_dissolv": {"S_Ni": "1", "X_NiS": "-1"},
            "rho_E9_CoS_precip": {"S_Co": "-1", "X_CoS": "1"},
            "rho_E9_CoS_dissolv": {"S_Co": "1", "X_CoS": "-1"},
            "rho_E9_FeS_precip": {"S_Fe2_te": "-1", "X_FeS_te": "1"},
            "rho_E9_FeS_dissolv": {"S_Fe2_te": "1", "X_FeS_te": "-1"},
            "rho_E9_FeCO3_precip": {"S_Fe2_te": "-1", "S_IC": "-1", "X_FeCO3": "1"},
            "rho_E9_FeCO3_dissolv": {"S_Fe2_te": "1", "S_IC": "1", "X_FeCO3": "-1"},
        }
        conditional_stoichiometry_patches = {
            "srb": {
                "rho_E9_NiS_precip": {"S_H2S": "-1"},
                "rho_E9_NiS_dissolv": {"S_H2S": "1"},
                "rho_E9_CoS_precip": {"S_H2S": "-1"},
                "rho_E9_CoS_dissolv": {"S_H2S": "1"},
                "rho_E9_FeS_precip": {"S_H2S": "-1"},
                "rho_E9_FeS_dissolv": {"S_H2S": "1"},
            }
        }

        return FullModelExtensionContribution(
            states=states,
            processes=processes,
            parameters=parameters,
            biochemical_stoichiometry_rows=biochemical_stoichiometry_rows,
            conditional_stoichiometry_patches=conditional_stoichiometry_patches,
            rate_function=self._rates,
            diagnostics_hook=self._diagnostics,
            inhibition_hook=self._inhibition,
            validate_hook=self._validate,
        )

    @staticmethod
    def _free_fraction(total_conc: float, k_complex: float, s_dom: float) -> float:
        if total_conc <= 0.0:
            return 0.0
        alpha = 1.0 / (1.0 + max(k_complex, 0.0) * max(s_dom, 0.0))
        return total_conc * alpha

    @staticmethod
    def _carbonate_concentration(s_ic: float, s_h_ion: float, ka_co2: float) -> float:
        ka_hco3 = 4.68e-11
        s_hco3 = ka_co2 * max(s_ic, 0.0) / max(ka_co2 + s_h_ion, 1e-30)
        return ka_hco3 * s_hco3 / max(s_h_ion, 1e-14)

    def _rates(self, state: Mapping[str, float], params: Mapping[str, float]) -> dict[str, float]:
        s_ni = max(float(state.get("S_Ni", 0.0)), 0.0)
        s_co = max(float(state.get("S_Co", 0.0)), 0.0)
        s_fe2 = max(float(state.get("S_Fe2_te", 0.0)), 0.0)
        x_nis = max(float(state.get("X_NiS", 0.0)), 0.0)
        x_cos = max(float(state.get("X_CoS", 0.0)), 0.0)
        x_fes = max(float(state.get("X_FeS_te", 0.0)), 0.0)
        x_feco3 = max(float(state.get("X_FeCO3", 0.0)), 0.0)
        s_h2s = max(float(state.get("S_H2S", 0.0)), 0.0)
        s_ic = max(float(state.get("S_IC", 0.0)), 0.0)
        s_h_ion = max(float(state.get("S_H_ion", 1e-7)), 1e-14)
        s_dom = max(float(params.get("S_DOM_TE", 0.0)), 0.0)

        s_ni_free = self._free_fraction(s_ni, float(params.get("K_c_Ni", 0.0)), s_dom)
        s_co_free = self._free_fraction(s_co, float(params.get("K_c_Co", 0.0)), s_dom)
        s_co3 = self._carbonate_concentration(s_ic, s_h_ion, float(params.get("K_a_co2", 4.47e-7)))

        ip_nis = (s_ni_free * s_h2s) / max(float(params["Ksp_NiS"]), 1e-30)
        ip_cos = (s_co_free * s_h2s) / max(float(params["Ksp_CoS"]), 1e-30)
        ip_fes = (s_fe2 * s_h2s) / max(float(params["Ksp_FeS_te"]), 1e-30)
        ip_feco3 = (s_fe2 * s_co3) / max(float(params["Ksp_FeCO3"]), 1e-30)

        rho_nis_p = float(params["k_precip_NiS"]) * max(ip_nis - 1.0, 0.0) * s_ni_free
        rho_nis_d = float(params["k_dissolv_NiS"]) * max(1.0 - ip_nis, 0.0) * x_nis
        rho_cos_p = float(params["k_precip_CoS"]) * max(ip_cos - 1.0, 0.0) * s_co_free
        rho_cos_d = float(params["k_dissolv_CoS"]) * max(1.0 - ip_cos, 0.0) * x_cos
        rho_fes_p = float(params["k_precip_FeS_te"]) * max(ip_fes - 1.0, 0.0) * s_fe2
        rho_fes_d = float(params["k_dissolv_FeS_te"]) * max(1.0 - ip_fes, 0.0) * x_fes
        rho_feco3_p = float(params["k_precip_FeCO3"]) * max(ip_feco3 - 1.0, 0.0) * s_fe2
        rho_feco3_d = float(params["k_dissolv_FeCO3"]) * max(1.0 - ip_feco3, 0.0) * x_feco3

        return {
            "rho_E9_NiS_precip": rho_nis_p,
            "rho_E9_NiS_dissolv": rho_nis_d,
            "rho_E9_CoS_precip": rho_cos_p,
            "rho_E9_CoS_dissolv": rho_cos_d,
            "rho_E9_FeS_precip": rho_fes_p,
            "rho_E9_FeS_dissolv": rho_fes_d,
            "rho_E9_FeCO3_precip": rho_feco3_p,
            "rho_E9_FeCO3_dissolv": rho_feco3_d,
        }

    def _inhibition(self, state: Mapping[str, float], params: Mapping[str, float]) -> dict[str, float]:
        s_dom = max(float(params.get("S_DOM_TE", 0.0)), 0.0)
        s_ni_free = self._free_fraction(float(state.get("S_Ni", 0.0)), float(params.get("K_c_Ni", 0.0)), s_dom)
        s_co_free = self._free_fraction(float(state.get("S_Co", 0.0)), float(params.get("K_c_Co", 0.0)), s_dom)
        s_fe2 = max(float(state.get("S_Fe2_te", 0.0)), 0.0)

        def _monod(s_value: float, k_value: float) -> float:
            return s_value / (max(k_value, 0.0) + s_value + 1e-30)

        i_ni_ac = _monod(s_ni_free, float(params.get("K_TE_Ni_ac", 5.0e-7)))
        i_ni_h2 = _monod(s_ni_free, float(params.get("K_TE_Ni_h2", 5.0e-7)))
        i_co_ac = _monod(s_co_free, float(params.get("K_TE_Co_ac", 1.0e-7)))
        i_co_h2 = _monod(s_co_free, float(params.get("K_TE_Co_h2", 1.0e-7)))
        i_fe_ac = _monod(s_fe2, float(params.get("K_TE_Fe_ac", 1.0e-6)))
        i_fe_h2 = _monod(s_fe2, float(params.get("K_TE_Fe_h2", 1.0e-6)))

        return {
            "rho_11_uptake_acetate": i_ni_ac * i_co_ac * i_fe_ac,
            "rho_12_uptake_hydrogen": i_ni_h2 * i_co_h2 * i_fe_h2,
        }

    def _diagnostics(
        self,
        matrix: np.ndarray,
        assembly: FullModelAssembly,
        params: Mapping[str, float],
    ) -> dict[str, list[float]]:
        s_ni = np.clip(matrix[:, assembly.full_state_index["S_Ni"]], 0.0, None)
        s_co = np.clip(matrix[:, assembly.full_state_index["S_Co"]], 0.0, None)
        s_fe2 = np.clip(matrix[:, assembly.full_state_index["S_Fe2_te"]], 0.0, None)
        x_nis = np.clip(matrix[:, assembly.full_state_index["X_NiS"]], 0.0, None)
        x_cos = np.clip(matrix[:, assembly.full_state_index["X_CoS"]], 0.0, None)
        x_fes = np.clip(matrix[:, assembly.full_state_index["X_FeS_te"]], 0.0, None)
        x_feco3 = np.clip(matrix[:, assembly.full_state_index["X_FeCO3"]], 0.0, None)
        s_ic = np.clip(matrix[:, assembly.full_state_index["S_IC"]], 0.0, None)
        s_h_ion = np.clip(matrix[:, assembly.full_state_index["S_H_ion"]], 1e-14, None)
        s_h2s = (
            np.clip(matrix[:, assembly.full_state_index["S_H2S"]], 0.0, None)
            if "S_H2S" in assembly.full_state_index
            else np.zeros(len(s_ni), dtype=float)
        )

        s_dom = max(float(params.get("S_DOM_TE", 0.0)), 0.0)
        alpha_ni = 1.0 / (1.0 + max(float(params.get("K_c_Ni", 0.0)), 0.0) * s_dom)
        alpha_co = 1.0 / (1.0 + max(float(params.get("K_c_Co", 0.0)), 0.0) * s_dom)
        s_ni_free = s_ni * alpha_ni
        s_co_free = s_co * alpha_co
        ni_free_ratio = np.divide(s_ni_free, s_ni, out=np.zeros_like(s_ni_free), where=s_ni > 1e-30)
        co_free_ratio = np.divide(s_co_free, s_co, out=np.zeros_like(s_co_free), where=s_co > 1e-30)
        ni_complex = np.where(s_ni > 1e-30, 1.0 - ni_free_ratio, 0.0)
        co_complex = np.where(s_co > 1e-30, 1.0 - co_free_ratio, 0.0)

        ka_co2 = float(params.get("K_a_co2", 4.47e-7))
        ka_hco3 = 4.68e-11
        s_hco3 = ka_co2 * s_ic / np.maximum(ka_co2 + s_h_ion, 1e-30)
        s_co3 = ka_hco3 * s_hco3 / np.maximum(s_h_ion, 1e-14)

        ip_nis = s_ni_free * s_h2s / max(float(params["Ksp_NiS"]), 1e-30)
        ip_cos = s_co_free * s_h2s / max(float(params["Ksp_CoS"]), 1e-30)
        ip_fes = s_fe2 * s_h2s / max(float(params["Ksp_FeS_te"]), 1e-30)
        ip_feco3 = s_fe2 * s_co3 / max(float(params["Ksp_FeCO3"]), 1e-30)

        def _monod(series: np.ndarray, k_value: float) -> np.ndarray:
            return series / (k_value + series + 1e-30)

        te_lim_ac = (
            _monod(s_ni_free, float(params.get("K_TE_Ni_ac", 5.0e-7)))
            * _monod(s_co_free, float(params.get("K_TE_Co_ac", 1.0e-7)))
            * _monod(s_fe2, float(params.get("K_TE_Fe_ac", 1.0e-6)))
        )
        te_lim_h2 = (
            _monod(s_ni_free, float(params.get("K_TE_Ni_h2", 5.0e-7)))
            * _monod(s_co_free, float(params.get("K_TE_Co_h2", 1.0e-7)))
            * _monod(s_fe2, float(params.get("K_TE_Fe_h2", 1.0e-6)))
        )

        ni_total_pool = s_ni + x_nis
        co_total_pool = s_co + x_cos
        fe_total_pool = s_fe2 + x_fes + x_feco3
        ni_bio = np.divide(s_ni_free, ni_total_pool, out=np.zeros_like(s_ni_free), where=ni_total_pool > 1e-30)
        co_bio = np.divide(s_co_free, co_total_pool, out=np.zeros_like(s_co_free), where=co_total_pool > 1e-30)
        fe_bio = np.divide(s_fe2, fe_total_pool, out=np.zeros_like(s_fe2), where=fe_total_pool > 1e-30)

        return {
            "S_Ni": s_ni.astype(float).tolist(),
            "S_Ni_free": s_ni_free.astype(float).tolist(),
            "S_Co": s_co.astype(float).tolist(),
            "S_Co_free": s_co_free.astype(float).tolist(),
            "S_Fe2_te": s_fe2.astype(float).tolist(),
            "X_NiS": x_nis.astype(float).tolist(),
            "X_CoS": x_cos.astype(float).tolist(),
            "X_FeS_te": x_fes.astype(float).tolist(),
            "X_FeCO3": x_feco3.astype(float).tolist(),
            "Ni_complexation_fraction": np.clip(ni_complex, 0.0, 1.0).astype(float).tolist(),
            "Co_complexation_fraction": np.clip(co_complex, 0.0, 1.0).astype(float).tolist(),
            "Ni_bioavailability": np.clip(ni_bio, 0.0, 1.0).astype(float).tolist(),
            "Co_bioavailability": np.clip(co_bio, 0.0, 1.0).astype(float).tolist(),
            "Fe_bioavailability": np.clip(fe_bio, 0.0, 1.0).astype(float).tolist(),
            "TE_limitation_X_ac": np.clip(te_lim_ac, 0.0, 1.0).astype(float).tolist(),
            "TE_limitation_X_h2": np.clip(te_lim_h2, 0.0, 1.0).astype(float).tolist(),
            "IP_NiS": np.clip(ip_nis, 0.0, None).astype(float).tolist(),
            "IP_CoS": np.clip(ip_cos, 0.0, None).astype(float).tolist(),
            "IP_FeS": np.clip(ip_fes, 0.0, None).astype(float).tolist(),
            "IP_FeCO3": np.clip(ip_feco3, 0.0, None).astype(float).tolist(),
        }

    def _validate(self, assembly: FullModelAssembly) -> None:
        if "iron" in set(assembly.active_extensions):
            raise ValueError(
                "E9 (trace_elements) não pode ser combinado com E8 (iron): ambos introduzem "
                "química de Fe com precipitação própria. Use E9 para Ni/Co/Fe simplificado ou E8 para o ciclo de ferro dedicado."
            )


TRACE_ELEMENTS_EXTENSION = _TraceElementsExtension()
