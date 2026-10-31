"""E20 - Digestão anaeróbia de microalgas (Mairet et al. 2011).

Implements a dedicated algal particulate composite ``X_alg`` and couples it to the
ADM1 hydrolysis steps using the Contois-type hydrolysis formulation reported by
Mairet et al. (2011). The paper does not introduce new hydrolytic populations;
instead, the existing ADM1 hydrolysers (X_su, X_aa, X_fa) modulate hydrolysis of
carbohydrates, proteins and lipids through biomass-to-substrate ratios.

This extension keeps the practical ``X_alg`` feed state introduced in the project
and maps its disintegration products to the standard ADM1 particulate pools. Once
those pools are formed, the core hydrolysis processes ``rho_2``/``rho_3``/``rho_4``
are modified with Contois multipliers:

    rho_2 = k_hyd_ch * X_ch * X_su / (K_S_ch_alg * X_su + X_ch)
    rho_3 = k_hyd_pr * X_pr * X_aa / (K_S_pr_alg * X_aa + X_pr)
    rho_4 = k_hyd_li * X_li * X_fa / (K_S_li_alg * X_fa + X_li)

The base ADM1 rates already include ``k_hyd_* * X_*``. Therefore the extension
provides multiplicative factors equal to the biomass ratio term above.

Reference:
    Mairet F, Bernard O, Ras M, Lardon L, Steyer JP (2011).
    Modeling anaerobic digestion of microalgae using ADM1.
    Bioresource Technology 102(13):6823-6829. doi:10.1016/j.biortech.2011.04.015
"""
from __future__ import annotations

from typing import Mapping

import numpy as np

from simulator.full_model.assembly import FullModelAssembly
from simulator.full_model.catalog_types import ParameterDefinition, ProcessDefinition, StateDefinition
from simulator.full_model.extensions import FullModelExtensionContribution
from simulator.full_model.units import DAY_INV, DIMENSIONLESS, KG_COD_M3

_SRC = (
    "Mairet et al. (2011) Bioresour Technol 102:6823-6829 doi:10.1016/j.biortech.2011.04.015; "
    "Batstone et al. (2002) Water Sci Technol 45(10):65-73"
)


