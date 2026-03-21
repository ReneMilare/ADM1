from __future__ import annotations

import shutil
from pathlib import Path

from simulator.full_parity import (
    ARTIFACT_JSON_NAME,
    ARTIFACT_MD_NAME,
    COMPARED_INTERNAL_STATE_NAMES,
    build_full_parity_scenarios,
    run_full_parity_benchmark,
)

WORKSPACE_TMP = Path("simulator") / "tests" / ".tmp" / "full_parity_tests"
EXPECTED_SCENARIO_NAMES = [
    "baseline_bsm2_reference",
    "high_nitrogen_sin_x2",
    "high_organic_loading_cod_x1_2",
    "short_hrt_15d",
    "temperature_25c",
    "lipid_rich_influent",
]


def _reset_workspace() -> None:
    shutil.rmtree(WORKSPACE_TMP, ignore_errors=True)
    WORKSPACE_TMP.mkdir(parents=True, exist_ok=True)


def test_full_parity_scenario_names_are_versioned() -> None:
    scenario_names = [scenario.name for scenario in build_full_parity_scenarios()]
    assert scenario_names == EXPECTED_SCENARIO_NAMES
    assert COMPARED_INTERNAL_STATE_NAMES == (
        "S_su",
        "S_aa",
        "S_fa",
        "S_va",
        "S_bu",
        "S_pro",
        "S_ac",
        "S_h2",
        "S_ch4",
        "S_IC",
        "S_IN",
        "S_I",
        "X_xc",
        "X_ch",
        "X_pr",
        "X_li",
        "X_su",
        "X_aa",
        "X_fa",
        "X_c4",
        "X_pro",
        "X_ac",
        "X_h2",
        "X_I",
        "S_gas_h2",
        "S_gas_ch4",
        "S_gas_co2",
    )



def test_full_parity_baseline_passes_gates() -> None:
    _reset_workspace()
    report, output_dir = run_full_parity_benchmark(
        output_root=WORKSPACE_TMP,
        scenario_names=["baseline_bsm2_reference"],
    )
    assert output_dir.resolve() == WORKSPACE_TMP.resolve()
    assert report["aggregate"]["all_gates_pass"] is True
    assert report["conclusion"]["baseline_passed"] is True
    assert report["aggregate"]["summary_metrics"]["methane_final_m3_day"]["max_rel_delta_pct"] < 0.1
    assert report["aggregate"]["series_metrics"]["methane_m3_day"]["max_nrmse_pct"] < 1.0



def test_full_parity_subset_persists_artifacts() -> None:
    _reset_workspace()
    report, output_dir = run_full_parity_benchmark(
        output_root=WORKSPACE_TMP,
        scenario_names=["baseline_bsm2_reference", "high_nitrogen_sin_x2"],
    )
    assert output_dir.resolve() == WORKSPACE_TMP.resolve()
    assert report["scenario_count"] == 2
    assert report["aggregate"]["all_gates_pass"] is True
    assert report["conclusion"]["all_gates_pass"] is True
    assert report["scenario_names"] == ["baseline_bsm2_reference", "high_nitrogen_sin_x2"]
    assert (output_dir / ARTIFACT_JSON_NAME).exists()
    assert (output_dir / ARTIFACT_MD_NAME).exists()
