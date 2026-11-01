from __future__ import annotations

import numpy as np
import pytest

from simulator.full_model import acid_base
from simulator.full_model.extension_registry import resolve_full_model_assembly
from simulator.full_model.iron_extension import IRON_EXTENSION
from simulator.full_model.model import build_numeric_biochemical_matrix
from simulator.full_model.srb_extension import SRB_EXTENSION
from simulator.full_model.trace_elements_extension import TRACE_ELEMENTS_EXTENSION
from simulator.tests.test_extensions import _base_state, _make_params


@pytest.mark.parametrize("p_h", [5.0, 7.0, 9.0])
def test_sulfide_speciation_preserves_total_sulfur(p_h: float) -> None:
    h = 10.0 ** -p_h
    free, hs = acid_base.speciate_sulfide(0.003, h)
    assert free == pytest.approx(0.003 * h / (h + 1e-7))
    assert hs == pytest.approx(0.003 * 1e-7 / (h + 1e-7))
    assert free + hs - 0.003 == pytest.approx(0.0, abs=1e-18)


@pytest.mark.parametrize("p_h", [6.0, 7.0, 8.0])
def test_h2s_transfer_uses_free_species_and_henry_backpressure(p_h: float) -> None:
    params = _make_params("srb")
    state = {"S_H2S": 0.003, "S_H_ion": 10.0 ** -p_h, "S_gas_H2S": 1e-5}
    free = 0.003 / (1.0 + 10.0 ** (p_h - 7.0))
    expected = params["k_La_H2S"] * (
        free - params["K_H_H2S"] * 1e-5 * params["R"] * params["T_op"]
    )
    assert SRB_EXTENSION._rates(state, params)["rho_E4_H2S_transfer"] == pytest.approx(expected)


@pytest.mark.parametrize("p_h", [6.0, 7.0, 8.0])
def test_h2s_inhibition_uses_free_species_in_hooks_and_srb_rates(p_h: float) -> None:
    params = _make_params("srb")
    state = _base_state() | {
        "S_H2S": 0.003, "S_H_ion": 10.0 ** -p_h, "S_SO4": 0.01,
        "X_SRB_ac": 0.1, "X_SRB_h2": 0.1, "X_SRB_pro": 0.1, "X_SRB_bu": 0.1,
    }
    free = 0.003 / (1.0 + 10.0 ** (p_h - 7.0))
    inhibition = 1.0 - free / params["K_I_H2S"]
    assert all(value == pytest.approx(inhibition) for value in SRB_EXTENSION._inhibition(state, params).values())
    inhibited = SRB_EXTENSION._rates(state, params)
    uninhibited = SRB_EXTENSION._rates(state | {"S_H2S": 0.0}, params)
    for substrate in ("ac", "h2", "pro", "bu"):
        process = f"rho_E4_SRB_uptake_{substrate}"
        assert inhibited[process] / uninhibited[process] == pytest.approx(inhibition)


CHARGES = [
    ("S_SO4", 0.001, -0.002, 0.0),
    ("S_H2S", 0.002, -0.001, 5000.0),
    ("S_Fe2", 0.001, 0.002, 0.0),
    ("S_Fe2_te", 0.001, 0.002, 0.0),
    ("S_Ni", 0.001, 0.002, 0.0),
    ("S_Co", 0.001, 0.002, 0.0),
] + [
    (name, cod * 0.001, -0.001 * 10.0 ** -pka / (1e-7 + 10.0 ** -pka),
     0.001 * 10.0 ** -pka / (1e-7 + 10.0 ** -pka) ** 2)
    for name, cod, pka in (("S_lac", 96.0, 3.86), ("S_ben", 240.0, 4.2), ("S_phen", 224.0, 9.99))
]


@pytest.mark.parametrize("name,amount,charge,gradient", CHARGES)
def test_each_extension_charge_and_analytic_gradient(
    name: str, amount: float, charge: float, gradient: float,
) -> None:
    params = _make_params("srb")
    dr, dg = acid_base._extension_charge_contribution({name: amount}, params, 1e-7)
    assert dr == pytest.approx(charge)
    assert dg == pytest.approx(gradient)
    step = 1e-11
    above = acid_base._extension_charge_contribution({name: amount}, params, 1e-7 + step)[0]
    below = acid_base._extension_charge_contribution({name: amount}, params, 1e-7 - step)[0]
    assert dg == pytest.approx((above - below) / (2.0 * step), rel=1e-7, abs=1e-6)


@pytest.mark.parametrize("name,amount,charge,gradient", CHARGES)
def test_newton_includes_each_extension_charge(
    name: str, amount: float, charge: float, gradient: float,
) -> None:
    params = _make_params("srb")
    baseline = _base_state()
    reference = acid_base.solve_acid_base(baseline, params)
    changed = acid_base.solve_acid_base(baseline | {name: amount}, params)
    assert changed.converged
    assert abs(changed.p_h - reference.p_h) > 1e-6
    if charge > 0:
        assert changed.p_h > reference.p_h
    else:
        assert changed.p_h < reference.p_h
    # The extension charge is exactly equivalent to a strong-ion correction
    # evaluated at the same [H+], independently of the Newton implementation.
    h = changed.s_h_ion
    if name == "S_H2S":
        delta = -amount * 1e-7 / (h + 1e-7)
    elif name in ("S_lac", "S_ben", "S_phen"):
        cod, pka = {"S_lac": (96.0, 3.86), "S_ben": (240.0, 4.2), "S_phen": (224.0, 9.99)}[name]
        delta = -amount / cod * 10.0 ** -pka / (h + 10.0 ** -pka)
    else:
        delta = charge
    equivalent = acid_base.solve_acid_base(baseline | {"S_cation": baseline["S_cation"] + delta}, params)
    assert changed.p_h == pytest.approx(equivalent.p_h, abs=1e-9)


