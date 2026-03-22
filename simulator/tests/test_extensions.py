"""Tests for the 5 new ADM1 extensions (E4-SRB, E5-LCFA, E6-Lactate, E10-Ethanol, E11-Phenolics).

Tests validate:
  1. Each extension can be contributed (contribute() runs without error)
  2. Each extension registers with the correct name
  3. Assemblies with each extension build successfully (no stoichiometry errors)
  4. Each extension can simulate without crashing
  5. Key states evolve in the expected direction
  6. Rate functions return the expected process names
"""
from __future__ import annotations

import pytest

from simulator.core.defaults import make_default_feed, make_default_initial_state, make_default_kinetics, make_default_operating_conditions
from simulator.core.models import OperatingConditions, SimulationConfig
from simulator.full_model.adapter import build_backend_inputs_from_state_maps
from simulator.full_model.extension_registry import resolve_full_model_assembly
from simulator.full_model.lactate_extension import LACTATE_EXTENSION
from simulator.full_model.ethanol_extension import ETHANOL_EXTENSION
from simulator.full_model.phenolics_extension import PHENOLICS_EXTENSION
from simulator.full_model.lcfa_extension import LCFA_EXTENSION
from simulator.full_model.srb_extension import SRB_EXTENSION
from simulator.full_model.model import FULL_STATE_NAMES, resolve_full_parameter_values
from simulator.full_model.solver import simulate_with_full_inputs
from simulator.service import ADM1SimulationService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _base_state() -> dict[str, float]:
    """ADM1 baseline state with enough substrate for active biological processes."""
    state = {name: 0.0 for name in FULL_STATE_NAMES}
    state.update({
        "S_su": 0.01,
        "S_aa": 0.001,
        "S_fa": 0.005,
        "S_va": 0.001,
        "S_bu": 0.001,
        "S_pro": 0.001,
        "S_ac": 0.20,
        "S_h2": 2e-7,
        "S_ch4": 0.055,
        "S_IC": 0.04,
        "S_IN": 0.01,
        "S_I": 0.02,
        "S_cation": 0.04,
        "S_anion": 0.02,
        "X_xc": 0.1,
        "X_ch": 0.028,
        "X_pr": 0.028,
        "X_li": 0.028,
        "X_su": 0.5,
        "X_aa": 0.5,
        "X_fa": 0.5,
        "X_c4": 0.5,
        "X_pro": 0.5,
        "X_ac": 1.5,
        "X_h2": 0.5,
        "X_I": 25.0,
        "S_gas_h2": 1e-5,
        "S_gas_ch4": 1.62,
        "S_gas_co2": 0.014,
    })
    return state


def _make_params(ext_name: str | list[str]) -> dict:
    """Return fully resolved parameter dict (includes derived K_pH_aa, nn_aa, etc.)."""
    ext_names = [ext_name] if isinstance(ext_name, str) else ext_name
    assembly = resolve_full_model_assembly(ext_names)
    oc = OperatingConditions(volume_m3=3400.0, temperature_c=35.0, hrt_days=20.0)
    return resolve_full_parameter_values(
        operating_conditions=oc,
        parameters=make_default_kinetics(),
        flow_rate_m3_day=170.0,
        assembly=assembly,
    )


def _run_extension(ext_name: str, extra_initial: dict[str, float] | None = None, hrt_days: float = 20.0) -> dict:
    """Build inputs with one extension active, run simulation, return results."""
    oc = OperatingConditions(volume_m3=3400.0, temperature_c=35.0, hrt_days=hrt_days)
    initial = _base_state()
    if extra_initial:
        initial.update(extra_initial)
    influent = dict(initial)
    inputs = build_backend_inputs_from_state_maps(
        operating_conditions=oc,
        parameters=make_default_kinetics(),
        influent_values=influent,
        initial_values=initial,
        flow_rate_m3_day=3400.0 / hrt_days,
        active_extensions=[ext_name],
    )
    sim = SimulationConfig(
        duration_days=10.0,
        evaluation_points=21,
        solver="BDF",
        backend="full",
        persist=False,
        full_extensions=[ext_name],
    )
    return simulate_with_full_inputs(inputs=inputs, simulation=sim)


