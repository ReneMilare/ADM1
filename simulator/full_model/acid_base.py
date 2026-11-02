from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping

from simulator.core.algebraic import bracketed_newton

_CHARGE_INPUTS = ("S_cation", "S_anion", "S_IN", "S_IC", "S_ac", "S_pro", "S_bu", "S_va", "S_IP")


# Barrera et al. (2015), §2.1/Table 2: H2S/HS- equilibrium; S2- is
# negligible at digester pH (pKa2 ≈ 14). No dissociation enthalpy is supplied.
KA_H2S = 1e-7  # pKa1 ≈ 7 at 25 °C; kmol/m3 = mol/L.
KA_HS = 1e-14


def speciate_sulfide(s_total: float, s_h_ion: float) -> tuple[float, float]:
    """Return free H2S and HS- from S_H2S = H2S + HS- (kmolS/m3)."""
    total = max(float(s_total), 0.0)
    h = max(float(s_h_ion), 1e-14)
    return total * h / (h + KA_H2S), total * KA_H2S / (h + KA_H2S)


def sulfide_ion_concentration(s_total: float, s_h_ion: float) -> float:
    """Trace S2- for mineral Ksp based on [M2+][S2-], in kmolS/m3.

    Maharaj et al. (2018), §2.3/Table 1, includes HS-/S2- dissociation
    and uses S2- for FeS, NiS and CoS. S_H2S retains its H2S + HS- basis.
    """
    _, hs = speciate_sulfide(s_total, s_h_ion)
    return KA_HS * hs / max(float(s_h_ion), 1e-14)


def _extension_charge_contribution(
    total_state: Mapping[str, float],
    params: Mapping[str, float],
    s_h_ion: float,
) -> tuple[float, float]:
    """Extension charge (kmol charge/m3) and its analytical H+ derivative."""
    residual = -2.0 * max(float(total_state.get("S_SO4", 0.0)), 0.0)
    # E8 and E9 dissolved metals are molar; fixed feed parameters are not states.
    for name in ("S_Fe2", "S_Fe2_te", "S_Ni", "S_Co"):
        residual += 2.0 * max(float(total_state.get(name, 0.0)), 0.0)

    total_sulfide = max(float(total_state.get("S_H2S", 0.0)), 0.0)
    _, hs = speciate_sulfide(total_sulfide, s_h_ion)
    residual -= hs
    gradient = total_sulfide * KA_H2S / (s_h_ion + KA_H2S) ** 2

    # Satpathy et al. (2016), model development: pKa(lactate) = 3.86.
    # COD from complete oxidation of C3H6O3, C7H6O2 and C6H6O:
    # (C + H/4 - O/2)*32 = 96, 240, 224 kgCOD/kmol, respectively.
    # Phenol/benzoate acid-base extension: Fezzani & Ben Cheikh (2009), §3.
    for name, pka, molar_cod in (
        ("S_lac", 3.86, 96.0),
        ("S_ben", 4.2, 240.0),
        ("S_phen", 9.99, 224.0),
    ):
        total = max(float(total_state.get(name, 0.0)), 0.0) / molar_cod
        ka = 10.0 ** -pka
        residual -= total * ka / (s_h_ion + ka)
        gradient += total * ka / (s_h_ion + ka) ** 2
    return residual, gradient