def test_inactive_extensions_leave_reference_ph_unchanged() -> None:
    params = _make_params("srb")
    state = _base_state()
    reference = acid_base.solve_acid_base(state, params)
    empty = acid_base.solve_acid_base(state | {name: 0.0 for name, *_ in CHARGES}, params)
    assert reference.converged and empty.converged
    assert empty == reference
    assert reference.p_h == pytest.approx(6.6166798832849265, abs=1e-10)


@pytest.mark.parametrize("extension,metal,solid,ksp_name,process", [
    (IRON_EXTENSION, "S_Fe2", "X_FeS", "Ksp_FeS", "rho_E8_FeS"),
    (TRACE_ELEMENTS_EXTENSION, "S_Fe2_te", "X_FeS_te", "Ksp_FeS_te", "rho_E9_FeS"),
    (TRACE_ELEMENTS_EXTENSION, "S_Ni", "X_NiS", "Ksp_NiS", "rho_E9_NiS"),
    (TRACE_ELEMENTS_EXTENSION, "S_Co", "X_CoS", "Ksp_CoS", "rho_E9_CoS"),
])
@pytest.mark.parametrize("p_h", [6.0, 8.0])
def test_metal_sulfides_use_s2_for_saturation_and_diagnostics(
    extension, metal: str, solid: str, ksp_name: str, process: str, p_h: float,
) -> None:
    names = ["srb", "phosphorus", "iron"] if extension is IRON_EXTENSION else ["srb", "trace_elements"]
    params = _make_params(names)
    h = 10.0 ** -p_h
    s2 = 1e-3 * 1e-7 / (h + 1e-7) * 1e-14 / h
    # Below saturation in the S2- basis, while total-sulfide incorrectly
    # predicts supersaturation by several orders of magnitude.
    concentration = 0.5 * params[ksp_name] / s2
    state = {metal: concentration, solid: 1e-5, "S_H2S": 1e-3, "S_H_ion": h}
    params = params | {"S_DOM_TE": 0.0}
    rates = extension._rates(state, params)
    assert rates[f"{process}_precip"] == 0.0
    suffix = "FeS" if extension is IRON_EXTENSION else process.removeprefix("rho_E9_")
    kinetic_suffix = "FeS_te" if metal == "S_Fe2_te" else suffix
    assert rates[f"{process}_dissolv"] == pytest.approx(params[f"k_dissolv_{kinetic_suffix}"] * 0.5e-5)
    assembly = resolve_full_model_assembly(names)
    row = np.array([[state.get(name, 0.0) for name in assembly.full_state_names]])
    diagnostic = extension._diagnostics(row, assembly, params)
    assert diagnostic[f"IP_{suffix}"][0] == pytest.approx(0.5)


def test_fes_constants_use_same_amorphous_s2_basis() -> None:
    assert _make_params(["srb", "phosphorus", "iron"])["Ksp_FeS"] == pytest.approx(1e-18, abs=1e-30)
    params = _make_params("trace_elements")
    assert params["Ksp_FeS_te"] == pytest.approx(1e-18, abs=1e-30)
    assert params["Ksp_NiS"] == pytest.approx(10.0 ** -20.7, rel=0.003, abs=1e-30)
    assert params["Ksp_CoS"] == pytest.approx(10.0 ** -20.3, rel=0.003, abs=1e-30)


@pytest.mark.parametrize("names", [["srb", "phosphorus", "iron"], ["srb", "trace_elements"]])
def test_sulfur_and_metal_conservation_in_precipitation_rows(names: list[str]) -> None:
    assembly = resolve_full_model_assembly(names)
    params = _make_params(names)
    matrix = build_numeric_biochemical_matrix(params, assembly)
    sulfur_states = {"S_SO4", "S_H2S", "X_FeS", "X_S0", "X_FeS_te", "X_NiS", "X_CoS"}
    sulfur = np.array([float(name in sulfur_states) for name in assembly.dynamic_state_names])
    for process in assembly.biochemical_process_names:
        if process.startswith(("rho_E8_", "rho_E9_")):
            row = matrix[:, assembly.biochemical_process_names.index(process)]
            assert row @ sulfur == pytest.approx(0.0, abs=1e-15)
            for elements in (
                {"S_Ni": 1.0, "X_NiS": 1.0},
                {"S_Co": 1.0, "X_CoS": 1.0},
                {"S_Fe2": 1.0, "X_FeS": 1.0, "X_VIV": 3.0,
                 "S_Fe2_te": 1.0, "X_FeS_te": 1.0, "X_FeCO3": 1.0},
            ):
                if process in ("rho_E8_Fe3_red_h2", "rho_E8_Fe3_red_h2s"):
                    continue  # Fe(III) is an external fixed feed, not a state.
                weights = np.array([elements.get(name, 0.0) for name in assembly.dynamic_state_names])
                assert row @ weights == pytest.approx(0.0, abs=1e-15)