# ---------------------------------------------------------------------------
# E6 — Lactate
# ---------------------------------------------------------------------------

class TestLactateExtension:
    def test_contribute_runs(self):
        contribution = LACTATE_EXTENSION.contribute()
        state_names = {s.name for s in contribution.states}
        assert "S_lac" in state_names
        assert "X_lac" in state_names

    def test_contribute_process_names(self):
        contribution = LACTATE_EXTENSION.contribute()
        process_names = {p.name for p in contribution.processes}
        assert "rho_E6_uptake_lactate" in process_names
        assert "rho_E6_decay_X_lac" in process_names
        # overflow process removed: S_lac is an external substrate only
        assert "rho_E6_lactate_from_sugars" not in process_names

    def test_stoichiometry_rows_cover_all_processes(self):
        contribution = LACTATE_EXTENSION.contribute()
        process_names = {p.name for p in contribution.processes if p.family == "biochemical"}
        stoich_names = set(contribution.biochemical_stoichiometry_rows.keys())
        assert process_names == stoich_names

    def test_assembly_builds_without_error(self):
        assembly = resolve_full_model_assembly(["lactate"])
        assert "S_lac" in assembly.full_state_index
        assert "X_lac" in assembly.full_state_index
        assert "rho_E6_uptake_lactate" in assembly.full_process_index

    def test_rate_function_returns_correct_keys(self):
        assembly = resolve_full_model_assembly(["lactate"])
        state = {name: 0.01 for name in assembly.full_state_names}
        state["S_H_ion"] = 1e-7
        state["S_IN"] = 0.01
        params = _make_params("lactate")
        rates = LACTATE_EXTENSION._rates(state, params)
        assert set(rates.keys()) == {"rho_E6_uptake_lactate", "rho_E6_decay_X_lac"}
        assert all(v >= 0.0 for v in rates.values())

    def test_simulation_runs_without_crash(self):
        result = _run_extension("lactate", {"S_lac": 0.05, "X_lac": 0.3})
        assert "profiles" in result
        assert "S_lac" in result["metadata"]["full_state_columns"]

    def test_lactate_decreases_when_X_lac_present(self):
        result = _run_extension("lactate", {"S_lac": 0.5, "X_lac": 0.5})
        s_lac = result["profiles"].get("S_lac")
        assert s_lac is not None, "S_lac must appear in diagnostics"
        assert s_lac[-1] <= s_lac[0] + 1e-6

    def test_diagnostics_hook_returns_expected_series(self):
        result = _run_extension("lactate", {"S_lac": 0.1, "X_lac": 0.2})
        profiles = result["profiles"]
        assert "S_lac" in profiles
        assert "X_lac" in profiles
        assert len(profiles["S_lac"]) == 21


# ---------------------------------------------------------------------------
# E10 — Ethanol
# ---------------------------------------------------------------------------