def _phosphate_charge_contribution(
    s_ip: float,
    params: Mapping[str, float],
    s_h_ion: float,
) -> tuple[float, float]:
    """Contribution of dissolved inorganic phosphate to the charge-balance residual and gradient.

    Called automatically in the Newton loop when S_IP > 0, i.e., when the
    phosphorus extension (E7) is active. When E7 is inactive, S_IP is absent
    from total_state and this function is never called (s_ip guard below).

    The three phosphate species at digestor pH (6–8):
        H3PO4 → H2PO4⁻ → HPO4²⁻ → PO4³⁻
    pKa1 ≈ 2.15 (negligible), pKa2 ≈ 7.20, pKa3 ≈ 12.34 (negligible).
    All three species are included for generality; pKa1 and pKa3 contribute
    negligibly at typical digester pH.

    Speciation from S_IP (total dissolved P):
        denom  = [H+]² + Ka2·[H+] + Ka2·Ka3
        H2PO4⁻ = S_IP · [H+]² / denom   (monovalent anion, charge –1)
        HPO4²⁻ = S_IP · Ka2·[H+] / denom (divalent anion, charge –2)
        PO4³⁻  = S_IP · Ka2·Ka3 / denom  (trivalent anion, charge –3)

    Contribution to charge-balance residual (phosphates are anions → subtract):
        Δresidual = −(H2PO4⁻ + 2·HPO4²⁻ + 3·PO4³⁻)

    Returns:
        (delta_residual, delta_gradient): both floats to be *added* to the Newton
        residual and gradient respectively.
    """
    if s_ip <= 0.0:
        return 0.0, 0.0

    ka2 = float(params.get("Ka_H2PO4", 6.31e-8))
    ka3 = float(params.get("Ka_HPO4", 4.57e-13))

    denom = s_h_ion * s_h_ion + ka2 * s_h_ion + ka2 * ka3
    if denom <= 0.0:
        return 0.0, 0.0

    s_h2po4 = s_ip * s_h_ion * s_h_ion / denom
    s_hpo4 = s_ip * ka2 * s_h_ion / denom
    s_po4 = s_ip * ka2 * ka3 / denom

    # Charge contribution (phosphate anions reduce the residual)
    delta_residual = -(s_h2po4 + 2.0 * s_hpo4 + 3.0 * s_po4)

    # Analytical gradient: d(delta_residual)/d(s_h_ion)
    # Let N_k = numerator of species k, D = denom, dD/dh = 2h + Ka2
    d_denom = 2.0 * s_h_ion + ka2
    d_s_h2po4 = s_ip * (2.0 * s_h_ion * denom - s_h_ion * s_h_ion * d_denom) / (denom * denom)
    d_s_hpo4 = s_ip * ka2 * (denom - s_h_ion * d_denom) / (denom * denom)
    d_s_po4 = s_ip * ka2 * ka3 * (-d_denom) / (denom * denom)

    delta_gradient = -(d_s_h2po4 + 2.0 * d_s_hpo4 + 3.0 * d_s_po4)

    return float(delta_residual), float(delta_gradient)


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



def _charge_residual(
    total_state: Mapping[str, float], params: Mapping[str, float], s_h_ion: float,
) -> tuple[float, float]:
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
    # Phosphate contribution (active when E7 phosphorus extension is enabled).
    # S_IP is a dynamic liquid state added by E7; when absent, get() returns 0.0.
    s_ip = float(total_state.get("S_IP", 0.0))
    if s_ip > 0.0:
        dr_p, dg_p = _phosphate_charge_contribution(s_ip, params, s_h_ion)
        residual += dr_p
        gradient += dg_p
    dr_ext, dg_ext = _extension_charge_contribution(total_state, params, s_h_ion)
    residual += dr_ext
    gradient += dg_ext
    return residual, gradient


def solve_acid_base(
    total_state: Mapping[str, float],
    params: Mapping[str, float],
    *,
    initial_guess: float | None = None,
) -> AcidBaseState:
    tol = float(params["ph_solver_tol"])
    max_iterations = int(params["max_newton_iterations"])
    s_h_ion = max(float(initial_guess or 1e-7), 1e-14)
    converged = False
    iterations = 0
    finite = all(math.isfinite(float(total_state[name])) for name in _CHARGE_INPUTS if name in total_state)

    for iterations in range(1, max_iterations + 1 if finite else 1):
        residual, gradient = _charge_residual(total_state, params, s_h_ion)
        if not (math.isfinite(residual) and math.isfinite(gradient)):
            break
        if abs(residual) < tol:
            converged = True
            break
        if abs(gradient) <= 1e-24:
            break
        next_value = s_h_ion - residual / gradient
        if not (next_value > 0.0):
            next_value = max(s_h_ion * 0.5, 1e-14)
        # BSM2 (Rosén & Jeppsson 2006, §4.2.1): convergence requires charge balance,
        # even when a Newton step is tiny in absolute [H+] units.
        s_h_ion = max(next_value, 1e-14)

    if not converged and finite:
        # Plain Newton failed on a finite state: bracket the physical root
        # [1e-14, 1] mol/L and bisect (deterministic, monotone residual).
        root, extra, ok = bracketed_newton(
            lambda h: _charge_residual(total_state, params, h),
            1e-14, 1.0, s_h_ion, tolerance=tol, max_iterations=max_iterations,
        )
        if ok:
            s_h_ion, converged, iterations = root, True, iterations + extra
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
