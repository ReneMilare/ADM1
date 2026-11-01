from __future__ import annotations

import pytest

from simulator.core.defaults import make_default_simulation_config
from simulator.service import ADM1SimulationService
from simulator import mcp_server


@pytest.mark.parametrize(("requested", "reactor"), [("reduced", "cstr"), ("auto", "plug_flow"), ("pyadm1", "uasb")])
def test_reduced_results_are_exploratory(requested: str, reactor: str) -> None:
    config = make_default_simulation_config().model_copy(update={"backend": requested, "duration_days": 1.0, "evaluation_points": 11, "persist": False})
    result = ADM1SimulationService().simulate(reactor, simulation=config, metadata={"model_fidelity": "reference"})
    assert result.metadata["backend_used"] == "reduced"
    assert result.metadata["model_fidelity"] == "exploratory"
    assert len(result.metadata["known_limitations"]) >= 3
    assert all(isinstance(item, str) for item in result.metadata["known_limitations"])
    if requested != "reduced":
        assert result.metadata["backend_requested"] == requested
        assert result.metadata["backend_fallback_reason"]


@pytest.mark.parametrize("backend", ["pyadm1", "full"])
def test_reference_backend_metadata(backend: str) -> None:
    config = make_default_simulation_config().model_copy(update={"backend": backend, "duration_days": 1.0, "evaluation_points": 11, "persist": False})
    result = ADM1SimulationService().simulate("cstr", simulation=config, metadata={"known_limitations": ["incorrect"]})
    assert result.metadata["model_fidelity"] == "reference"
    assert "known_limitations" not in result.metadata


@pytest.mark.parametrize("name", ["simulate_reactor", "simulate_codigestion", "simulate_two_phase", "simulate_tpad", "simulate_batch", "compare_backends", "optimize_parameter", "calibrate_model", "design_reactor"])
def test_mcp_backend_tool_description_mentions_exploratory(name: str) -> None:
    assert "exploratory" in (getattr(mcp_server, name).__doc__ or "").lower()