class TestEthanolExtension:
    def test_contribute_state_process_names(self):
        contribution = ETHANOL_EXTENSION.contribute()
        state_names = {s.name for s in contribution.states}
        process_names = {p.name for p in contribution.processes}
        assert {"S_et", "X_et"} <= state_names
        assert {"rho_E10_uptake_ethanol", "rho_E10_decay_X_et"} <= process_names
        # overflow process removed: S_et is an external substrate only
        assert "rho_E10_ethanol_from_sugars" not in process_names

    def test_assembly_builds_without_error(self):
        assembly = resolve_full_model_assembly(["ethanol"])
        assert "S_et" in assembly.full_state_index
        assert "X_et" in assembly.full_state_index

    def test_rate_function_nonnegative(self):
        assembly = resolve_full_model_assembly(["ethanol"])
        state = {name: 0.01 for name in assembly.full_state_names}
        state["S_H_ion"] = 1e-7
        state["S_IN"] = 0.01
        params = _make_params("ethanol")
        rates = ETHANOL_EXTENSION._rates(state, params)
        assert set(rates.keys()) == {"rho_E10_uptake_ethanol", "rho_E10_decay_X_et"}
        assert all(v >= 0.0 for v in rates.values())

    def test_simulation_runs_without_crash(self):
        result = _run_extension("ethanol", {"S_et": 0.05, "X_et": 0.3})
        assert "profiles" in result
        assert "S_et" in result["metadata"]["full_state_columns"]

    def test_diagnostics_contains_s_et_and_x_et(self):
        result = _run_extension("ethanol", {"S_et": 0.1, "X_et": 0.2})
        assert "S_et" in result["profiles"]
        assert "X_et" in result["profiles"]
        assert len(result["profiles"]["S_et"]) == 21

    def test_ethanol_c_et_less_than_c_su(self):
        """C_et = 0.02083 < C_su = 0.03125; ethanol has less C per COD than sugars."""
        assembly = resolve_full_model_assembly(["ethanol"])
        params = assembly.parameter_defaults
        assert params["C_et"] < params["C_su"]
        assert abs(params["C_et"] - 2.0 / 96.0) < 1e-5


# ---------------------------------------------------------------------------
# E11 — Phenolics
# ---------------------------------------------------------------------------

class TestPhenolicsExtension:
    def test_contribute_state_process_names(self):
        contribution = PHENOLICS_EXTENSION.contribute()
        state_names = {s.name for s in contribution.states}
        process_names = {p.name for p in contribution.processes}
        assert {"S_phen", "X_phen"} <= state_names
        assert {"rho_E11_uptake_phenolics", "rho_E11_decay_X_phen"} <= process_names

    def test_assembly_builds_without_error(self):
        assembly = resolve_full_model_assembly(["phenolics"])
        assert "S_phen" in assembly.full_state_index
        assert "K_I_phen" in assembly.parameter_defaults

    def test_rate_function_nonnegative(self):
        assembly = resolve_full_model_assembly(["phenolics"])
        state = {name: 0.01 for name in assembly.full_state_names}
        state["S_H_ion"] = 1e-7
        state["S_IN"] = 0.01
        params = _make_params("phenolics")
        rates = PHENOLICS_EXTENSION._rates(state, params)
        assert set(rates.keys()) == {"rho_E11_uptake_phenolics", "rho_E11_uptake_benzoate", "rho_E11_decay_X_phen", "rho_E11_decay_X_ben"}
        assert all(v >= 0.0 for v in rates.values())

    def test_high_phenol_reduces_rate(self):
        """Haldane inhibition dominates at S_phen >> K_I_phen, suppressing rho_E11_uptake_phenolics."""
        assembly = resolve_full_model_assembly(["phenolics"])
        params = _make_params("phenolics")
        state_low = {name: 0.01 for name in assembly.full_state_names}
        # Near K_S_phen=30.5: moderate substrate, inhibition I≈0.8 (K_I=50, S=25)
        state_low["S_phen"] = 25.0
        state_low["X_phen"] = 0.5
        state_low["S_H_ion"] = 1e-7
        state_low["S_IN"] = 0.01
        # Far above K_I_phen=50: Haldane inhibition I≈0.01 (S=500)
        state_high = dict(state_low)
        state_high["S_phen"] = 500.0
        rate_low = PHENOLICS_EXTENSION._rates(state_low, params)["rho_E11_uptake_phenolics"]
        rate_high = PHENOLICS_EXTENSION._rates(state_high, params)["rho_E11_uptake_phenolics"]
        # At S_phen=500 >> K_I_phen=50: I=1/(1+(500/50)²)≈0.01 — Haldane inhibition suppresses rate
        assert rate_high < rate_low

    def test_simulation_runs_without_crash(self):
        result = _run_extension("phenolics", {"S_phen": 0.05, "X_phen": 0.3})
        assert "profiles" in result
        assert "S_phen" in result["metadata"]["full_state_columns"]

    def test_diagnostics_contains_s_phen_and_x_phen(self):
        result = _run_extension("phenolics", {"S_phen": 0.1, "X_phen": 0.2})
        assert "S_phen" in result["profiles"]
        assert "X_phen" in result["profiles"]


