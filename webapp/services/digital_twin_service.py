from __future__ import annotations

from simulator.digital_twin_api import DigitalTwinRequest, run_digital_twin


def run_scenario(
    name: str, influent: str = "observed", seed: int = 0,
    duration_days: float | None = None, estimator: str = "open_loop",
) -> dict[str, object]:
    request = DigitalTwinRequest(scenario=name, influent=influent, seed=seed, duration_days=duration_days, estimator=estimator)
    result = run_digital_twin(request)
    frames = {"plant": result["truth"], "twin": result["simulated"], "measurements": result["measured"]}
    if "parameter_history" in result:
        frames["parameters"] = result["parameter_history"]
    return {
        "scenario": request.scenario,
        "influent": request.influent,
        "estimator": request.estimator,
        "series": frames,
        "metrics": result["report"],
        "csv": {name: frame.to_csv(index=False).encode("utf-8") for name, frame in frames.items()},
    }
