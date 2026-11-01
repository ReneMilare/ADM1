from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from simulator.digital_twin import engine as engine_module
from simulator.digital_twin.contracts import MEASUREMENT_COLUMNS, InfluentWindow, TwinState
from simulator.digital_twin.dataset import read_measurements, to_daily, write_measurements
from simulator.digital_twin.demo import OUTPUT_COLUMNS, stitch
from simulator.digital_twin.engine import TwinEngine
from simulator.digital_twin.measurement import SensorSpec, measure
from simulator.digital_twin.metrics import tracking_report
from simulator.full_model.diagnostics import translate_full_profiles


@pytest.fixture
def physical_case(monkeypatch):
    def make(*, temperature_c=35.0, p_atm=1.01325, extensions=(), gases=True):
        engine = TwinEngine(volume_m3=3000.0, active_extensions=extensions,
                            parameter_overrides={"p_atm": p_atm})
        window = InfluentWindow(t_start_days=0.0, t_end_days=1.0, flow_m3_day=150.0,
                                temperature_c=temperature_c, influent_values={})
        inputs = engine._inputs(window, {}, engine.parameter_overrides)
        params = inputs.parameter_values
        values = {name: 0.0 for name in inputs.assembly.full_state_names}
        values.update({
            "S_IN": 0.1, "S_nh3": 0.02, "S_nh4_ion": 0.08,
            "S_IC": 0.15, "S_hco3_ion": 0.1, "S_co2": 0.05,
            "S_H_ion": 1e-8,
            "S_ac": 1.28, "S_ac_ion": 0.64,
            "S_pro": 4.48, "S_pro_ion": 2.24,
            "S_bu": 9.6, "S_bu_ion": 4.8,
            "S_va": 16.64, "S_va_ion": 8.32,
        })
        # Known partial pressures [bar], including CO and H2S when active.
        pressures = {"S_gas_ch4": (0.8, 64.0), "S_gas_co2": (0.3, 1.0),
                     "S_gas_h2": (0.01, 16.0), "S_gas_CO": (0.07, 16.0),
                     "S_gas_H2S": (0.02, 1.0)}
        for name, (pressure, divisor) in pressures.items():
            if name in values and gases:
                values[name] = pressure * divisor / (params["R"] * params["T_op"])
        row = [values[name] for name in inputs.assembly.full_state_names]
        profiles = translate_full_profiles(full_state_matrix=np.asarray([row, row]),
                                           parameter_values=params, assembly=inputs.assembly)
        dynamic = {name: values[name] for name in inputs.assembly.dynamic_state_names}
        state = TwinState(time_days=0.0, volume_m3=3000.0, dynamic_state=dynamic,
                          parameter_overrides=engine.parameter_overrides,
                          active_extensions=engine.active_extensions)

        def solve(**kwargs):
            np.testing.assert_array_equal(kwargs["initial_dynamic_state"], list(dynamic.values()))
            return {"profiles": profiles, "time_days": [0.0, 1.0]}

        monkeypatch.setattr(engine_module, "simulate_with_full_inputs", solve)
        result = engine.advance(state, window)
        assert state.dynamic_state == dynamic
        assert result.state.dynamic_state == dynamic
        return result, profiles, params, window

    return make


def test_ammonium_excludes_free_ammonia_and_conserves_nitrogen(physical_case):
    result, profiles, _, _ = physical_case()
    ammonium = np.asarray(result.outputs["nh4_kg_n_m3"])
    np.testing.assert_allclose(ammonium, [1.12, 1.12], rtol=0.0, atol=1e-14)
    residual = ammonium + 14.0 * np.asarray(profiles["S_nh3"]) - 14.0 * np.asarray(profiles["S_IN"])
    np.testing.assert_allclose(residual, 0.0, rtol=0.0, atol=1e-14)


def test_alkalinity_sums_bicarbonate_vfa_equivalents_and_free_ammonia(physical_case):
    result, profiles, _, _ = physical_case()
    # 0.10 HCO3 + 0.01 acetate + 0.02 propionate + 0.03 butyrate
    # + 0.04 valerate + 0.02 NH3, all in kmol of charge/m3.
    expected = 0.22
    np.testing.assert_allclose(result.outputs["alkalinity_kmol_m3"], expected, rtol=0.0, atol=1e-14)
    assert expected != pytest.approx(profiles["S_IC"][0])