# ---------------------------------------------------------------------------
# E5 — LCFA Adsorption
# ---------------------------------------------------------------------------

class TestLCFAExtension:
    def test_contribute_state_process_names(self):
        contribution = LCFA_EXTENSION.contribute()
        state_names = {s.name for s in contribution.states}
        process_names = {p.name for p in contribution.processes}
        assert "X_LCFA_ads" in state_names
        assert {"rho_E5_LCFA_adsorption", "rho_E5_LCFA_desorption", "rho_E5_LCFA_ads_degradation"} <= process_names

    def test_assembly_builds_without_error(self):
        assembly = resolve_full_model_assembly(["lcfa_adsorption"])
        assert "X_LCFA_ads" in assembly.full_state_index
        assert "k_ads_LCFA" in assembly.parameter_defaults

    def test_rate_function_nonnegative(self):
        assembly = resolve_full_model_assembly(["lcfa_adsorption"])
        state = {name: 0.01 for name in assembly.full_state_names}
        state["S_H_ion"] = 1e-7
        state["S_IN"] = 0.01
        params = _make_params("lcfa_adsorption")
        rates = LCFA_EXTENSION._rates(state, params)
        assert set(rates.keys()) == {"rho_E5_LCFA_adsorption", "rho_E5_LCFA_desorption", "rho_E5_LCFA_ads_degradation"}
        assert all(v >= 0.0 for v in rates.values())

    def test_adsorption_proportional_to_active_biomass(self):
        """rho_E5_LCFA_adsorption should increase with X_total_active."""
        assembly = resolve_full_model_assembly(["lcfa_adsorption"])
        params = _make_params("lcfa_adsorption")
        state_low = {name: 0.0 for name in assembly.full_state_names}
        state_low.update({"S_fa": 0.5, "X_su": 0.01, "S_H_ion": 1e-7, "S_IN": 0.01})
        state_high = dict(state_low)
        state_high.update({"X_su": 2.0, "X_aa": 2.0, "X_fa": 2.0})
        rate_low = LCFA_EXTENSION._rates(state_low, params)["rho_E5_LCFA_adsorption"]
        rate_high = LCFA_EXTENSION._rates(state_high, params)["rho_E5_LCFA_adsorption"]
        assert rate_high > rate_low

    def test_simulation_runs_without_crash(self):
        result = _run_extension("lcfa_adsorption", {"X_LCFA_ads": 0.05})
        assert "profiles" in result
        assert "X_LCFA_ads" in result["metadata"]["full_state_columns"]

    def test_diagnostics_contains_x_lcfa_ads(self):
        result = _run_extension("lcfa_adsorption", {"X_LCFA_ads": 0.1})
        assert "X_LCFA_ads" in result["profiles"]
        assert len(result["profiles"]["X_LCFA_ads"]) == 21


# ---------------------------------------------------------------------------
# E4 — SRB
# ---------------------------------------------------------------------------

