from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Mapping

import numpy as np

from simulator.full_model.acid_base import AcidBaseState, solve_acid_base
from simulator.full_model.gas_transfer import GasTransferState, compute_gas_transfer
from simulator.full_model.kinetics import biochemical_rates
from simulator.full_model.model import FullModelInputs, FullModelState, assemble_full_state, build_numeric_biochemical_matrix, dynamic_state_dict


@dataclass(frozen=True, slots=True)
class FullStateEvaluation:
    full_state: FullModelState
    acid_base: AcidBaseState
    gas_transfer: GasTransferState
    rates: dict[str, float]
    inhibitions: dict[str, float]


class FullCSTRRhs:
    def __init__(self, *, inputs: FullModelInputs) -> None:
        self.inputs = inputs
        self.params = inputs.parameter_values
        self.assembly = inputs.assembly
        self.biochemical_matrix = build_numeric_biochemical_matrix(self.params, assembly=self.assembly)
        self._last_h_ion = float(inputs.initial_values.get("S_H_ion", 1e-7))

    def __call__(self, t: float, y: np.ndarray) -> np.ndarray:
        del t
        dynamic_values = dynamic_state_dict(y, assembly=self.assembly)
        evaluation = self.evaluate(dynamic_values=dynamic_values, use_cache=True)
        rate_vector = np.asarray([evaluation.rates[name] for name in self.assembly.biochemical_process_names], dtype=float)
        bio_dynamic = self.biochemical_matrix @ rate_vector
        derivatives = np.zeros(len(self.assembly.dynamic_state_names), dtype=float)
        q_over_v = self.params["q_ad"] / self.params["V_liq"]

        for state_name in self.assembly.dynamic_liquid_state_names:
            state_index = self.assembly.dynamic_state_index[state_name]
            derivatives[state_index] = q_over_v * (self.inputs.influent_values.get(state_name, 0.0) - dynamic_values[state_name]) + bio_dynamic[state_index]

        derivatives[self.assembly.dynamic_state_index["S_h2"]] -= evaluation.gas_transfer.rho_t8
        derivatives[self.assembly.dynamic_state_index["S_ch4"]] -= evaluation.gas_transfer.rho_t9
        derivatives[self.assembly.dynamic_state_index["S_IC"]] -= evaluation.gas_transfer.rho_t10
        derivatives[self.assembly.dynamic_state_index["S_gas_h2"]] = (
            -(evaluation.gas_transfer.q_gas / self.params["V_gas"]) * dynamic_values["S_gas_h2"]
            + evaluation.gas_transfer.rho_t8 * self.params["V_liq"] / self.params["V_gas"]
        )
        derivatives[self.assembly.dynamic_state_index["S_gas_ch4"]] = (
            -(evaluation.gas_transfer.q_gas / self.params["V_gas"]) * dynamic_values["S_gas_ch4"]
            + evaluation.gas_transfer.rho_t9 * self.params["V_liq"] / self.params["V_gas"]
        )
        derivatives[self.assembly.dynamic_state_index["S_gas_co2"]] = (
            -(evaluation.gas_transfer.q_gas / self.params["V_gas"]) * dynamic_values["S_gas_co2"]
            + evaluation.gas_transfer.rho_t10 * self.params["V_liq"] / self.params["V_gas"]
        )
        return derivatives

    def evaluate(self, *, dynamic_values: Mapping[str, float], use_cache: bool) -> FullStateEvaluation:
        acid_base = solve_acid_base(dynamic_values, self.params, initial_guess=self._last_h_ion if use_cache else None)
        if not acid_base.converged:
            logging.getLogger("adm1.full").warning(
                "pH solver não convergiu em %d iterações (último pH=%.3f)",
                acid_base.iterations,
                acid_base.p_h,
            )
        s_h2 = max(float(dynamic_values["S_h2"]), 0.0)
        full_state = assemble_full_state(
            dynamic_values,
            s_h2=s_h2,
            s_h_ion=acid_base.s_h_ion,
            acid_values={
                "S_va_ion": acid_base.s_va_ion,
                "S_bu_ion": acid_base.s_bu_ion,
                "S_pro_ion": acid_base.s_pro_ion,
                "S_ac_ion": acid_base.s_ac_ion,
                "S_hco3_ion": acid_base.s_hco3_ion,
                "S_co2": acid_base.s_co2,
                "S_nh3": acid_base.s_nh3,
                "S_nh4_ion": acid_base.s_nh4_ion,
            },
            assembly=self.assembly,
        )
        rates, inhibitions = biochemical_rates(full_state.values, self.params, assembly=self.assembly)
        gas_transfer = compute_gas_transfer(full_state.values, self.params)
        if use_cache:
            self._last_h_ion = acid_base.s_h_ion
        return FullStateEvaluation(
            full_state=full_state,
            acid_base=acid_base,
            gas_transfer=gas_transfer,
            rates=rates,
            inhibitions=inhibitions,
        )