@pytest.mark.parametrize("temperature_c", [15.0, 35.0, 55.0])
@pytest.mark.parametrize("p_atm", [0.95, 1.01325, 1.2])
def test_dry_normal_biogas_conserves_molar_flow(physical_case, temperature_c, p_atm):
    result, profiles, params, _ = physical_case(temperature_c=temperature_c, p_atm=p_atm)
    q_normal = np.asarray(result.outputs["biogas_m3_d"])
    q_headspace = np.asarray(profiles["q_gas_headspace_m3_day"])
    p_dry = np.asarray(profiles["Pgas_bar"]) - params["p_gas_h2o"]
    expected = q_headspace * p_dry / 1.01325 * 273.15 / (temperature_c + 273.15)
    np.testing.assert_allclose(q_normal, expected, rtol=1e-13, atol=1e-12)
    # Ideal-gas molar flux before and after normalisation [kmol/d].
    residual = q_normal * 1.01325 / (params["R"] * 273.15) - q_headspace * p_dry / (params["R"] * params["T_op"])
    np.testing.assert_allclose(residual, 0.0, rtol=0.0, atol=1e-12)


@pytest.mark.parametrize("extensions,extra_pressure", [
    ((), 0.0), (("srb",), 0.02), (("syngas",), 0.07), (("srb", "syngas"), 0.09),
])
def test_methane_fraction_is_dry_and_includes_extension_gases(physical_case, extensions, extra_pressure):
    result, profiles, params, _ = physical_case(extensions=extensions)
    expected = 0.8 / (0.8 + 0.3 + 0.01 + extra_pressure)
    np.testing.assert_allclose(result.outputs["ch4_fraction"], expected, rtol=1e-13, atol=1e-14)
    partials = np.asarray([0.8, 0.3, 0.01, 0.07 if "syngas" in extensions else 0.0,
                           0.02 if "srb" in extensions else 0.0])
    fractions = partials / partials.sum()
    fractions[0] = result.outputs["ch4_fraction"][0]
    molar_before = profiles["q_gas_headspace_m3_day"][0] * partials / (params["R"] * params["T_op"])
    molar_after = result.outputs["biogas_m3_d"][0] * 1.01325 / (params["R"] * 273.15) * fractions
    # CH4, CO2, H2, CO, H2S: carbon, COD and sulfur fluxes must survive
    # conversion from wet reactor volume to dry normal volume.
    balances = np.asarray([[1.0, 1.0, 0.0, 1.0, 0.0],
                           [64.0, 0.0, 16.0, 16.0, 0.0],
                           [0.0, 0.0, 0.0, 0.0, 1.0]])
    np.testing.assert_allclose(balances @ (molar_after - molar_before), 0.0, rtol=0.0, atol=1e-11)


def test_empty_headspace_has_finite_zero_gas_outputs(physical_case):
    result, _, _, _ = physical_case(gases=False)
    assert result.outputs["biogas_m3_d"] == [0.0, 0.0]
    assert result.outputs["ch4_fraction"] == [0.0, 0.0]


def test_ammonium_tracks_native_speciation_across_temperature_windows():
    from simulator.digital_twin.scenarios import base_influent_values

    engine = TwinEngine(volume_m3=3000.0)
    window = InfluentWindow(t_start_days=0.0, t_end_days=1.0, flow_m3_day=150.0,
                            temperature_c=35.0, influent_values=base_influent_values())
    state = engine.initial_state(window, warmup_days=30.0)
    for temperature in (35.0, 55.0):
        window = window.model_copy(update={"t_start_days": state.time_days,
                                           "t_end_days": state.time_days + 1.0,
                                           "temperature_c": temperature})
        result = engine.advance(state, window)
        params = engine._inputs(window, state.dynamic_state, state.parameter_overrides).parameter_values
        for index, checkpoint in ((0, state), (-1, result.state)):
            h_ion = 10.0 ** -result.outputs["ph"][index]
            total_n = checkpoint.dynamic_state["S_IN"] * 14.0
            free_n = total_n * params["K_a_IN"] / (params["K_a_IN"] + h_ion)
            residual = result.outputs["nh4_kg_n_m3"][index] + free_n - total_n
            assert residual == pytest.approx(0.0, abs=1e-12)
        state = result.state


def test_physical_outputs_survive_sensor_csv_and_metrics_pipeline(physical_case, tmp_path):
    result, _, _, window = physical_case()
    time, outputs, inputs = stitch([result], [window])
    suite = [SensorSpec(column=column) for column in OUTPUT_COLUMNS]
    measured = measure(time, outputs, inputs, suite, seed=0)
    path = tmp_path / "physical_measurements.csv"
    write_measurements(measured, path)
    recovered = read_measurements(path)
    pd.testing.assert_frame_equal(measured, recovered)
    assert list(recovered.columns) == list(MEASUREMENT_COLUMNS)
    assert recovered["nh4_kg_n_m3"].iloc[0] == pytest.approx(1.12)
    assert recovered["alkalinity_kmol_m3"].iloc[0] == pytest.approx(0.22)
    simulated = to_daily(pd.DataFrame({"time_days": time, **outputs, **inputs}))
    report = tracking_report(recovered, simulated, columns=list(OUTPUT_COLUMNS))
    assert all(stats["mape"] == pytest.approx(0.0) for stats in report.values())
