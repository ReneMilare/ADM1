from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

from simulator.literature_validation import _build_conclusion


@pytest.mark.parametrize(
    ("module_name", "runner_name"),
    [
        ("simulator.benchmark", "run_benchmark"),
        ("simulator.validation", "run_phase3_validation"),
        ("simulator.literature_validation", "run_literature_validation"),
        ("simulator.full_parity", "run_full_parity_benchmark"),
    ],
)
def test_validation_clis_do_not_expose_absolute_output_paths(
    module_name: str, runner_name: str, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str], tmp_path: Path,
) -> None:
    module = importlib.import_module(module_name)
    report = {
        "scenario_count": 1,
        "aggregate": {
            "runtime_seconds": {"pyadm1": {"mean": 1.0}},
            "summary_metrics": {
                "methane_final_m3_day": {"mean_rel_delta_pct_vs_pyadm1": 0.0},
                "ph_final": {"mean_rel_delta_pct_vs_pyadm1": 0.0},
            },
            "recommendation": {"rationale": "ok"},
            "all_gates_pass": True,
        },
        "openmodelica": {"status": "toolchain_not_available"},
        "pyadm1": {"validated": True},
        "reduced": {"validated": False},
        "conclusion": {
            "prefer_pyadm1_for_cstr_fidelity": True,
            "promote_pyadm1_as_global_default": True,
            "rationale": "ok",
            "pyadm1_max_rel_delta_pct": 0.0,
            "reduced_max_rel_delta_pct": 100.0,
            "max_summary_rel_delta_pct": 0.0,
            "max_series_nrmse_pct": 0.0,
        },
    }
    monkeypatch.setattr(module, runner_name, lambda **kwargs: (report, tmp_path))
    monkeypatch.setattr(sys, "argv", [module_name])
    module.main()
    output = json.loads(capsys.readouterr().out)
    assert output["output_dir"] == tmp_path.name


def test_failed_literature_comparison_does_not_claim_a_match() -> None:
    failed = {"validated": False, "comparison": {"pH": {"rel_delta_pct": 2.0}}}
    conclusion = _build_conclusion(failed, failed)
    assert not conclusion["pyadm1_matches_bsm2_reference"]
    assert "fora da tolerancia" in conclusion["summary"]
