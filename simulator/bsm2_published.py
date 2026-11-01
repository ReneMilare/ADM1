from __future__ import annotations

from typing import Any, Literal

import numpy as np

from simulator.core.defaults import make_default_kinetics
from simulator.core.pyadm1_backend import P_ATM_BAR, R_GAS, simulate_with_pyadm1_frames
from simulator.full_model.adapter import build_backend_inputs_from_state_maps
from simulator.full_model.solver import simulate_with_full_inputs
from simulator.literature_validation import (
    REFERENCE_SOURCE,
    build_reference_influent_frame,
    build_reference_initial_frame,
    build_reference_operating_conditions,
    build_reference_pyadm1_feed,
    build_reference_simulation_config,
)

RELATIVE_TOLERANCE = 0.001
ABSOLUTE_TOLERANCE = 1e-14

# Rosén & Jeppsson (2008), Table 6, p. 22 of the original PDF, not the
# rounded Markdown conversion: https://assets.pubpub.org/awqjabxp/51603224611145.pdf
PUBLISHED_OUTPUTS: dict[str, float] = {
    "S_su": 0.011954829716958,
    "S_aa": 0.005314740171633,
    "S_fa": 0.098621400930799,
    "S_va": 0.011625006463861,
    "S_bu": 0.013250729666269,
    "S_pro": 0.015783666284542,
    "S_ac": 0.197629716937552,
    "S_h2": 0.000000235945059,
    "S_ch4": 0.055088776445959,
    "S_IC": 0.152677870626333,
    "S_IN": 0.130229815803682,
    "S_I": 0.328697663721532,
    "X_xc": 0.308697663721532,
    "X_ch": 0.027947240435040,
    "X_pr": 0.102574106106682,
    "X_li": 0.029483049707287,
    "X_su": 0.420165982454567,
    "X_aa": 1.179171798923700,
    "X_fa": 0.243035344719442,
    "X_c4": 0.431921105635979,
    "X_pro": 0.137305908933954,
    "X_ac": 0.760562658313215,
    "X_h2": 0.317022953361272,
    "X_I": 25.617395327443063,
    "S_cation": 0.04,
    "S_anion": 0.02,
    "Q": 170.0,
    "T_op": 35.0,
    "pH": 7.465537769904638,
    "S_H_ion": 0.000000034234361,
    "S_va_ion": 0.011596247072545,
    "S_bu_ion": 0.013220826248532,
    "S_pro_ion": 0.015742783191567,
    "S_ac_ion": 0.197241155436605,
    "S_hco3_ion": 0.142777479392078,
    "S_co2": 0.009900391234255,
    "S_nh3": 0.004090928458444,
    "S_nh4_ion": 0.126138887345238,
    "S_gas_h2": 0.000010241035595,
    "S_gas_ch4": 1.625607209981422,
    "S_gas_co2": 0.014150534678395,
    "p_gas_h2": 0.000016399182640,
    "p_gas_ch4": 0.650779632823186,
    "p_gas_co2": 0.362552713328102,
    "Pgas_bar": 1.069016490408918,
    "Qgas_Nm3_day": 2955.703454193784,
}

# Table 6 gives Qgas and partial pressures, but no methane flow. Ideal-gas
# volume fractions (BSM2 §3.5.4) give methane at the same pressure/temperature.
DERIVED_OUTPUTS = {
    "Qch4_Nm3_day": (
        PUBLISHED_OUTPUTS["Qgas_Nm3_day"]
        * PUBLISHED_OUTPUTS["p_gas_ch4"]
        / PUBLISHED_OUTPUTS["Pgas_bar"]
    ),
}


def compare_published_outputs(actual: dict[str, float]) -> dict[str, dict[str, Any]]:
    comparison = {}
    for name, reference in (PUBLISHED_OUTPUTS | DERIVED_OUTPUTS).items():
        delta = abs(actual[name] - reference)
        comparison[name] = {
            "reference": reference,
            "actual": actual[name],
            "abs_delta": delta,
            "rel_delta_pct": delta / abs(reference) * 100.0,
            "within_tolerance": delta <= max(ABSOLUTE_TOLERANCE, abs(reference) * RELATIVE_TOLERANCE),
            "reference_kind": "published_table_6" if name in PUBLISHED_OUTPUTS else "derived_from_table_6",
        }
    return comparison


