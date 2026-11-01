from __future__ import annotations

from typing import Literal

from pydantic import Field

from simulator.core.models import StrictModel
from simulator.digital_twin.demo import run_scenario
from simulator.digital_twin.scenarios import default_scenarios


class DigitalTwinRequest(StrictModel):
    scenario: Literal["steady_noisy", "overload_recovery", "cold_snap_ammonia"] = "overload_recovery"
    influent: Literal["observed", "oracle"] = "observed"
    seed: int = Field(default=0, ge=0, le=2**32 - 1)
    duration_days: float | None = Field(default=None, gt=0, le=3650, allow_inf_nan=False)
    estimator: Literal["open_loop", "ukf"] = "open_loop"


def run_digital_twin(request: DigitalTwinRequest) -> dict[str, object]:
    scenario = default_scenarios()[request.scenario]
    if request.duration_days is not None:
        scenario.duration_days = request.duration_days
    scenario.seed = request.seed
    return run_scenario(request.scenario, scenario, seed=request.seed, twin_influent=request.influent, estimator=request.estimator)
