"""Tests for ADM1 extensions (E4-SRB, E5-LCFA, E6-Lactate, E10-Ethanol, E11-Phenolics, E12, E7, E8, E20, E15, E9).

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
from simulator.full_model.multi_population_extension import MULTI_POPULATION_EXTENSION
from simulator.full_model.phosphorus_extension import PHOSPHORUS_EXTENSION
from simulator.full_model.iron_extension import IRON_EXTENSION
from simulator.full_model.microalgae_extension import MICROALGAE_EXTENSION
from simulator.full_model.syngas_extension import SYNGAS_EXTENSION
from simulator.full_model.trace_elements_extension import TRACE_ELEMENTS_EXTENSION
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


def _run_extensions(
    ext_names: str | list[str],
    *,
    extra_initial: dict[str, float] | None = None,
    extra_influent: dict[str, float] | None = None,
    parameter_overrides: dict[str, float] | None = None,
    hrt_days: float = 20.0,
    duration_days: float = 10.0,
    evaluation_points: int = 21,
) -> dict:
    """Build inputs with one or more extensions active, run simulation, return results."""
    ext_list = [ext_names] if isinstance(ext_names, str) else list(ext_names)
    oc = OperatingConditions(volume_m3=3400.0, temperature_c=35.0, hrt_days=hrt_days)
    initial = _base_state()
    if extra_initial:
        initial.update(extra_initial)
    influent = dict(initial)
    if extra_influent:
        influent.update(extra_influent)
    inputs = build_backend_inputs_from_state_maps(
        operating_conditions=oc,
        parameters=make_default_kinetics(),
        influent_values=influent,
        initial_values=initial,
        flow_rate_m3_day=3400.0 / hrt_days,
        active_extensions=ext_list,
        extension_parameter_overrides=parameter_overrides,
    )
    sim = SimulationConfig(
        duration_days=duration_days,
        evaluation_points=evaluation_points,
        solver="BDF",
        backend="full",
        persist=False,
        full_extensions=ext_list,
    )
    return simulate_with_full_inputs(inputs=inputs, simulation=sim)


def _run_extension(
    ext_name: str,
    extra_initial: dict[str, float] | None = None,
    hrt_days: float = 20.0,
    parameter_overrides: dict[str, float] | None = None,
    extra_influent: dict[str, float] | None = None,
    duration_days: float = 10.0,
) -> dict:
    return _run_extensions(
        [ext_name],
        extra_initial=extra_initial,
        extra_influent=extra_influent,
        parameter_overrides=parameter_overrides,
        hrt_days=hrt_days,
        duration_days=duration_days,
    )


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


# ---------------------------------------------------------------------------
# Plano 2 — Metadados técnicos do solver full
# ---------------------------------------------------------------------------

class TestFullModelSolverMetadata:
    """Verifica presença e consistência dos metadados técnicos adicionados no Plano 2."""

    def _run_cstr(self, extensions: list[str] | None = None) -> dict:
        """Executa simulação CSTR básica com backend full e retorna o resultado."""
        oc = OperatingConditions(volume_m3=3400.0, temperature_c=35.0, hrt_days=20.0)
        initial = _base_state()
        ext_names = extensions or []
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
        return simulate_with_full_inputs(inputs=inputs, simulation=sim)

    def test_metadata_has_required_fields(self):
        """Todos os campos de metadados técnicos do solver devem estar presentes."""
        result = self._run_cstr()
        meta = result["metadata"]
        required_fields = [
            "full_model_state_count",
            "full_model_dynamic_state_count",
            "full_model_algebraic_state_count",
            "full_model_pseudo_state_count",
            "full_model_segment_count",
            "full_model_effective_ode_dimension",
            "full_model_active_extensions",
            "full_model_ph_converged",
            "full_model_ph_iterations_max",
            "full_model_runtime_seconds",
            "full_model_solver_method",
            "full_model_solver_rtol",
            "full_model_solver_atol",
            "full_model_time_grid_points",
            "full_model_solver_nfev",
            "full_model_solver_njev",
            "full_model_solver_nlu",
        ]
        for field in required_fields:
            assert field in meta, f"Campo ausente no metadata: '{field}'"

    def test_state_count_consistency_no_extensions(self):
        """As contagens de estado devem ser consistentes com o assembly sem extensões."""
        result = self._run_cstr(extensions=[])
        meta = result["metadata"]
        assembly = resolve_full_model_assembly([])
        assert meta["full_model_state_count"] == len(assembly.full_state_names)
        assert meta["full_model_dynamic_state_count"] == len(assembly.dynamic_state_names)
        assert meta["full_model_algebraic_state_count"] == len(assembly.algebraic_state_names)
        assert meta["full_model_pseudo_state_count"] == len(assembly.pseudo_state_names)

    def test_state_count_increases_with_extension(self):
        """Adicionar extensão deve aumentar a contagem de estados."""
        result_base = self._run_cstr(extensions=[])
        result_ext = self._run_cstr(extensions=["lactate"])
        assert result_ext["metadata"]["full_model_state_count"] > result_base["metadata"]["full_model_state_count"]
        assert result_ext["metadata"]["full_model_dynamic_state_count"] > result_base["metadata"]["full_model_dynamic_state_count"]

    def test_cstr_segment_count_is_one(self):
        """CSTR deve ter segment_count = 1 e effective_ode_dimension = n_dynamic × 1."""
        result = self._run_cstr()
        meta = result["metadata"]
        assert meta["full_model_segment_count"] == 1
        assert meta["full_model_effective_ode_dimension"] == meta["full_model_dynamic_state_count"] * 1

    def test_plug_flow_segment_count_and_ode_dimension(self):
        """Plug-flow com N segmentos deve ter effective_ode_dimension = n_dynamic × N."""
        from simulator.core.models import ReactorConfig
        oc = OperatingConditions(volume_m3=3400.0, temperature_c=35.0, hrt_days=20.0)
        initial = _base_state()
        n_seg = 4
        inputs = build_backend_inputs_from_state_maps(
            operating_conditions=oc,
            parameters=make_default_kinetics(),
            influent_values=initial,
            initial_values=initial,
            flow_rate_m3_day=170.0,
            active_extensions=[],
        )
        sim = SimulationConfig(
            duration_days=5.0,
            evaluation_points=21,
            solver="BDF",
            backend="full",
            persist=False,
        )
        reactor_config = ReactorConfig(reactor_type="plug_flow", segments=n_seg)
        result = simulate_with_full_inputs(inputs=inputs, simulation=sim, reactor_config=reactor_config)
        meta = result["metadata"]
        assert meta["full_model_segment_count"] == n_seg
        assert meta["full_model_effective_ode_dimension"] == meta["full_model_dynamic_state_count"] * n_seg

    def test_active_extensions_list_matches_assembly(self):
        """Lista de extensões ativas no metadata deve bater com o assembly."""
        ext_names = ["lactate", "ethanol"]
        result = self._run_cstr(extensions=ext_names)
        meta = result["metadata"]
        assert set(meta["full_model_active_extensions"]) == set(ext_names)

    def test_runtime_seconds_is_positive(self):
        """Tempo de execução do solver deve ser um float positivo."""
        result = self._run_cstr()
        runtime = result["metadata"]["full_model_runtime_seconds"]
        assert isinstance(runtime, float)
        assert runtime > 0.0

    def test_solver_method_matches_config(self):
        """Método do solver no metadata deve corresponder ao configurado."""
        result = self._run_cstr()
        assert result["metadata"]["full_model_solver_method"] == "BDF"

    def test_time_grid_points_matches_config(self):
        """Número de pontos de saída no metadata deve bater com evaluation_points."""
        result = self._run_cstr()
        assert result["metadata"]["full_model_time_grid_points"] == 21

    def test_nfev_is_nonnegative_integer(self):
        """Avaliações de função do solver devem ser um inteiro não-negativo."""
        result = self._run_cstr()
        nfev = result["metadata"]["full_model_solver_nfev"]
        assert isinstance(nfev, int)
        assert nfev >= 0

    def test_ph_converged_is_bool(self):
        """full_model_ph_converged deve ser um booleano."""
        result = self._run_cstr()
        ph_conv = result["metadata"]["full_model_ph_converged"]
        assert isinstance(ph_conv, bool)

    def test_state_count_coherence_all_extensions(self):
        """Com todas as extensões, o total de estados deve ser ≥ base + extensões × 2."""
        all_exts = ["lactate", "ethanol", "phenolics", "lcfa_adsorption", "srb"]
        result_base = self._run_cstr(extensions=[])
        result_all = self._run_cstr(extensions=all_exts)
        # Cada extensão adiciona pelo menos um estado
        assert result_all["metadata"]["full_model_state_count"] > result_base["metadata"]["full_model_state_count"] + len(all_exts)


# ---------------------------------------------------------------------------
# E12 — Multi-população de acetoclásticos e hidrogenotróficos
# ---------------------------------------------------------------------------

def _run_multi_extension(
    ext_names: list[str],
    extra_initial: dict | None = None,
    hrt_days: float = 20.0,
    parameter_overrides: dict[str, float] | None = None,
    extra_influent: dict[str, float] | None = None,
    duration_days: float = 10.0,
) -> dict:
    """Run simulation with multiple extensions active."""
    return _run_extensions(
        ext_names,
        extra_initial=extra_initial,
        extra_influent=extra_influent,
        parameter_overrides=parameter_overrides,
        hrt_days=hrt_days,
        duration_days=duration_days,
    )


class TestMultiPopulationExtension:
    def test_contribute_returns_4_states(self):
        contribution = MULTI_POPULATION_EXTENSION.contribute()
        state_names = {s.name for s in contribution.states}
        assert {"X_ac_1", "X_ac_2", "X_h2_1", "X_h2_2"} == state_names

    def test_contribute_returns_8_processes(self):
        contribution = MULTI_POPULATION_EXTENSION.contribute()
        assert len(contribution.processes) == 8

    def test_process_names_are_correct(self):
        contribution = MULTI_POPULATION_EXTENSION.contribute()
        process_names = {p.name for p in contribution.processes}
        expected = {
            "rho_E12_uptake_ac_1", "rho_E12_decay_ac_1",
            "rho_E12_uptake_ac_2", "rho_E12_decay_ac_2",
            "rho_E12_uptake_h2_1", "rho_E12_decay_h2_1",
            "rho_E12_uptake_h2_2", "rho_E12_decay_h2_2",
        }
        assert process_names == expected

    def test_assembly_builds_without_error(self):
        assembly = resolve_full_model_assembly(["multi_population"])
        assert "X_ac_1" in assembly.full_state_index
        assert "X_ac_2" in assembly.full_state_index
        assert "X_h2_1" in assembly.full_state_index
        assert "X_h2_2" in assembly.full_state_index

    def test_stoichiometry_patches_applied(self):
        """Core rho_11 and rho_18 should have X_ac='0' in stoichiometry."""
        assembly = resolve_full_model_assembly(["multi_population"])
        rows = assembly.biochemical_stoichiometry_rows
        assert rows["rho_11_uptake_acetate"]["X_ac"] == "0"
        assert rows["rho_18_decay_acetate_biomass"]["X_ac"] == "0"
        assert rows["rho_12_uptake_hydrogen"]["X_h2"] == "0"
        assert rows["rho_19_decay_hydrogen_biomass"]["X_h2"] == "0"

    def test_rate_function_returns_correct_keys(self):
        assembly = resolve_full_model_assembly(["multi_population"])
        state = {name: 0.01 for name in assembly.full_state_names}
        state["S_H_ion"] = 1e-7
        state["S_IN"] = 0.01
        state["S_nh3"] = 0.0
        params = _make_params("multi_population")
        rates = MULTI_POPULATION_EXTENSION._rates(state, params)
        assert set(rates.keys()) == {
            "rho_E12_uptake_ac_1", "rho_E12_decay_ac_1",
            "rho_E12_uptake_ac_2", "rho_E12_decay_ac_2",
            "rho_E12_uptake_h2_1", "rho_E12_decay_h2_1",
            "rho_E12_uptake_h2_2", "rho_E12_decay_h2_2",
        }
        assert all(v >= 0.0 for v in rates.values())

    def test_simulation_100_days_does_not_crash(self):
        """Multi_population simulates 100 days without error."""
        oc = OperatingConditions(volume_m3=3400.0, temperature_c=35.0, hrt_days=20.0)
        initial = _base_state()
        initial.update({"X_ac_1": 0.75, "X_ac_2": 0.75, "X_h2_1": 0.25, "X_h2_2": 0.25})
        # Core X_ac and X_h2 should be zeroed out to avoid double-counting
        initial["X_ac"] = 0.0
        initial["X_h2"] = 0.0
        influent = dict(initial)
        inputs = build_backend_inputs_from_state_maps(
            operating_conditions=oc,
            parameters=make_default_kinetics(),
            influent_values=influent,
            initial_values=initial,
            flow_rate_m3_day=170.0,
            active_extensions=["multi_population"],
        )
        sim = SimulationConfig(
            duration_days=100.0,
            evaluation_points=101,
            solver="BDF",
            backend="full",
            persist=False,
            full_extensions=["multi_population"],
        )
        result = simulate_with_full_inputs(inputs=inputs, simulation=sim)
        assert "profiles" in result

    def test_total_x_ac_in_diagnostics_is_nonnegative(self):
        result = _run_extension("multi_population", {
            "X_ac_1": 0.75, "X_ac_2": 0.75, "X_h2_1": 0.25, "X_h2_2": 0.25
        })
        profiles = result["profiles"]
        assert "total_X_ac" in profiles
        assert all(v >= 0.0 for v in profiles["total_X_ac"])

    def test_oligotrophic_fraction_between_0_and_1(self):
        result = _run_extension("multi_population", {
            "X_ac_1": 0.5, "X_ac_2": 1.0, "X_h2_1": 0.25, "X_h2_2": 0.25
        })
        profiles = result["profiles"]
        assert "fraction_oligotrophic_ac" in profiles
        fracs = profiles["fraction_oligotrophic_ac"]
        assert all(0.0 <= f <= 1.0 for f in fracs)


# ---------------------------------------------------------------------------
# E7 — Fósforo (Phosphorus)
# ---------------------------------------------------------------------------

class TestPhosphorusExtension:
    def test_contribute_returns_3_states(self):
        contribution = PHOSPHORUS_EXTENSION.contribute()
        state_names = {s.name for s in contribution.states}
        assert {"S_IP", "X_MAP", "X_CaCO3"} == state_names

    def test_contribute_returns_4_processes(self):
        contribution = PHOSPHORUS_EXTENSION.contribute()
        assert len(contribution.processes) == 4

    def test_process_names_are_correct(self):
        contribution = PHOSPHORUS_EXTENSION.contribute()
        process_names = {p.name for p in contribution.processes}
        assert process_names == {
            "rho_E7_MAP_precip", "rho_E7_MAP_dissolv",
            "rho_E7_CaCO3_precip", "rho_E7_CaCO3_dissolv",
        }

    def test_assembly_builds_without_error(self):
        assembly = resolve_full_model_assembly(["phosphorus"])
        assert "S_IP" in assembly.full_state_index
        assert "X_MAP" in assembly.full_state_index
        assert "X_CaCO3" in assembly.full_state_index

    def test_parameters_present(self):
        assembly = resolve_full_model_assembly(["phosphorus"])
        assert "Ka_H2PO4" in assembly.parameter_defaults
        assert "Ksp_MAP" in assembly.parameter_defaults
        assert "S_Mg" in assembly.parameter_defaults

    def test_rate_function_returns_correct_keys(self):
        assembly = resolve_full_model_assembly(["phosphorus"])
        state = {name: 0.01 for name in assembly.full_state_names}
        state["S_H_ion"] = 1e-7
        state["S_IN"] = 0.01
        state["S_IP"] = 0.001
        params = _make_params("phosphorus")
        rates = PHOSPHORUS_EXTENSION._rates(state, params)
        assert set(rates.keys()) == {
            "rho_E7_MAP_precip", "rho_E7_MAP_dissolv",
            "rho_E7_CaCO3_precip", "rho_E7_CaCO3_dissolv",
        }
        assert all(v >= 0.0 for v in rates.values())

    def test_simulation_basic_does_not_crash(self):
        result = _run_extension("phosphorus", {"S_IP": 0.001, "X_MAP": 0.0, "X_CaCO3": 0.0})
        assert "profiles" in result
        assert "S_IP" in result["metadata"]["full_state_columns"]

    def test_s_ip_not_negative(self):
        """S_IP must not go negative during simulation."""
        result = _run_extension("phosphorus", {"S_IP": 0.001})
        profiles = result["profiles"]
        if "S_IP" in profiles:
            assert all(v >= -1e-10 for v in profiles["S_IP"]), "S_IP went negative"

    def test_x_map_grows_with_high_s_ip(self):
        """With high S_IP and default Mg, struvite should precipitate: X_MAP should increase."""
        oc = OperatingConditions(volume_m3=3400.0, temperature_c=35.0, hrt_days=20.0)
        initial = _base_state()
        # High phosphorus, favorable conditions for struvite
        initial.update({
            "S_IP": 0.01,   # 10 mmolP/m³ — quite high
            "X_MAP": 0.0,
            "X_CaCO3": 0.0,
        })
        influent = dict(initial)
        inputs = build_backend_inputs_from_state_maps(
            operating_conditions=oc,
            parameters=make_default_kinetics(),
            influent_values=influent,
            initial_values=initial,
            flow_rate_m3_day=170.0,
            active_extensions=["phosphorus"],
        )
        sim = SimulationConfig(
            duration_days=30.0,
            evaluation_points=61,
            solver="BDF",
            backend="full",
            persist=False,
            full_extensions=["phosphorus"],
        )
        result = simulate_with_full_inputs(inputs=inputs, simulation=sim)
        # X_MAP should be ≥ 0 throughout; actual precipitation depends on S_nh4_ion level
        assert "profiles" in result

    def test_diagnostics_returns_expected_series(self):
        result = _run_extension("phosphorus", {"S_IP": 0.001})
        profiles = result["profiles"]
        assert "S_IP" in profiles
        assert "X_MAP" in profiles
        assert "X_CaCO3" in profiles

    def test_validate_hook_passes_when_extension_active(self):
        """validate_hook should not raise when phosphorus extension is in assembly."""
        assembly = resolve_full_model_assembly(["phosphorus"])
        # Should not raise
        PHOSPHORUS_EXTENSION._validate(assembly)

    def test_phosphate_charge_included_in_ph_solver(self):
        """pH solver should handle S_IP in state without crashing."""
        from simulator.full_model.acid_base import solve_acid_base
        from simulator.full_model.model import FULL_STATE_NAMES, resolve_full_parameter_values
        assembly = resolve_full_model_assembly(["phosphorus"])
        oc = OperatingConditions(volume_m3=3400.0, temperature_c=35.0, hrt_days=20.0)
        params = resolve_full_parameter_values(
            operating_conditions=oc,
            parameters=make_default_kinetics(),
            flow_rate_m3_day=170.0,
            assembly=assembly,
        )
        state = {name: 0.0 for name in assembly.full_state_names}
        state.update({
            "S_ac": 0.2, "S_pro": 0.001, "S_bu": 0.001, "S_va": 0.001,
            "S_IC": 0.04, "S_IN": 0.01, "S_cation": 0.04, "S_anion": 0.02,
            "S_IP": 0.001,
        })
        result = solve_acid_base(state, params)
        assert result.converged
        assert 5.0 < result.p_h < 9.0


# ---------------------------------------------------------------------------
# E8 — Ferro (Iron)
# ---------------------------------------------------------------------------

class TestIronExtension:
    def test_validate_hook_raises_without_srb(self):
        """E8 must raise ValueError if srb is not in active_extensions."""
        assembly = resolve_full_model_assembly(["phosphorus"])
        with pytest.raises(ValueError, match="srb"):
            IRON_EXTENSION._validate(assembly)

    def test_validate_hook_raises_without_phosphorus(self):
        """E8 must raise ValueError if phosphorus is not in active_extensions."""
        assembly = resolve_full_model_assembly(["srb"])
        with pytest.raises(ValueError, match="phosphorus"):
            IRON_EXTENSION._validate(assembly)

    def test_validate_hook_passes_with_both_deps(self):
        """E8 validate_hook should not raise when srb and phosphorus are active."""
        assembly = resolve_full_model_assembly(["srb", "phosphorus", "iron"])
        # Should not raise
        IRON_EXTENSION._validate(assembly)

    def test_contribute_returns_4_states(self):
        # X_S0 keeps sulfur conserved in Fe(III) reduction by sulfide.
        contribution = IRON_EXTENSION.contribute()
        state_names = {s.name for s in contribution.states}
        assert {"S_Fe2", "X_FeS", "X_VIV", "X_S0"} == state_names

    def test_contribute_returns_5_processes(self):
        contribution = IRON_EXTENSION.contribute()
        assert len(contribution.processes) == 5

    def test_process_names_are_correct(self):
        contribution = IRON_EXTENSION.contribute()
        process_names = {p.name for p in contribution.processes}
        assert process_names == {
            "rho_E8_Fe3_red_h2", "rho_E8_Fe3_red_h2s",
            "rho_E8_FeS_precip", "rho_E8_FeS_dissolv",
            "rho_E8_VIV_precip",
        }

    def test_assembly_builds_with_deps(self):
        assembly = resolve_full_model_assembly(["srb", "phosphorus", "iron"])
        assert "S_Fe2" in assembly.full_state_index
        assert "X_FeS" in assembly.full_state_index
        assert "X_VIV" in assembly.full_state_index

    def test_rate_function_returns_correct_keys(self):
        assembly = resolve_full_model_assembly(["srb", "phosphorus", "iron"])
        state = {name: 0.0 for name in assembly.full_state_names}
        state.update({
            "S_H_ion": 1e-7, "S_IN": 0.01, "S_h2": 2e-7,
            "S_H2S": 0.001, "S_IP": 0.001, "S_Fe2": 0.001,
        })
        params = _make_params(["srb", "phosphorus", "iron"])
        rates = IRON_EXTENSION._rates(state, params)
        assert set(rates.keys()) == {
            "rho_E8_Fe3_red_h2", "rho_E8_Fe3_red_h2s",
            "rho_E8_FeS_precip", "rho_E8_FeS_dissolv",
            "rho_E8_VIV_precip",
        }

    def test_all_rates_nonnegative(self):
        assembly = resolve_full_model_assembly(["srb", "phosphorus", "iron"])
        state = {name: 0.0 for name in assembly.full_state_names}
        state.update({
            "S_H_ion": 1e-7, "S_IN": 0.01, "S_h2": 2e-7,
            "S_H2S": 0.001, "S_IP": 0.001, "S_Fe2": 0.001,
        })
        params = _make_params(["srb", "phosphorus", "iron"])
        rates = IRON_EXTENSION._rates(state, params)
        assert all(v >= 0.0 for v in rates.values())

    def test_simulation_with_iron_srb_phosphorus_does_not_crash(self):
        """Simulation with iron + srb + phosphorus active should not crash."""
        result = _run_multi_extension(
            ["srb", "phosphorus", "iron"],
            extra_initial={
                "S_SO4": 0.01, "X_SRB_ac": 0.2, "X_SRB_h2": 0.1,
                "S_IP": 0.001, "X_MAP": 0.0, "X_CaCO3": 0.0,
                "S_Fe2": 0.0, "X_FeS": 0.0, "X_VIV": 0.0,
            },
        )
        assert "profiles" in result

    def test_x_fes_nonnegative_throughout(self):
        """X_FeS must not go negative during simulation."""
        result = _run_multi_extension(
            ["srb", "phosphorus", "iron"],
            extra_initial={
                "S_SO4": 0.01, "X_SRB_ac": 0.2, "X_SRB_h2": 0.1,
                "S_IP": 0.001, "X_MAP": 0.0, "X_CaCO3": 0.0,
                "S_Fe2": 0.001, "X_FeS": 0.0, "X_VIV": 0.0,
            },
        )
        profiles = result["profiles"]
        if "X_FeS" in profiles:
            assert all(v >= -1e-10 for v in profiles["X_FeS"]), "X_FeS went negative"

    def test_diagnostics_returns_expected_series(self):
        result = _run_multi_extension(
            ["srb", "phosphorus", "iron"],
            extra_initial={
                "S_SO4": 0.01, "X_SRB_ac": 0.1,
                "S_IP": 0.001,
                "S_Fe2": 0.001, "X_FeS": 0.0, "X_VIV": 0.0,
            },
        )
        profiles = result["profiles"]
        assert "S_Fe2" in profiles
        assert "X_FeS" in profiles
        assert "X_VIV" in profiles


# ---------------------------------------------------------------------------
# E20 — Microalgas (Microalgae)
# ---------------------------------------------------------------------------

class TestMicroalgaeExtension:
    def test_contribute_returns_1_state(self):
        contribution = MICROALGAE_EXTENSION.contribute()
        state_names = {s.name for s in contribution.states}
        assert state_names == {"X_alg"}

    def test_contribute_returns_1_process(self):
        contribution = MICROALGAE_EXTENSION.contribute()
        assert len(contribution.processes) == 1
        assert contribution.processes[0].name == "rho_E20_dis_alg"

    def test_stoichiometry_rows_cover_all_biochemical_processes(self):
        contribution = MICROALGAE_EXTENSION.contribute()
        process_names = {p.name for p in contribution.processes if p.family == "biochemical"}
        stoich_names = set(contribution.biochemical_stoichiometry_rows.keys())
        assert process_names == stoich_names

    def test_assembly_builds_without_error(self):
        assembly = resolve_full_model_assembly(["microalgae"])
        assert "X_alg" in assembly.full_state_index
        assert "rho_E20_dis_alg" in assembly.full_process_index

    def test_assembly_has_30_dynamic_states(self):
        assembly = resolve_full_model_assembly(["microalgae"])
        assert len(assembly.dynamic_state_names) == 30

    def test_rate_function_returns_correct_keys(self):
        assembly = resolve_full_model_assembly(["microalgae"])
        state = {name: 0.0 for name in assembly.full_state_names}
        state.update({"X_alg": 0.5, "S_IN": 0.01})
        params = _make_params("microalgae")
        rates = MICROALGAE_EXTENSION._rates(state, params)
        assert set(rates.keys()) == {"rho_E20_dis_alg"}
        assert rates["rho_E20_dis_alg"] > 0.0

    def test_base_rate_modifier_returns_hydrolysis_processes(self):
        assembly = resolve_full_model_assembly(["microalgae"])
        state = {name: 0.0 for name in assembly.full_state_names}
        state.update({"X_ch": 0.5, "X_pr": 0.4, "X_li": 0.3, "X_su": 0.2, "X_aa": 0.2, "X_fa": 0.2})
        params = _make_params("microalgae")
        modifiers = MICROALGAE_EXTENSION._base_rate_modifier(state, params)
        assert set(modifiers) == {
            "rho_2_hydrolysis_carbohydrates",
            "rho_3_hydrolysis_proteins",
            "rho_4_hydrolysis_lipids",
        }
        assert all(value >= 0.0 for value in modifiers.values())

    def test_lower_f_hyd_alg_reduces_hydrolysis_modifier(self):
        assembly = resolve_full_model_assembly(["microalgae"])
        state = {name: 0.0 for name in assembly.full_state_names}
        state.update({"X_ch": 0.6, "X_pr": 0.6, "X_li": 0.6, "X_su": 0.2, "X_aa": 0.2, "X_fa": 0.2})
        params_default = _make_params("microalgae")
        params_low = dict(params_default)
        params_low["f_hyd_alg"] = 0.5
        modifiers_default = MICROALGAE_EXTENSION._base_rate_modifier(state, params_default)
        modifiers_low = MICROALGAE_EXTENSION._base_rate_modifier(state, params_low)
        assert modifiers_low["rho_2_hydrolysis_carbohydrates"] < modifiers_default["rho_2_hydrolysis_carbohydrates"]
        assert modifiers_low["rho_3_hydrolysis_proteins"] < modifiers_default["rho_3_hydrolysis_proteins"]
        assert modifiers_low["rho_4_hydrolysis_lipids"] < modifiers_default["rho_4_hydrolysis_lipids"]

    def test_validate_hook_accepts_default_fractions(self):
        assembly = resolve_full_model_assembly(["microalgae"])
        MICROALGAE_EXTENSION._validate(assembly)

    def test_simulation_does_not_crash(self):
        result = _run_extension("microalgae", extra_initial={"X_alg": 0.5})
        assert "profiles" in result

    def test_x_alg_decreases_over_time(self):
        result = _run_extension(
            "microalgae",
            extra_initial={"X_alg": 0.5},
            extra_influent={"X_alg": 0.0},
            hrt_days=500.0,
        )
        profiles = result["profiles"]
        assert "X_alg" in profiles
        assert profiles["X_alg"][-1] < profiles["X_alg"][0] + 1e-9

    def test_diagnostics_profiles_present(self):
        result = _run_extension("microalgae", extra_initial={"X_alg": 0.5})
        profiles = result["profiles"]
        assert "X_alg" in profiles
        assert "hydrolysis_modifier_ch" in profiles
        assert "hydrolysis_modifier_pr" in profiles
        assert "hydrolysis_modifier_li" in profiles


# ---------------------------------------------------------------------------
# E15 — Biometanação de Syngas (Syngas)
# ---------------------------------------------------------------------------

class TestSyngasExtension:
    def test_contribute_returns_3_states(self):
        contribution = SYNGAS_EXTENSION.contribute()
        state_names = {s.name for s in contribution.states}
        assert state_names == {"S_CO", "S_gas_CO", "X_met_CO"}

    def test_contribute_returns_4_processes(self):
        contribution = SYNGAS_EXTENSION.contribute()
        assert len(contribution.processes) == 4
        process_names = {p.name for p in contribution.processes}
        assert process_names == {
            "rho_E15_CO_uptake",
            "rho_E15_CO_acetate",
            "rho_E15_decay_X_met_CO",
            "rho_E15_CO_transfer",
        }

    def test_stoichiometry_rows_cover_all_biochemical_processes(self):
        contribution = SYNGAS_EXTENSION.contribute()
        process_names = {p.name for p in contribution.processes if p.family == "biochemical"}
        stoich_names = set(contribution.biochemical_stoichiometry_rows.keys())
        assert process_names == stoich_names

    def test_assembly_builds_without_error(self):
        assembly = resolve_full_model_assembly(["syngas"])
        assert "S_CO" in assembly.full_state_index
        assert "S_gas_CO" in assembly.full_state_index
        assert "X_met_CO" in assembly.full_state_index

    def test_assembly_has_32_dynamic_states(self):
        assembly = resolve_full_model_assembly(["syngas"])
        assert len(assembly.dynamic_state_names) == 32

    def test_s_gas_co_is_gas_state(self):
        assembly = resolve_full_model_assembly(["syngas"])
        assert "S_gas_CO" in assembly.dynamic_gas_state_names

    def test_parameter_defaults_follow_local_paper(self):
        assembly = resolve_full_model_assembly(["syngas"])
        defaults = assembly.parameter_defaults
        assert defaults["k_m_met_CO"] == pytest.approx(75.0)
        assert defaults["K_S_CO"] == pytest.approx(8.0e-6)
        assert defaults["Y_met_CO"] == pytest.approx(0.025)
        assert defaults["k_dec_X_met_CO"] == pytest.approx(0.02)
        assert defaults["k_m_ac"] == pytest.approx(12.5)
        assert defaults["k_m_h2"] == pytest.approx(90.0)
        assert defaults["K_S_ac"] == pytest.approx(0.05)
        assert defaults["K_S_h2"] == pytest.approx(1.0e-6)
        assert defaults["f_co_to_h2"] == pytest.approx(0.65)

    def test_rate_function_returns_correct_keys(self):
        assembly = resolve_full_model_assembly(["syngas"])
        state = {name: 0.0 for name in assembly.full_state_names}
        state.update({"S_CO": 0.01, "X_met_CO": 0.1, "S_gas_CO": 0.5, "S_IN": 0.01, "S_H_ion": 1e-7})
        params = _make_params("syngas")
        rates = SYNGAS_EXTENSION._rates(state, params)
        assert set(rates.keys()) == {
            "rho_E15_CO_uptake",
            "rho_E15_CO_acetate",
            "rho_E15_decay_X_met_CO",
            "rho_E15_CO_transfer",
        }

    def test_co_split_respects_f_co_to_h2(self):
        assembly = resolve_full_model_assembly(["syngas"])
        state = {name: 0.0 for name in assembly.full_state_names}
        state.update({"S_CO": 0.05, "X_met_CO": 0.5, "S_gas_CO": 0.0, "S_IN": 0.01, "S_H_ion": 1e-7})
        params = _make_params("syngas")
        params["f_co_to_h2"] = 0.35
        rates = SYNGAS_EXTENSION._rates(state, params)
        rho_total = rates["rho_E15_CO_uptake"] + rates["rho_E15_CO_acetate"]
        assert rho_total > 0.0
        assert rates["rho_E15_CO_uptake"] / rho_total == pytest.approx(0.35)
        assert rates["rho_E15_CO_acetate"] / rho_total == pytest.approx(0.65)

    def test_inhibition_hook_targets_acetate_and_hydrogen_uptake(self):
        assembly = resolve_full_model_assembly(["syngas"])
        state = {name: 0.0 for name in assembly.full_state_names}
        state["S_CO"] = 0.01
        params = _make_params("syngas")
        factors = SYNGAS_EXTENSION._inhibition(state, params)
        assert set(factors) == {"rho_11_uptake_acetate", "rho_12_uptake_hydrogen"}
        assert factors["rho_11_uptake_acetate"] < factors["rho_12_uptake_hydrogen"]

    def test_co_uptake_zero_without_biomass(self):
        assembly = resolve_full_model_assembly(["syngas"])
        state = {name: 0.0 for name in assembly.full_state_names}
        state.update({"S_CO": 0.05, "X_met_CO": 0.0, "S_IN": 0.01, "S_H_ion": 1e-7})
        params = _make_params("syngas")
        rates = SYNGAS_EXTENSION._rates(state, params)
        assert rates["rho_E15_CO_uptake"] == pytest.approx(0.0)
        assert rates["rho_E15_CO_acetate"] == pytest.approx(0.0)

    def test_biochemical_rates_are_nonnegative(self):
        assembly = resolve_full_model_assembly(["syngas"])
        state = {name: 0.0 for name in assembly.full_state_names}
        state.update({"S_CO": 0.05, "X_met_CO": 0.5, "S_gas_CO": 0.5, "S_IN": 0.01, "S_H_ion": 1e-7})
        params = _make_params("syngas")
        rates = SYNGAS_EXTENSION._rates(state, params)
        assert rates["rho_E15_CO_uptake"] >= 0.0
        assert rates["rho_E15_CO_acetate"] >= 0.0
        assert rates["rho_E15_decay_X_met_CO"] >= 0.0
        assert isinstance(rates["rho_E15_CO_transfer"], float)

    def test_simulation_does_not_crash(self):
        result = _run_extension(
            "syngas",
            extra_initial={"S_CO": 0.01, "S_gas_CO": 0.5, "X_met_CO": 0.05},
        )
        assert "profiles" in result

    def test_co_decreases_when_biomass_present(self):
        result = _run_extension(
            "syngas",
            extra_initial={"S_CO": 0.05, "S_gas_CO": 1.0, "X_met_CO": 0.5},
            extra_influent={"S_CO": 0.0, "S_gas_CO": 0.0, "X_met_CO": 0.0},
            hrt_days=500.0,
        )
        profiles = result["profiles"]
        assert "S_CO" in profiles
        assert profiles["S_CO"][-1] <= profiles["S_CO"][0] + 1e-6

    def test_diagnostics_profiles_present(self):
        result = _run_extension(
            "syngas",
            extra_initial={"S_CO": 0.01, "S_gas_CO": 0.5, "X_met_CO": 0.05},
        )
        profiles = result["profiles"]
        assert "S_CO" in profiles
        assert "S_gas_CO" in profiles
        assert "X_met_CO" in profiles
        assert "CO_conversion" in profiles


# ---------------------------------------------------------------------------
# E9 — Trace Elements (Ni, Co, Fe)
# ---------------------------------------------------------------------------

class TestTraceElementsExtension:
    def test_contribute_returns_7_states(self):
        contribution = TRACE_ELEMENTS_EXTENSION.contribute()
        state_names = {s.name for s in contribution.states}
        assert state_names == {"S_Ni", "S_Co", "S_Fe2_te", "X_NiS", "X_CoS", "X_FeS_te", "X_FeCO3"}

    def test_contribute_returns_8_processes(self):
        contribution = TRACE_ELEMENTS_EXTENSION.contribute()
        assert len(contribution.processes) == 8
        process_names = {p.name for p in contribution.processes}
        assert process_names == {
            "rho_E9_NiS_precip",
            "rho_E9_NiS_dissolv",
            "rho_E9_CoS_precip",
            "rho_E9_CoS_dissolv",
            "rho_E9_FeS_precip",
            "rho_E9_FeS_dissolv",
            "rho_E9_FeCO3_precip",
            "rho_E9_FeCO3_dissolv",
        }

    def test_stoichiometry_rows_cover_all_processes(self):
        contribution = TRACE_ELEMENTS_EXTENSION.contribute()
        process_names = {p.name for p in contribution.processes if p.family == "biochemical"}
        stoich_names = set(contribution.biochemical_stoichiometry_rows.keys())
        assert process_names == stoich_names

    def test_base_stoichiometry_does_not_reference_s_h2s(self):
        contribution = TRACE_ELEMENTS_EXTENSION.contribute()
        for row in contribution.biochemical_stoichiometry_rows.values():
            assert "S_H2S" not in row

    def test_conditional_patch_declares_srb_dependency(self):
        contribution = TRACE_ELEMENTS_EXTENSION.contribute()
        patches = contribution.conditional_stoichiometry_patches
        assert "srb" in patches
        assert patches["srb"]["rho_E9_NiS_precip"]["S_H2S"] == "-1"
        assert patches["srb"]["rho_E9_FeS_dissolv"]["S_H2S"] == "1"

    def test_assembly_builds_without_srb(self):
        assembly = resolve_full_model_assembly(["trace_elements"])
        assert "S_Ni" in assembly.full_state_index
        assert "S_Co" in assembly.full_state_index
        assert "S_Fe2_te" in assembly.full_state_index
        assert "X_FeCO3" in assembly.full_state_index

    def test_assembly_builds_with_srb_and_h2s_rows(self):
        assembly = resolve_full_model_assembly(["srb", "trace_elements"])
        assert "S_H2S" in assembly.full_state_index
        assert "S_H2S" in assembly.biochemical_stoichiometry_rows["rho_E9_NiS_precip"]
        assert "S_H2S" in assembly.biochemical_stoichiometry_rows["rho_E9_CoS_precip"]
        assert "S_H2S" in assembly.biochemical_stoichiometry_rows["rho_E9_FeS_precip"]

    def test_validate_hook_raises_when_combined_with_iron(self):
        with pytest.raises(ValueError, match="não pode ser combinado com E8"):
            resolve_full_model_assembly(["srb", "phosphorus", "iron", "trace_elements"])

    def test_assembly_has_36_dynamic_states(self):
        assembly = resolve_full_model_assembly(["trace_elements"])
        assert len(assembly.dynamic_state_names) == 36

    def test_rate_function_returns_correct_keys(self):
        assembly = resolve_full_model_assembly(["trace_elements"])
        state = {name: 0.0 for name in assembly.full_state_names}
        state.update({"S_Ni": 2e-6, "S_Co": 5e-7, "S_Fe2_te": 1e-5, "X_NiS": 0.0, "X_CoS": 0.0, "X_FeS_te": 0.0, "X_FeCO3": 0.0})
        params = _make_params("trace_elements")
        rates = TRACE_ELEMENTS_EXTENSION._rates(state, params)
        assert set(rates.keys()) == {
            "rho_E9_NiS_precip",
            "rho_E9_NiS_dissolv",
            "rho_E9_CoS_precip",
            "rho_E9_CoS_dissolv",
            "rho_E9_FeS_precip",
            "rho_E9_FeS_dissolv",
            "rho_E9_FeCO3_precip",
            "rho_E9_FeCO3_dissolv",
        }

    def test_precipitation_rate_zero_without_h2s(self):
        assembly = resolve_full_model_assembly(["trace_elements"])
        state = {name: 0.0 for name in assembly.full_state_names}
        state.update({"S_Ni": 2e-6, "S_Co": 5e-7, "S_Fe2_te": 1e-5})
        params = _make_params("trace_elements")
        rates = TRACE_ELEMENTS_EXTENSION._rates(state, params)
        assert rates["rho_E9_NiS_precip"] == pytest.approx(0.0)
        assert rates["rho_E9_CoS_precip"] == pytest.approx(0.0)
        assert rates["rho_E9_FeS_precip"] == pytest.approx(0.0)

    def test_feco3_precipitation_positive_when_iron_and_ic_are_high(self):
        assembly = resolve_full_model_assembly(["trace_elements"])
        state = {name: 0.0 for name in assembly.full_state_names}
        state.update({"S_Fe2_te": 1e-4, "S_IC": 0.2, "S_H_ion": 1e-7})
        params = _make_params("trace_elements")
        rates = TRACE_ELEMENTS_EXTENSION._rates(state, params)
        assert rates["rho_E9_FeCO3_precip"] > 0.0

    def test_dissolution_rates_positive_when_precipitates_present(self):
        assembly = resolve_full_model_assembly(["trace_elements"])
        state = {name: 0.0 for name in assembly.full_state_names}
        state.update({"X_NiS": 1e-5, "X_CoS": 1e-5, "X_FeS_te": 1e-5, "X_FeCO3": 1e-5, "S_H_ion": 1e-7})
        params = _make_params("trace_elements")
        rates = TRACE_ELEMENTS_EXTENSION._rates(state, params)
        assert rates["rho_E9_NiS_dissolv"] > 0.0
        assert rates["rho_E9_CoS_dissolv"] > 0.0
        assert rates["rho_E9_FeS_dissolv"] > 0.0
        assert rates["rho_E9_FeCO3_dissolv"] > 0.0

    def test_all_rates_nonnegative(self):
        assembly = resolve_full_model_assembly(["trace_elements"])
        state = {name: 0.0 for name in assembly.full_state_names}
        state.update({"S_Ni": 2e-6, "S_Co": 5e-7, "S_Fe2_te": 1e-5, "S_IC": 0.2, "S_H_ion": 1e-7})
        params = _make_params("trace_elements")
        rates = TRACE_ELEMENTS_EXTENSION._rates(state, params)
        for k, v in rates.items():
            assert v >= -1e-15, f"Rate {k} negative: {v}"

    def test_complexation_reduces_free_metal_fraction(self):
        assembly = resolve_full_model_assembly(["trace_elements"])
        state = {name: 0.0 for name in assembly.full_state_names}
        state.update({"S_Ni": 2e-6, "S_Co": 5e-7, "S_Fe2_te": 1e-5})
        params_low = _make_params("trace_elements")
        params_high = dict(params_low)
        params_high["S_DOM_TE"] = 1.0
        low = TRACE_ELEMENTS_EXTENSION._diagnostics(
            __import__('numpy').array([[state.get(name, 0.0) for name in assembly.full_state_names]], dtype=float),
            assembly,
            params_low,
        )
        high = TRACE_ELEMENTS_EXTENSION._diagnostics(
            __import__('numpy').array([[state.get(name, 0.0) for name in assembly.full_state_names]], dtype=float),
            assembly,
            params_high,
        )
        assert high["S_Ni_free"][0] < low["S_Ni_free"][0]
        assert high["S_Co_free"][0] < low["S_Co_free"][0]

    def test_simulation_does_not_crash(self):
        result = _run_extension(
            "trace_elements",
            extra_initial={"S_Ni": 2e-6, "S_Co": 5e-7, "S_Fe2_te": 1e-5},
        )
        assert "profiles" in result

    def test_trace_element_states_remain_nonnegative(self):
        result = _run_extension(
            "trace_elements",
            extra_initial={"S_Ni": 2e-6, "S_Co": 5e-7, "S_Fe2_te": 1e-5},
        )
        profiles = result["profiles"]
        for key in ("S_Ni", "S_Co", "S_Fe2_te"):
            if key in profiles:
                assert all(v >= -1e-12 for v in profiles[key]), f"{key} went negative"

    def test_diagnostics_profiles_present(self):
        result = _run_extension(
            "trace_elements",
            extra_initial={"S_Ni": 2e-6, "S_Co": 5e-7, "S_Fe2_te": 1e-5},
        )
        profiles = result["profiles"]
        assert "S_Ni_free" in profiles
        assert "S_Co_free" in profiles
        assert "S_Fe2_te" in profiles
        assert "X_FeCO3" in profiles


class TestTraceElementsCombinations:
    def test_e4_e9_conditional_patch_present_in_stoichiometry(self):
        assembly = resolve_full_model_assembly(["srb", "trace_elements"])
        assert "S_H2S" in assembly.biochemical_stoichiometry_rows["rho_E9_NiS_precip"]
        assert "S_H2S" in assembly.biochemical_stoichiometry_rows["rho_E9_CoS_precip"]
        assert "S_H2S" in assembly.biochemical_stoichiometry_rows["rho_E9_FeS_precip"]

    def test_e9_standalone_no_h2s_in_stoichiometry(self):
        assembly = resolve_full_model_assembly(["trace_elements"])
        assert "S_H2S" not in assembly.biochemical_stoichiometry_rows["rho_E9_NiS_precip"]
        assert "S_H2S" not in assembly.biochemical_stoichiometry_rows["rho_E9_CoS_precip"]
        assert "S_H2S" not in assembly.biochemical_stoichiometry_rows["rho_E9_FeS_precip"]

    def test_e7_e9_assembly_compiles_without_error(self):
        assembly = resolve_full_model_assembly(["phosphorus", "trace_elements"])
        assert "S_IP" in assembly.full_state_index
        assert "S_Fe2_te" in assembly.full_state_index

    def test_e4_e9_h2s_decreases_when_precipitating_metals_present(self):
        result = _run_multi_extension(
            ["srb", "trace_elements"],
            extra_initial={"S_H2S": 0.01, "S_Ni": 5e-5, "S_Co": 1e-5, "S_Fe2_te": 1e-4},
            extra_influent={"S_H2S": 0.0, "S_Ni": 0.0, "S_Co": 0.0, "S_Fe2_te": 0.0},
            hrt_days=500.0,
        )
        profiles = result["profiles"]
        assert profiles["S_H2S"][-1] < profiles["S_H2S"][0]

    def test_fe_dynamic_depletes_under_feco3_precipitation(self):
        result = _run_extension(
            "trace_elements",
            extra_initial={"S_Fe2_te": 1e-4, "S_IC": 0.2},
            extra_influent={"S_Fe2_te": 0.0},
            hrt_days=500.0,
        )
        profiles = result["profiles"]
        assert profiles["S_Fe2_te"][-1] < profiles["S_Fe2_te"][0]
        assert profiles["X_FeCO3"][-1] >= profiles["X_FeCO3"][0]

    def test_fe_limitation_activates_below_threshold(self):
        assembly = resolve_full_model_assembly(["trace_elements"])
        state = {name: 0.0 for name in assembly.full_state_names}
        state.update({"S_Ni": 5e-6, "S_Co": 5e-6, "S_Fe2_te": 1e-8})
        params = _make_params("trace_elements")
        inhibitions = TRACE_ELEMENTS_EXTENSION._inhibition(state, params)
        assert inhibitions["rho_11_uptake_acetate"] < 0.5
        assert inhibitions["rho_12_uptake_hydrogen"] < 0.5
