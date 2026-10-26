from __future__ import annotations

import asyncio
import json

import pytest
from pydantic import ValidationError

from simulator.core.models import CalibrationPoint, SimulationConfig
from simulator.mcp_server import (
    CalibrateModelInput,
    CompareBackendsInput,
    CompareScenariosInput,
    DesignReactorInput,
    OptimizeParameterInput,
    SimulateReactorInput,
    _build_blend_from_json,
    calibrate_model,
)


def test_duration_limits_apply_to_service_and_mcp_models() -> None:
    assert SimulationConfig(duration_days=3650).duration_days == 3650
    for build in (
        lambda: SimulationConfig(duration_days=3651),
        lambda: SimulateReactorInput(reactor_type="cstr", duration_days=3651),
        lambda: CompareBackendsInput(duration_days=3651),
        lambda: OptimizeParameterInput(parameter_path="kinetics.k_hyd", minimum=0, maximum=1, duration_days=3651),
        lambda: CalibrateModelInput(experimental_points_json="[]", duration_days=3651),
        lambda: DesignReactorInput(substrate="generic_sludge", duration_days=3651),
    ):
        with pytest.raises(ValidationError):
            build()


def test_mcp_collection_limits_and_candidate_deduplication() -> None:
    params = DesignReactorInput(substrate="generic_sludge", candidate_reactors=["cstr", "uasb", "cstr"])
    assert params.candidate_reactors == ["cstr", "uasb"]
    for build in (
        lambda: DesignReactorInput(substrate="generic_sludge", candidate_reactors=["cstr"] * 11),
        lambda: CompareScenariosInput(simulation_ids=["id"] * 101),
        lambda: CompareBackendsInput(backends=["full"] * 11),
        lambda: SimulateReactorInput(reactor_type="cstr", full_extensions=["srb"] * 21),
        lambda: SimulationConfig(full_initial_state_overrides={str(i): 0.0 for i in range(201)}),
    ):
        with pytest.raises(ValidationError):
            build()
    with pytest.raises(ValueError, match="at most 10"):
        _build_blend_from_json(json.dumps([{}] * 11))


def test_calibration_limits_before_processing() -> None:
    with pytest.raises(ValidationError):
        CalibrateModelInput(experimental_points_json=" " * 1_000_001 + "[]")
    with pytest.raises(ValidationError):
        CalibrationPoint(time_days=3651, observed_methane_m3_day=1)
    with pytest.raises(ValueError, match="at most 5000"):
        asyncio.run(calibrate_model(experimental_points_json=json.dumps([{}] * 5001)))
    with pytest.raises(ValueError, match="array"):
        asyncio.run(calibrate_model(experimental_points_json="{}"))