class _MicroalgaeExtension:
    name = "microalgae"
    description = (
        "E20: digestão de microalgas com X_alg, frações algais específicas e hidrólise "
        "tipo Contois em X_ch/X_pr/X_li conforme Mairet et al. (2011)."
    )

    def contribute(self) -> FullModelExtensionContribution:
        states = (
            StateDefinition(
                name="X_alg",
                description="Biomassa algal composta (kgCOD/m3).",
                unit=KG_COD_M3,
                phase="solid",
                domain="composite",
                role="dynamic",
                cod_role="cod",
                elemental_proxy="C_xc",
                source=_SRC,
                notes=(
                    "Estado de alimentação/estoque para biomassa algal. Disintegra em X_ch, X_pr, X_li, "
                    "X_I e S_I. Após a desintegração, a hidrólise segue o formalismo tipo Contois do artigo-base."
                ),
            ),
        )

        processes = (
            ProcessDefinition(
                name="rho_E20_dis_alg",
                vendor_symbol="Rho_E20_1",
                family="biochemical",
                description="Desintegração de X_alg para os pools particulados do ADM1.",
                rate_expression="computed_by_extension",
                affected_states=("X_alg", "X_ch", "X_pr", "X_li", "X_I", "S_I", "S_IN", "S_IC"),
                parameters=(
                    "k_dis_alg",
                    "f_wall_alg",
                    "f_ch_alg",
                    "f_pr_alg",
                    "f_li_alg",
                    "f_xI_alg",
                    "f_sI_alg",
                    "i_N_alg",
                ),
                inhibitions=(),
                source=_SRC,
                notes="Taxa = k_dis_alg * f_wall_alg * X_alg.",
            ),
        )

        parameters = (
            ParameterDefinition(
                name="k_dis_alg",
                value=0.25,
                unit=DAY_INV,
                group="biochemical",
                classification="calibrated",
                description="Taxa de desintegração de X_alg antes da recalcitrância de parede.",
                source=_SRC,
                notes="Parâmetro operacional do estado composto X_alg usado pelo projeto.",
            ),
            ParameterDefinition(
                name="f_wall_alg",
                value=0.70,
                unit=DIMENSIONLESS,
                group="biochemical",
                classification="calibrated",
                description="Fator de recalcitrância da parede celular aplicado a k_dis_alg.",
                source=_SRC,
                notes="1.0 = totalmente acessível; valores menores representam biomassa mais resistente.",
            ),
            ParameterDefinition(
                name="f_ch_alg",
                value=0.21,
                unit=DIMENSIONLESS,
                group="stoichiometric",
                classification="calibrated",
                description="Fração de carboidratos em X_alg que alimenta X_ch.",
                source=_SRC,
                notes="Valor padrão de Chlorella vulgaris em Mairet et al. (2011).",
            ),
            ParameterDefinition(
                name="f_pr_alg",
                value=0.50,
                unit=DIMENSIONLESS,
                group="stoichiometric",
                classification="calibrated",
                description="Fração proteica em X_alg que alimenta X_pr.",
                source=_SRC,
                notes="Valor padrão de Chlorella vulgaris em Mairet et al. (2011).",
            ),
            ParameterDefinition(
                name="f_li_alg",
                value=0.20,
                unit=DIMENSIONLESS,
                group="stoichiometric",
                classification="calibrated",
                description="Fração lipídica em X_alg que alimenta X_li.",
                source=_SRC,
            ),
            ParameterDefinition(
                name="f_xI_alg",
                value=0.07,
                unit=DIMENSIONLESS,
                group="stoichiometric",
                classification="calibrated",
                description="Fração inerte insolúvel em X_alg que alimenta X_I.",
                source=_SRC,
            ),
            ParameterDefinition(
                name="f_sI_alg",
                value=0.02,
                unit=DIMENSIONLESS,
                group="stoichiometric",
                classification="calibrated",
                description="Fração inerte solúvel em X_alg que alimenta S_I.",
                source=_SRC,
            ),
            ParameterDefinition(
                name="i_N_alg",
                value=0.06,
                unit="kgN/kgCOD",
                group="stoichiometric",
                classification="calibrated",
                description="Conteúdo de nitrogênio da biomassa algal composta.",
                source=_SRC,
                notes="Microalgas possuem teor proteico e nitrogênio muito maior que o resíduo municipal padrão do ADM1.",
            ),
            ParameterDefinition(
                name="k_hyd_ch",
                value=3.18,
                unit=DAY_INV,
                group="biochemical",
                classification="calibrated",
                description="Constante de hidrólise de carboidratos na formulação de Mairet et al. (2011).",
                source=_SRC,
                notes="Sobrescreve o valor ADM1 default quando E20 está ativo.",
            ),
            ParameterDefinition(
                name="k_hyd_pr",
                value=1.04,
                unit=DAY_INV,
                group="biochemical",
                classification="calibrated",
                description="Constante de hidrólise de proteínas na formulação de Mairet et al. (2011).",
                source=_SRC,
                notes="Sobrescreve o valor ADM1 default quando E20 está ativo.",
            ),
            ParameterDefinition(
                name="k_hyd_li",
                value=3.07,
                unit=DAY_INV,
                group="biochemical",
                classification="calibrated",
                description="Constante de hidrólise de lipídios na formulação de Mairet et al. (2011).",
                source=_SRC,
                notes="Sobrescreve o valor ADM1 default quando E20 está ativo.",
            ),
            ParameterDefinition(
                name="K_S_ch_alg",
                value=0.50,
                unit=KG_COD_M3,
                group="biochemical",
                classification="calibrated",
                description="Parâmetro de Contois para hidrólise de carboidratos de microalgas.",
                source=_SRC,
                notes="Tabela 4 de Mairet et al. (2011).",
            ),
            ParameterDefinition(
                name="K_S_pr_alg",
                value=0.26,
                unit=KG_COD_M3,
                group="biochemical",
                classification="calibrated",
                description="Parâmetro de Contois para hidrólise de proteínas de microalgas.",
                source=_SRC,
                notes="Tabela 4 de Mairet et al. (2011).",
            ),
            ParameterDefinition(
                name="K_S_li_alg",
                value=0.49,
                unit=KG_COD_M3,
                group="biochemical",
                classification="calibrated",
                description="Parâmetro de Contois para hidrólise de lipídios de microalgas.",
                source=_SRC,
                notes="Tabela 4 de Mairet et al. (2011).",
            ),
            ParameterDefinition(
                name="f_hyd_alg",
                value=1.0,
                unit=DIMENSIONLESS,
                group="biochemical",
                classification="provisional",
                description="Multiplicador opcional de calibração sobre o termo de Contois das hidrólises algais.",
                source=_SRC,
                notes="Mantido apenas como ajuste operacional; 1.0 preserva a forma literária do modelo.",
            ),
        )

        biochemical_stoichiometry_rows = {
            "rho_E20_dis_alg": {
                "X_alg": "-1",
                "X_ch": "f_ch_alg",
                "X_pr": "f_pr_alg",
                "X_li": "f_li_alg",
                "X_I": "f_xI_alg",
                "S_I": "f_sI_alg",
                "S_IN": "i_N_alg / 14 - f_pr_alg * N_aa - (f_xI_alg + f_sI_alg) * N_I",
                "S_IC": "C_xc - f_ch_alg * C_ch - f_pr_alg * C_pr - f_li_alg * C_li - (f_xI_alg + f_sI_alg) * C_xI",
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
            base_rate_modifier_hook=self._base_rate_modifier,
        )

    def _rates(self, state: Mapping[str, float], params: Mapping[str, float]) -> dict[str, float]:
        x_alg = max(float(state.get("X_alg", 0.0)), 0.0)
        rho_dis_alg = float(params["k_dis_alg"]) * float(params["f_wall_alg"]) * x_alg
        return {"rho_E20_dis_alg": rho_dis_alg}

    @staticmethod
    def _contois_factor(x_substrate: float, x_biomass: float, k_s: float, extra_factor: float) -> float:
        if x_biomass <= 0.0:
            return 0.0
        denominator = k_s * x_biomass + x_substrate
        if denominator <= 0.0:
            return 0.0
        return max(extra_factor, 0.0) * x_biomass / denominator

    def _base_rate_modifier(self, state: Mapping[str, float], params: Mapping[str, float]) -> dict[str, float]:
        x_ch = max(float(state.get("X_ch", 0.0)), 0.0)
        x_pr = max(float(state.get("X_pr", 0.0)), 0.0)
        x_li = max(float(state.get("X_li", 0.0)), 0.0)
        x_su = max(float(state.get("X_su", 0.0)), 0.0)
        x_aa = max(float(state.get("X_aa", 0.0)), 0.0)
        x_fa = max(float(state.get("X_fa", 0.0)), 0.0)
        f_hyd = float(params.get("f_hyd_alg", 1.0))
        return {
            "rho_2_hydrolysis_carbohydrates": self._contois_factor(x_ch, x_su, float(params["K_S_ch_alg"]), f_hyd),
            "rho_3_hydrolysis_proteins": self._contois_factor(x_pr, x_aa, float(params["K_S_pr_alg"]), f_hyd),
            "rho_4_hydrolysis_lipids": self._contois_factor(x_li, x_fa, float(params["K_S_li_alg"]), f_hyd),
        }

    def _diagnostics(
        self,
        matrix: np.ndarray,
        assembly: FullModelAssembly,
        params: Mapping[str, float],
    ) -> dict[str, list[float]]:
        x_alg = np.clip(matrix[:, assembly.full_state_index["X_alg"]], 0.0, None)
        x_ch = np.clip(matrix[:, assembly.full_state_index["X_ch"]], 0.0, None)
        x_pr = np.clip(matrix[:, assembly.full_state_index["X_pr"]], 0.0, None)
        x_li = np.clip(matrix[:, assembly.full_state_index["X_li"]], 0.0, None)
        x_su = np.clip(matrix[:, assembly.full_state_index["X_su"]], 0.0, None)
        x_aa = np.clip(matrix[:, assembly.full_state_index["X_aa"]], 0.0, None)
        x_fa = np.clip(matrix[:, assembly.full_state_index["X_fa"]], 0.0, None)
        s_in = np.clip(matrix[:, assembly.full_state_index["S_IN"]], 0.0, None)

        x_alg_0 = x_alg[0] if x_alg[0] > 1e-12 else 1.0
        alg_conversion = np.clip(1.0 - x_alg / x_alg_0, 0.0, 1.0)
        k_eff = float(params["k_dis_alg"]) * float(params["f_wall_alg"])
        k_eff_series = np.full(len(x_alg), k_eff)
        f_hyd = float(params.get("f_hyd_alg", 1.0))

        mod_ch = np.array(
            [self._contois_factor(float(xs), float(xb), float(params["K_S_ch_alg"]), f_hyd) for xs, xb in zip(x_ch, x_su)],
            dtype=float,
        )
        mod_pr = np.array(
            [self._contois_factor(float(xs), float(xb), float(params["K_S_pr_alg"]), f_hyd) for xs, xb in zip(x_pr, x_aa)],
            dtype=float,
        )
        mod_li = np.array(
            [self._contois_factor(float(xs), float(xb), float(params["K_S_li_alg"]), f_hyd) for xs, xb in zip(x_li, x_fa)],
            dtype=float,
        )

        return {
            "X_alg": x_alg.astype(float).tolist(),
            "X_alg_conversion": alg_conversion.astype(float).tolist(),
            "k_dis_alg_effective": k_eff_series.astype(float).tolist(),
            "hydrolysis_modifier_ch": mod_ch.tolist(),
            "hydrolysis_modifier_pr": mod_pr.tolist(),
            "hydrolysis_modifier_li": mod_li.tolist(),
            "S_IN": s_in.astype(float).tolist(),
        }

    def _validate(self, assembly: FullModelAssembly) -> None:
        defaults = {p.name: p.value for p in assembly.parameter_catalog}
        f_sum = sum(defaults.get(name, 0.0) for name in ("f_ch_alg", "f_pr_alg", "f_li_alg", "f_xI_alg", "f_sI_alg"))
        if abs(f_sum - 1.0) > 1e-3:
            raise ValueError(
                f"E20 (microalgae): frações algais somam {f_sum:.4f} != 1.0. "
                "Verifique f_ch_alg + f_pr_alg + f_li_alg + f_xI_alg + f_sI_alg."
            )


MICROALGAE_EXTENSION = _MicroalgaeExtension()