class TestSRBExtension:
    def test_contribute_state_process_names(self):
        contribution = SRB_EXTENSION.contribute()
        state_names = {s.name for s in contribution.states}
        process_names = {p.name for p in contribution.processes}
        assert {"S_SO4", "S_H2S", "X_SRB_ac", "X_SRB_h2"} <= state_names
        assert {
            "rho_E4_SRB_uptake_ac",
            "rho_E4_SRB_uptake_h2",
            "rho_E4_decay_X_SRB_ac",
            "rho_E4_decay_X_SRB_h2",
            "rho_E4_SRB_uptake_pro",
            "rho_E4_SRB_uptake_bu",
            "rho_E4_decay_X_SRB_pro",
            "rho_E4_decay_X_SRB_bu",
            "rho_E4_H2S_transfer",
        } <= process_names

    def test_assembly_builds_without_error(self):
        assembly = resolve_full_model_assembly(["srb"])
        assert "S_SO4" in assembly.full_state_index
        assert "S_H2S" in assembly.full_state_index
        assert "k_La_H2S" in assembly.parameter_defaults

    def test_rate_function_nonnegative(self):
        assembly = resolve_full_model_assembly(["srb"])
        state = {name: 0.01 for name in assembly.full_state_names}
        state["S_H_ion"] = 1e-7
        state["S_IN"] = 0.01
        state["S_SO4"] = 0.01
        params = _make_params("srb")
        rates = SRB_EXTENSION._rates(state, params)
        assert set(rates.keys()) == {
            "rho_E4_SRB_uptake_ac",
            "rho_E4_SRB_uptake_h2",
            "rho_E4_decay_X_SRB_ac",
            "rho_E4_decay_X_SRB_h2",
            "rho_E4_SRB_uptake_pro",
            "rho_E4_SRB_uptake_bu",
            "rho_E4_decay_X_SRB_pro",
            "rho_E4_decay_X_SRB_bu",
            "rho_E4_H2S_transfer",
        }
        # Gas-liquid transfer can be negative (re-absorption), so check only biochemical rates
        for k, v in rates.items():
            if k != "rho_E4_H2S_transfer":
                assert v >= 0.0, f"{k} = {v} < 0"

    def test_no_sulfate_no_srb_activity(self):
        """SRB rates must be zero when S_SO4 = 0."""
        assembly = resolve_full_model_assembly(["srb"])
        state = {name: 0.01 for name in assembly.full_state_names}
        state.update({"S_H_ion": 1e-7, "S_IN": 0.01, "S_SO4": 0.0, "X_SRB_ac": 1.0, "X_SRB_h2": 1.0})
        params = _make_params("srb")
        rates = SRB_EXTENSION._rates(state, params)
        assert rates["rho_E4_SRB_uptake_ac"] == pytest.approx(0.0, abs=1e-10)
        assert rates["rho_E4_SRB_uptake_h2"] == pytest.approx(0.0, abs=1e-10)

    def test_h2s_stripping_proportional_to_h2s(self):
        """rho_E4_H2S_transfer must use Henry's law formulation."""
        assembly = resolve_full_model_assembly(["srb"])
        state = {name: 0.0 for name in assembly.full_state_names}
        state["S_H2S"] = 0.05
        state["S_gas_H2S"] = 0.0
        state["S_H_ion"] = 1e-7
        state["S_IN"] = 0.01
        params = _make_params("srb")
        rates = SRB_EXTENSION._rates(state, params)
        # With S_gas_H2S=0, transfer = k_La_H2S * S_H2S
        expected = params["k_La_H2S"] * 0.05
        assert rates["rho_E4_H2S_transfer"] == pytest.approx(expected, rel=1e-9)

    def test_simulation_runs_without_crash(self):
        result = _run_extension("srb", {"S_SO4": 0.01, "X_SRB_ac": 0.3, "X_SRB_h2": 0.1})
        assert "profiles" in result
        assert "S_SO4" in result["metadata"]["full_state_columns"]
        assert "S_H2S" in result["metadata"]["full_state_columns"]

    def test_sulfate_decreases_when_srb_present(self):
        """S_SO4 should decrease over time with active SRB and sufficient substrate."""
        result = _run_extension("srb", {
            "S_ac": 0.8,
            "S_SO4": 0.02,
            "X_SRB_ac": 0.5,
            "X_SRB_h2": 0.1,
        })
        s_so4 = result["profiles"].get("S_SO4")
        assert s_so4 is not None
        assert s_so4[-1] < s_so4[0] + 1e-6

    def test_diagnostics_returns_all_srb_series(self):
        result = _run_extension("srb", {"S_SO4": 0.01, "X_SRB_ac": 0.2, "X_SRB_h2": 0.1})
        profiles = result["profiles"]
        assert "S_SO4" in profiles
        assert "S_H2S" in profiles
        assert "X_SRB_ac" in profiles
        assert "X_SRB_h2" in profiles


