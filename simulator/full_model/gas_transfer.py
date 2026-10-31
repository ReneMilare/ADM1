from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from simulator.full_model.assembly import FullModelAssembly
from simulator.full_model.model import DEFAULT_FULL_MODEL_ASSEMBLY
from simulator.full_model.units import KG_COD_M3

CORE_GAS_STATES = frozenset(("S_gas_h2", "S_gas_ch4", "S_gas_co2"))
_GAS_COD_KG_PER_KMOL = {"S_gas_CO": 16.0}


def extra_gas_molar_divisors(assembly: FullModelAssembly) -> dict[str, float]:
    """Convert extra headspace concentrations to kmol/m³ before applying p = cRT."""
    units = {state.name: state.unit for state in assembly.state_catalog}
    divisors: dict[str, float] = {}
    for name in assembly.dynamic_gas_state_names:
        if name in CORE_GAS_STATES:
            continue
        unit = units.get(name, "")
        if unit == KG_COD_M3 and name in _GAS_COD_KG_PER_KMOL:
            divisors[name] = _GAS_COD_KG_PER_KMOL[name]
        elif unit.startswith("kmol") and unit.endswith("/m3"):
            divisors[name] = 1.0
        else:
            raise ValueError(f"Conversão molar ausente para gás {name} (unidade: {unit}).")
    return divisors


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
    q_co: float = 0.0
    q_h2s: float = 0.0



def compute_gas_transfer(
    state: Mapping[str, float],
    params: Mapping[str, float],
    assembly: FullModelAssembly = DEFAULT_FULL_MODEL_ASSEMBLY,
) -> GasTransferState:
    p_gas_h2 = float(state["S_gas_h2"]) * params["R"] * params["T_op"] / 16.0
    p_gas_ch4 = float(state["S_gas_ch4"]) * params["R"] * params["T_op"] / 64.0
    p_gas_co2 = float(state["S_gas_co2"]) * params["R"] * params["T_op"]
    extra_pressures = {
        name: float(state[name]) * params["R"] * params["T_op"] / divisor
        for name, divisor in extra_gas_molar_divisors(assembly).items()
    }
    p_total = max(p_gas_h2 + p_gas_ch4 + p_gas_co2 + sum(extra_pressures.values()) + params["p_gas_h2o"], 1e-12)
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
        q_co=float(q_gas * extra_pressures.get("S_gas_CO", 0.0) / p_total),
        q_h2s=float(q_gas * extra_pressures.get("S_gas_H2S", 0.0) / p_total),
    )
