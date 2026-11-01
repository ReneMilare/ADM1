from __future__ import annotations

import asyncio
import json

import pytest
from pydantic import ValidationError

from simulator.mcp_server import DigitalTwinRequest, run_digital_twin_scenario


def test_mcp_scenario_json_and_missing_measurements():
    result = json.loads(asyncio.run(run_digital_twin_scenario(DigitalTwinRequest(scenario="steady_noisy", influent="oracle", seed=2, duration_days=2))))
    assert result["influent"] == "oracle"
    assert len(result["metrics"]) == 6
    assert set(result["series"]) == {"plant", "twin", "measurements"}
    assert result["series"]["measurements"][1]["vfa_kg_cod_m3"] is None
    assert all(len(rows) <= 200 for rows in result["series"].values())
    json.dumps(result, allow_nan=False)


def test_mcp_strict_input():
    with pytest.raises(ValidationError):
        DigitalTwinRequest(extra_field=True)
    request = DigitalTwinRequest()
    with pytest.raises(ValidationError):
        request.influent = "invalid"
    with pytest.raises(ValidationError):
        DigitalTwinRequest(duration_days=float("nan"))


def test_request_passes_seed_and_duration_to_scenario(monkeypatch):
    import simulator.digital_twin_api as api

    captured = {}
    def fake_run(name, scenario, *, seed, twin_influent):
        captured.update(name=name, scenario=scenario, seed=seed, influent=twin_influent)
        return {}
    monkeypatch.setattr(api, "run_scenario", fake_run)
    api.run_digital_twin(DigitalTwinRequest(scenario="overload_recovery", seed=17, duration_days=1.5, influent="oracle"))
    assert captured["scenario"].duration_days == 1.5
    assert captured["scenario"].seed == captured["seed"] == 17
    assert captured["influent"] == "oracle"
    assert captured["name"] == "overload_recovery"


def test_tool_is_registered_before_server_starts():
    import ast
    from pathlib import Path
    import simulator.mcp_server as server

    module = ast.parse(Path(server.__file__).read_text(encoding="utf-8"))
    tool = next(node for node in module.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "run_digital_twin_scenario")
    startup = next(node for node in module.body if isinstance(node, ast.If) and "__main__" in ast.unparse(node.test))
    assert tool.lineno < startup.lineno
    assert "run_digital_twin_scenario" in {item.name for item in asyncio.run(server.mcp.list_tools())}