def run_published_steady_state_case(
    backend: Literal["full", "pyadm1"], *, duration_days: float = 200.0,
) -> dict[str, Any]:
    operating = build_reference_operating_conditions()
    simulation = build_reference_simulation_config(backend=backend).model_copy(
        update={"duration_days": duration_days, "evaluation_points": int(duration_days) + 1},
    )
    influent = build_reference_influent_frame(
        np.linspace(0.0, simulation.duration_days, simulation.evaluation_points),
    )
    initial = build_reference_initial_frame()
    parameters = make_default_kinetics()
    if backend == "full":
        inputs = build_backend_inputs_from_state_maps(
            operating_conditions=operating,
            parameters=parameters,
            influent_values=influent.iloc[0].to_dict(),
            initial_values=initial.iloc[0].to_dict(),
            flow_rate_m3_day=float(influent.iloc[0]["Q"]),
        )
        result = simulate_with_full_inputs(inputs=inputs, simulation=simulation)
        columns = result["metadata"]["full_state_columns"]
        formulation = "DAE1: differential dissolved H2, algebraic acid-base equilibrium"
    elif backend == "pyadm1":
        result = simulate_with_pyadm1_frames(
            operating_conditions=operating,
            feed=build_reference_pyadm1_feed(),
            parameters=parameters,
            simulation=simulation,
            influent_frame=influent,
            initial_frame=initial,
        )
        columns = result["metadata"]["pyadm1_state_columns"]
        formulation = "DAE2: algebraic dissolved H2 and acid-base equilibrium"
    else:
        raise ValueError("Published BSM2 validation requires full or pyadm1")

    actual = dict(zip(columns, result["metadata"]["final_internal_state"], strict=True))
    profiles = result["profiles"]
    actual["pH"] = float(profiles["ph"][-1])
    actual["S_H_ion"] = 10.0 ** -actual["pH"]
    temperature_k = operating.temperature_c + 273.15
    actual["p_gas_h2"] = actual["S_gas_h2"] * R_GAS * temperature_k / 16.0
    actual["p_gas_ch4"] = actual["S_gas_ch4"] * R_GAS * temperature_k / 64.0
    actual["p_gas_co2"] = actual["S_gas_co2"] * R_GAS * temperature_k
    p_water = 0.0313 * np.exp(5290.0 * (1.0 / 298.15 - 1.0 / temperature_k))
    actual["Pgas_bar"] = float(sum(actual[name] for name in ("p_gas_h2", "p_gas_ch4", "p_gas_co2")) + p_water)
    actual["Qgas_Nm3_day"] = float(profiles["biogas_m3_day"][-1])
    actual["Qch4_Nm3_day"] = float(profiles["methane_m3_day"][-1])
    actual["Q"] = float(influent.iloc[-1]["Q"])
    actual["T_op"] = operating.temperature_c
    comparison = compare_published_outputs(actual)
    return {
        "source": REFERENCE_SOURCE,
        "execution": {
            "backend": backend,
            "formulation": formulation,
            "duration_days": duration_days,
            "evaluation_points": simulation.evaluation_points,
            "solver": simulation.solver,
            "rtol": simulation.rtol,
            "atol": simulation.atol,
            "initial_state_source": "vendor/PyADM1/src/digester_initial.csv",
            "gas_reference_pressure_bar": P_ATM_BAR,
            "gas_reference_temperature_c": operating.temperature_c,
        },
        "comparison": comparison,
        "validated": all(item["within_tolerance"] for item in comparison.values()),
        "tolerances": {"relative_percent_max": RELATIVE_TOLERANCE * 100.0, "absolute_floor": ABSOLUTE_TOLERANCE},
    }
