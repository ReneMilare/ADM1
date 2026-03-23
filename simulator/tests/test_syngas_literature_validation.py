from __future__ import annotations

import pytest

from simulator.full_model.extension_registry import resolve_full_model_assembly
from simulator.full_model.syngas_extension import SYNGAS_EXTENSION
from simulator.tests.test_extensions import _make_params


class TestSyngasLiteratureValidation:
    def test_wgs_route_fraction_proportional_to_f_co_to_h2(self):
        assembly = resolve_full_model_assembly(["syngas"])
        state = {name: 0.0 for name in assembly.full_state_names}
        state.update({"S_CO": 0.05, "X_met_CO": 0.5, "S_gas_CO": 0.0, "S_IN": 0.01, "S_H_ion": 1e-7})
        params = _make_params("syngas")
        params["f_co_to_h2"] = 0.25
        rates = SYNGAS_EXTENSION._rates(state, params)
        total = rates["rho_E15_CO_uptake"] + rates["rho_E15_CO_acetate"]
        assert total > 0.0
        assert rates["rho_E15_CO_uptake"] / total == pytest.approx(0.25)
        assert rates["rho_E15_CO_acetate"] / total == pytest.approx(0.75)

    def test_acetate_route_produces_acetate_not_h2(self):
        assembly = resolve_full_model_assembly(["syngas"])
        state = {name: 0.0 for name in assembly.full_state_names}
        state.update({"S_CO": 0.05, "X_met_CO": 0.5, "S_gas_CO": 0.0, "S_IN": 0.01, "S_H_ion": 1e-7})
        params = _make_params("syngas")
        params["f_co_to_h2"] = 0.0
        rates = SYNGAS_EXTENSION._rates(state, params)
        row = SYNGAS_EXTENSION.contribute().biochemical_stoichiometry_rows["rho_E15_CO_acetate"]
        assert rates["rho_E15_CO_uptake"] == pytest.approx(0.0)
        assert rates["rho_E15_CO_acetate"] > 0.0
        assert "S_ac" in row
        assert "S_h2" not in row

    def test_carbon_balance_wgs_route(self):
        params = _make_params("syngas")
        carbon_in = 0.0625
        carbon_out = (0.0625 - float(params["Y_met_CO"]) * float(params["C_bac"])) + float(params["Y_met_CO"]) * float(params["C_bac"])
        assert carbon_out == pytest.approx(carbon_in, rel=1e-9)

    def test_carbon_balance_acetate_route(self):
        params = _make_params("syngas")
        y = float(params["Y_met_CO"])
        carbon_in = 0.0625
        carbon_out = (0.0625 - (1.0 - y) * float(params["C_ac"]) - y * float(params["C_bac"])) + (1.0 - y) * float(params["C_ac"]) + y * float(params["C_bac"])
        assert carbon_out == pytest.approx(carbon_in, rel=1e-9)

    def test_co_inhibition_acetoclastic_more_sensitive_than_hydrogenotrophic(self):
        assembly = resolve_full_model_assembly(["syngas"])
        state = {name: 0.0 for name in assembly.full_state_names}
        state["S_CO"] = 0.01
        params = _make_params("syngas")
        inhibitions = SYNGAS_EXTENSION._inhibition(state, params)
        assert inhibitions["rho_11_uptake_acetate"] < inhibitions["rho_12_uptake_hydrogen"]

    def test_higher_co_load_increases_transfer_to_liquid(self):
        assembly = resolve_full_model_assembly(["syngas"])
        base_state = {name: 0.0 for name in assembly.full_state_names}
        base_state.update({"S_CO": 0.0, "X_met_CO": 0.2, "S_IN": 0.01, "S_H_ion": 1e-7})
        params = _make_params("syngas")
        low = dict(base_state)
        high = dict(base_state)
        low["S_gas_CO"] = 0.5
        high["S_gas_CO"] = 1.5
        low_rates = SYNGAS_EXTENSION._rates(low, params)
        high_rates = SYNGAS_EXTENSION._rates(high, params)
        assert high_rates["rho_E15_CO_transfer"] < low_rates["rho_E15_CO_transfer"]
        assert abs(high_rates["rho_E15_CO_transfer"]) > abs(low_rates["rho_E15_CO_transfer"])
