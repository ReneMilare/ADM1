from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True, slots=True)
class AcidBaseState:
    s_h_ion: float
    p_h: float
    s_va_ion: float
    s_bu_ion: float
    s_pro_ion: float
    s_ac_ion: float
    s_hco3_ion: float
    s_co2: float
    s_nh3: float
    s_nh4_ion: float
    iterations: int
    converged: bool



def solve_acid_base(
    total_state: Mapping[str, float],
    params: Mapping[str, float],
    *,
    initial_guess: float | None = None,
) -> AcidBaseState:
    tol = float(params["ph_solver_tol"])
    max_iterations = int(params["max_newton_iterations"])
    s_h_ion = max(float(initial_guess or 1e-7), tol)
    converged = False
    iterations = 0

    for iterations in range(1, max_iterations + 1):
        values = _species(total_state, params, s_h_ion)
        residual = (
            float(total_state["S_cation"])
            + (float(total_state["S_IN"]) - values["S_nh3"])
            + s_h_ion
            - values["S_hco3_ion"]
            - values["S_ac_ion"] / 64.0
            - values["S_pro_ion"] / 112.0
            - values["S_bu_ion"] / 160.0
            - values["S_va_ion"] / 208.0
            - params["K_w"] / s_h_ion
            - float(total_state["S_anion"])
        )
        gradient = (
            1.0
            + params["K_a_IN"] * max(float(total_state["S_IN"]), 0.0) / ((params["K_a_IN"] + s_h_ion) ** 2)
            + params["K_a_co2"] * max(float(total_state["S_IC"]), 0.0) / ((params["K_a_co2"] + s_h_ion) ** 2)
            + (params["K_a_ac"] * max(float(total_state["S_ac"]), 0.0) / ((params["K_a_ac"] + s_h_ion) ** 2)) / 64.0
            + (params["K_a_pro"] * max(float(total_state["S_pro"]), 0.0) / ((params["K_a_pro"] + s_h_ion) ** 2)) / 112.0
            + (params["K_a_bu"] * max(float(total_state["S_bu"]), 0.0) / ((params["K_a_bu"] + s_h_ion) ** 2)) / 160.0
            + (params["K_a_va"] * max(float(total_state["S_va"]), 0.0) / ((params["K_a_va"] + s_h_ion) ** 2)) / 208.0
            + params["K_w"] / (s_h_ion * s_h_ion)
        )
        if abs(residual) <= tol:
            converged = True
            break
        if abs(gradient) <= 1e-24:
            break
        next_value = s_h_ion - residual / gradient
        if not (next_value > 0.0):
            next_value = max(s_h_ion * 0.5, tol)
        if abs(next_value - s_h_ion) <= tol * max(1.0, s_h_ion):
            s_h_ion = next_value
            values = _species(total_state, params, s_h_ion)
            converged = True
            break
        s_h_ion = max(next_value, tol)
    else:
        values = _species(total_state, params, s_h_ion)

    return AcidBaseState(
        s_h_ion=float(s_h_ion),
        p_h=float(-__import__("math").log10(max(s_h_ion, 1e-14))),
        s_va_ion=float(values["S_va_ion"]),
        s_bu_ion=float(values["S_bu_ion"]),
        s_pro_ion=float(values["S_pro_ion"]),
        s_ac_ion=float(values["S_ac_ion"]),
        s_hco3_ion=float(values["S_hco3_ion"]),
        s_co2=float(values["S_co2"]),
        s_nh3=float(values["S_nh3"]),
        s_nh4_ion=float(values["S_nh4_ion"]),
        iterations=iterations,
        converged=converged,
    )



def _species(total_state: Mapping[str, float], params: Mapping[str, float], s_h_ion: float) -> dict[str, float]:
    s_va_ion = params["K_a_va"] * max(float(total_state["S_va"]), 0.0) / (params["K_a_va"] + s_h_ion)
    s_bu_ion = params["K_a_bu"] * max(float(total_state["S_bu"]), 0.0) / (params["K_a_bu"] + s_h_ion)
    s_pro_ion = params["K_a_pro"] * max(float(total_state["S_pro"]), 0.0) / (params["K_a_pro"] + s_h_ion)
    s_ac_ion = params["K_a_ac"] * max(float(total_state["S_ac"]), 0.0) / (params["K_a_ac"] + s_h_ion)
    s_hco3_ion = params["K_a_co2"] * max(float(total_state["S_IC"]), 0.0) / (params["K_a_co2"] + s_h_ion)
    s_nh3 = params["K_a_IN"] * max(float(total_state["S_IN"]), 0.0) / (params["K_a_IN"] + s_h_ion)
    return {
        "S_va_ion": float(s_va_ion),
        "S_bu_ion": float(s_bu_ion),
        "S_pro_ion": float(s_pro_ion),
        "S_ac_ion": float(s_ac_ion),
        "S_hco3_ion": float(s_hco3_ion),
        "S_co2": float(max(float(total_state["S_IC"]) - s_hco3_ion, 0.0)),
        "S_nh3": float(s_nh3),
        "S_nh4_ion": float(max(float(total_state["S_IN"]) - s_nh3, 0.0)),
    }
