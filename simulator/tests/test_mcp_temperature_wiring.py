from __future__ import annotations

import asyncio
import pytest
from pydantic import ValidationError

import simulator.mcp_server as server


@pytest.mark.parametrize("model,kwargs", [(server.SimulateReactorInput, {"reactor_type": "cstr"}), (server.CompareBackendsInput, {})])
def test_temperature_input_validation(model, kwargs):
    assert model(temperature_kinetics="siegrist2002", **kwargs).temperature_kinetics == "siegrist2002"
    with pytest.raises(ValidationError):
        model(temperature_kinetics="invalid", **kwargs)


@pytest.mark.parametrize("name,kwargs", [
    ("simulate_reactor", {"reactor_type": "cstr"}),
    ("simulate_codigestion", {"reactor_type": "cstr", "substrates_json": '[{"name":"Lodo de Esgoto","fraction":0.5},{"name":"Lodo de Esgoto","fraction":0.5}]'}),
    ("simulate_two_phase", {}), ("simulate_tpad", {}), ("simulate_batch", {}),
    ("compare_backends", {}),
])
def test_temperature_reaches_kinetics(monkeypatch, name, kwargs):
    captured = []
    class Service:
        def simulate(self, **kw):
            captured.append(kw["parameters"])
            return object()
        def compare_backends(self, *args, **kw):
            captured.append(kw["parameters"])
            return {}
    monkeypatch.setattr(server, "_get_service", lambda: Service())
    monkeypatch.setattr(server, "_result_payload", lambda result: {})
    asyncio.run(getattr(server, name)(temperature_kinetics="siegrist2002", **kwargs))
    assert captured[0].temperature_kinetics == "siegrist2002"
