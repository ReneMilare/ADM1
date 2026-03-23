from __future__ import annotations

import numpy as np
import pytest

from simulator.full_model.extension_registry import resolve_full_model_assembly
from simulator.full_model.trace_elements_extension import TRACE_ELEMENTS_EXTENSION
from simulator.tests.test_extensions import _make_params, _run_extension, _run_multi_extension


def _single_row_diagnostics(state: dict[str, float], params: dict[str, float]) -> dict[str, list[float]]:
    assembly = resolve_full_model_assembly(["trace_elements"])
    row = np.array([[state.get(name, 0.0) for name in assembly.full_state_names]], dtype=float)
    return TRACE_ELEMENTS_EXTENSION._diagnostics(row, assembly, params)


class TestTraceElementsLiteratureValidation:
    def test_ksp_nis_lower_than_ksp_cos(self):
        params = _make_params("trace_elements")
        assert float(params["Ksp_NiS"]) < float(params["Ksp_CoS"])

    def test_nis_precipitates_more_strongly_than_cos_under_equal_conditions(self):
        assembly = resolve_full_model_assembly(["trace_elements"])
        state = {name: 0.0 for name in assembly.full_state_names}
        state.update({"S_Ni": 1e-5, "S_Co": 1e-5, "S_H2S": 1e-3, "S_Fe2_te": 0.0, "S_H_ion": 1e-7})
        params = _make_params("trace_elements")
        rates = TRACE_ELEMENTS_EXTENSION._rates(state, params)
        assert rates["rho_E9_NiS_precip"] > rates["rho_E9_CoS_precip"]

    def test_ni_limitation_below_threshold(self):
        assembly = resolve_full_model_assembly(["trace_elements"])
        state = {name: 0.0 for name in assembly.full_state_names}
        state.update({"S_Ni": 1e-8, "S_Co": 5e-6, "S_Fe2_te": 5e-5})
        params = _make_params("trace_elements")
        inhibitions = TRACE_ELEMENTS_EXTENSION._inhibition(state, params)
        assert inhibitions["rho_11_uptake_acetate"] < 0.5

    def test_co_limitation_affects_acetoclastic(self):
        assembly = resolve_full_model_assembly(["trace_elements"])
        state = {name: 0.0 for name in assembly.full_state_names}
        state.update({"S_Ni": 5e-6, "S_Co": 1e-9, "S_Fe2_te": 5e-5})
        params = _make_params("trace_elements")
        inhibitions = TRACE_ELEMENTS_EXTENSION._inhibition(state, params)
        assert inhibitions["rho_11_uptake_acetate"] < 0.5

    def test_complexation_reduces_free_ni_fraction(self):
        params_lo = _make_params("trace_elements")
        params_hi = dict(params_lo)
        params_hi["S_DOM_TE"] = 1.0
        state = {"S_Ni": 2e-6, "S_Co": 5e-7, "S_Fe2_te": 1e-5, "S_IC": 0.04, "S_H_ion": 1e-7}
        diag_lo = _single_row_diagnostics(state, params_lo)
        diag_hi = _single_row_diagnostics(state, params_hi)
        assert diag_hi["S_Ni_free"][0] < diag_lo["S_Ni_free"][0]

    def test_bioavailability_decreases_with_precipitation(self):
        result = _run_multi_extension(
            ["srb", "trace_elements"],
            extra_initial={"S_H2S": 0.01, "S_Ni": 5e-5, "S_Co": 1e-5, "S_Fe2_te": 1e-4},
            extra_influent={"S_H2S": 0.0, "S_Ni": 0.0, "S_Co": 0.0, "S_Fe2_te": 0.0},
            hrt_days=500.0,
            duration_days=20.0,
        )
        assert result["profiles"]["Ni_bioavailability"][-1] < result["profiles"]["Ni_bioavailability"][0]

    def test_fe_dynamic_depletes_above_ksp_feco3(self):
        result = _run_extension(
            "trace_elements",
            extra_initial={"S_Fe2_te": 1e-4, "S_IC": 0.2},
            extra_influent={"S_Fe2_te": 0.0},
            hrt_days=500.0,
            duration_days=20.0,
        )
        assert result["profiles"]["S_Fe2_te"][-1] < result["profiles"]["S_Fe2_te"][0]
        assert result["profiles"]["IP_FeCO3"][0] > 1.0

    def test_fe_limitation_activates_below_threshold(self):
        assembly = resolve_full_model_assembly(["trace_elements"])
        state = {name: 0.0 for name in assembly.full_state_names}
        state.update({"S_Ni": 5e-6, "S_Co": 5e-6, "S_Fe2_te": 1e-8})
        params = _make_params("trace_elements")
        inhibitions = TRACE_ELEMENTS_EXTENSION._inhibition(state, params)
        assert inhibitions["rho_11_uptake_acetate"] < 0.5
        assert inhibitions["rho_12_uptake_hydrogen"] < 0.5
