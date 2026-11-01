from __future__ import annotations

import pytest
from scipy.integrate import trapezoid

from simulator.full_model.extension_registry import resolve_full_model_assembly
from simulator.full_model.kinetics import biochemical_rates
from simulator.tests.test_extensions import _make_params, _run_extensions


def _sin_release_coefficient(params: dict[str, float]) -> float:
    return float(params["i_N_alg"]) - float(params["f_pr_alg"]) * float(params["N_aa"]) - (
        float(params["f_xI_alg"]) + float(params["f_sI_alg"])
    ) * float(params["N_I"])


class TestMicroalgaeLiteratureValidation:
    def test_high_protein_microalgae_releases_more_sin(self):
        spirulina = dict(_make_params("microalgae"))
        spirulina.update({
            "f_ch_alg": 0.13,
            "f_pr_alg": 0.65,
            "f_li_alg": 0.13,
            "f_xI_alg": 0.07,
            "f_sI_alg": 0.02,
            "i_N_alg": 0.10,
        })
        scenedesmus = dict(_make_params("microalgae"))
        scenedesmus.update({
            "f_ch_alg": 0.29,
            "f_pr_alg": 0.42,
            "f_li_alg": 0.20,
            "f_xI_alg": 0.07,
            "f_sI_alg": 0.02,
            "i_N_alg": 0.07,
        })
        assert _sin_release_coefficient(spirulina) > _sin_release_coefficient(scenedesmus)

    def test_cell_wall_recalcitrance_reduces_methane_yield(self):
        totals = []
        for accessibility in (0.4, 0.9):
            result = _run_extensions(
                "microalgae", extra_initial={"X_alg": 1.0}, extra_influent={"X_alg": 0.0},
                parameter_overrides={"f_wall_alg": accessibility}, hrt_days=500.0,
                duration_days=30.0, evaluation_points=601,
            )
            totals.append(trapezoid(result["profiles"]["methane_m3_day"], result["time_days"]))
        assert totals[1] > totals[0]

    def test_nitrogen_balance_in_disintegration(self):
        params = _make_params("microalgae")
        released_sin = _sin_release_coefficient(params)
        recovered_n = released_sin + float(params["f_pr_alg"]) * float(params["N_aa"]) + (
            float(params["f_xI_alg"]) + float(params["f_sI_alg"])
        ) * float(params["N_I"])
        assert recovered_n == pytest.approx(float(params["i_N_alg"]), rel=1e-12, abs=1e-14)

    def test_disintegration_rate_in_range_mairet_2011(self):
        params = _make_params("microalgae")
        effective_k = float(params["k_dis_alg"]) * float(params["f_wall_alg"])
        assert 0.1 <= effective_k <= 0.5

    def test_hydrolysis_modifier_reduces_hydrolysis_rate(self):
        base_assembly = resolve_full_model_assembly([])
        micro_assembly = resolve_full_model_assembly(["microalgae"])

        common_state = {
            "S_su": 0.01,
            "S_aa": 0.01,
            "S_fa": 0.01,
            "S_va": 0.001,
            "S_bu": 0.001,
            "S_pro": 0.001,
            "S_ac": 0.20,
            "S_h2": 2e-7,
            "S_ch4": 0.055,
            "S_IC": 0.04,
            "S_IN": 0.01,
            "S_I": 0.02,
            "S_cation": 0.04,
            "S_anion": 0.02,
            "X_xc": 0.1,
            "X_ch": 0.8,
            "X_pr": 0.8,
            "X_li": 0.8,
            "X_su": 0.1,
            "X_aa": 0.1,
            "X_fa": 0.1,
            "X_c4": 0.5,
            "X_pro": 0.5,
            "X_ac": 1.5,
            "X_h2": 0.5,
            "X_I": 25.0,
            "S_gas_h2": 1e-5,
            "S_gas_ch4": 1.62,
            "S_gas_co2": 0.014,
        }
        base_state = {name: 0.0 for name in base_assembly.full_state_names}
        base_state.update(common_state)
        micro_state = {name: 0.0 for name in micro_assembly.full_state_names}
        micro_state.update(common_state)
        micro_state["X_alg"] = 0.5

        base_rates, _ = biochemical_rates(base_state, _make_params([]), assembly=base_assembly)
        micro_rates, _ = biochemical_rates(micro_state, _make_params("microalgae"), assembly=micro_assembly)

        assert micro_rates["rho_2_hydrolysis_carbohydrates"] < base_rates["rho_2_hydrolysis_carbohydrates"]
        assert micro_rates["rho_3_hydrolysis_proteins"] < base_rates["rho_3_hydrolysis_proteins"]
        assert micro_rates["rho_4_hydrolysis_lipids"] < base_rates["rho_4_hydrolysis_lipids"]