# ---------------------------------------------------------------------------
# Combined: two extensions together
# ---------------------------------------------------------------------------

class TestMultipleExtensions:
    def test_lactate_and_ethanol_together(self):
        """Both E6+E10 can coexist in the same assembly."""
        assembly = resolve_full_model_assembly(["lactate", "ethanol"])
        assert "S_lac" in assembly.full_state_index
        assert "S_et" in assembly.full_state_index

    def test_srb_and_lcfa_together(self):
        """E4+E5 can coexist in the same assembly."""
        assembly = resolve_full_model_assembly(["srb", "lcfa_adsorption"])
        assert "S_SO4" in assembly.full_state_index
        assert "X_LCFA_ads" in assembly.full_state_index

    def test_all_extensions_together_build(self):
        """All 5 new extensions can coexist in one assembly without conflict."""
        assembly = resolve_full_model_assembly(["lactate", "ethanol", "phenolics", "lcfa_adsorption", "srb"])
        assert len(assembly.active_extensions) == 5
        for state_name in ["S_lac", "S_et", "S_phen", "X_LCFA_ads", "S_SO4", "S_H2S"]:
            assert state_name in assembly.full_state_index

    def test_all_extensions_together_simulate(self):
        """All 5 new extensions simulate together without crash."""
        oc = OperatingConditions(volume_m3=3400.0, temperature_c=35.0, hrt_days=20.0)
        initial = _base_state()
        initial.update({
            "S_lac": 0.02, "X_lac": 0.1,
            "S_et": 0.02, "X_et": 0.1,
            "S_phen": 0.01, "X_phen": 0.1,
            "X_LCFA_ads": 0.05,
            "S_SO4": 0.01, "X_SRB_ac": 0.1, "X_SRB_h2": 0.05,
        })
        ext_names = ["lactate", "ethanol", "phenolics", "lcfa_adsorption", "srb"]
        inputs = build_backend_inputs_from_state_maps(
            operating_conditions=oc,
            parameters=make_default_kinetics(),
            influent_values=initial,
            initial_values=initial,
            flow_rate_m3_day=170.0,
            active_extensions=ext_names,
        )
        sim = SimulationConfig(
            duration_days=5.0,
            evaluation_points=21,
            solver="BDF",
            backend="full",
            persist=False,
            full_extensions=ext_names,
        )
        result = simulate_with_full_inputs(inputs=inputs, simulation=sim)
        assert "profiles" in result
        assert result["profiles"]["biogas_m3_day"][-1] >= 0.0


class TestExtensionStateOverrides:
    def test_service_applies_srb_state_overrides_to_full_backend(self):
        service = ADM1SimulationService()
        feed = make_default_feed().model_copy(update={"acetate": 0.8, "propionate": 0.35})
        initial = make_default_initial_state(feed)
        simulation = SimulationConfig(
            duration_days=10.0,
            evaluation_points=21,
            solver="BDF",
            backend="full",
            persist=False,
            full_extensions=["srb"],
            full_initial_state_overrides={
                "S_SO4": 0.02,
                "X_SRB_ac": 0.4,
                "X_SRB_h2": 0.1,
                "X_SRB_pro": 0.05,
            },
            full_influent_state_overrides={"S_SO4": 0.02},
        )

        result = service.simulate(
            "cstr",
            operating_conditions=make_default_operating_conditions(),
            feed=feed,
            initial_state=initial,
            parameters=make_default_kinetics(),
            simulation=simulation,
        )

        sulfate_series = result.series.get("S_SO4")
        sulfide_series = result.series.get("S_H2S")
        assert sulfate_series is not None
        assert sulfide_series is not None
        assert max(sulfate_series) > 0.0
        assert max(result.series.get("X_SRB_ac", [])) > 0.0
        assert sulfate_series[-1] < sulfate_series[0] + 1e-6
        assert sulfide_series[-1] >= sulfide_series[0]


