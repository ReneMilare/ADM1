from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True, slots=True)
class GasTransferState:
    p_gas_h2: float
    p_gas_ch4: float
    p_gas_co2: float
    p_total: float
    q_gas: float
    q_ch4: float
    q_co2: float
    q_h2: float
    rho_t8: float
    rho_t9: float
    rho_t10: float



def compute_gas_transfer(state: Mapping[str, float], params: Mapping[str, float]) -> GasTransferState:
    p_gas_h2 = float(state["S_gas_h2"]) * params["R"] * params["T_op"] / 16.0
    p_gas_ch4 = float(state["S_gas_ch4"]) * params["R"] * params["T_op"] / 64.0
    p_gas_co2 = float(state["S_gas_co2"]) * params["R"] * params["T_op"]
    p_total = max(p_gas_h2 + p_gas_ch4 + p_gas_co2 + params["p_gas_h2o"], 1e-12)
    q_gas = max(params["k_p"] * (p_total - params["p_atm"]), 0.0)
    rho_t8 = params["k_L_a"] * (float(state["S_h2"]) - 16.0 * params["K_H_h2"] * p_gas_h2)
    rho_t9 = params["k_L_a"] * (float(state["S_ch4"]) - 64.0 * params["K_H_ch4"] * p_gas_ch4)
    rho_t10 = params["k_L_a"] * (float(state["S_co2"]) - params["K_H_co2"] * p_gas_co2)
    return GasTransferState(
        p_gas_h2=float(p_gas_h2),
        p_gas_ch4=float(p_gas_ch4),
        p_gas_co2=float(p_gas_co2),
        p_total=float(p_total),
        q_gas=float(q_gas),
        q_ch4=float(q_gas * (p_gas_ch4 / p_total)),
        q_co2=float(q_gas * (p_gas_co2 / p_total)),
        q_h2=float(q_gas * (p_gas_h2 / p_total)),
        rho_t8=float(rho_t8),
        rho_t9=float(rho_t9),
        rho_t10=float(rho_t10),
    )
