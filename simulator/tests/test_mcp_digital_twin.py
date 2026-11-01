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
    def fake_run(name, scenario, *, seed, twin_influent, estimator):
        captured.update(name=name, scenario=scenario, seed=seed, influent=twin_influent, estimator=estimator)
        return {}
    monkeypatch.setattr(api, "run_scenario", fake_run)
    api.run_digital_twin(DigitalTwinRequest(scenario="overload_recovery", seed=17, duration_days=1.5, influent="oracle"))
    assert captured["scenario"].duration_days == 1.5
    assert captured["scenario"].seed == captured["seed"] == 17
    assert captured["influent"] == "oracle"
    assert captured["name"] == "overload_recovery"
    assert captured["estimator"] == "open_loop"


def test_tool_is_registered_before_server_starts():
    import ast
    from pathlib import Path
    import simulator.mcp_server as server

    module = ast.parse(Path(server.__file__).read_text(encoding="utf-8"))
    tool = next(node for node in module.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "run_digital_twin_scenario")
    startup = next(node for node in module.body if isinstance(node, ast.If) and "__main__" in ast.unparse(node.test))
    assert tool.lineno < startup.lineno
    assert "run_digital_twin_scenario" in {item.name for item in asyncio.run(server.mcp.list_tools())}


def test_mcp_ukf_parameter_history_is_bounded(monkeypatch):
    import pandas as pd
    import simulator.mcp_server as server

    frame = pd.DataFrame({"time_days": range(501), "k_m_ac": [5.5] * 501, "k_m_ac_lower_2sigma": [4.0] * 501, "k_m_ac_upper_2sigma": [7.0] * 501, "nitrogen_factor": [1.0] * 501, "nitrogen_factor_lower_2sigma": [0.8] * 501, "nitrogen_factor_upper_2sigma": [1.2] * 501})
    monkeypatch.setattr(server, "run_digital_twin", lambda request: {"truth": frame, "simulated": frame, "measured": frame, "parameter_history": frame, "report": {}})
    result = json.loads(asyncio.run(server.run_digital_twin_scenario(DigitalTwinRequest(estimator="ukf"))))
    rows = result["series"]["parameters"]
    assert len(rows) == 200
    assert rows[0]["time_days"] == 0 and rows[-1]["time_days"] == 500
    assert rows[0]["nitrogen_factor_lower_2sigma"] == 0.8
