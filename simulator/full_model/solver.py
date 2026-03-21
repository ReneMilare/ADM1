from __future__ import annotations

from collections.abc import Mapping

import numpy as np
from scipy.integrate import solve_ivp

from simulator.core.models import FeedDefinition, InitialState, KineticParameters, OperatingConditions, SimulationConfig
from simulator.full_model.adapter import build_backend_inputs, translate_backend_profiles
from simulator.full_model.model import FullModelInputs
from simulator.full_model.rhs import FullCSTRRhs



def simulate_with_full(
    *,
    operating_conditions: OperatingConditions,
    feed: FeedDefinition,
    initial_state: InitialState,
    parameters: KineticParameters,
    simulation: SimulationConfig,
    active_extensions: list[str] | tuple[str, ...] | None = None,
    extension_parameter_overrides: Mapping[str, float] | None = None,
) -> dict[str, object]:
    backend_inputs = build_backend_inputs(
        operating_conditions=operating_conditions,
        feed=feed,
        initial_state=initial_state,
        parameters=parameters,
        active_extensions=active_extensions,
        extension_parameter_overrides=extension_parameter_overrides,
    )
    return simulate_with_full_inputs(inputs=backend_inputs, simulation=simulation)



def simulate_with_full_inputs(*, inputs: FullModelInputs, simulation: SimulationConfig) -> dict[str, object]:
    system = FullCSTRRhs(inputs=inputs)
    time_grid = np.linspace(0.0, simulation.duration_days, simulation.evaluation_points)
    solution = solve_ivp(
        system,
        t_span=(0.0, simulation.duration_days),
        y0=inputs.dynamic_initial,
        method=simulation.solver,
        t_eval=time_grid,
        rtol=simulation.rtol,
        atol=simulation.atol,
    )
    if not solution.success:
        raise RuntimeError(f"Full ADM1 simulation failed: {solution.message}")

    dynamic_matrix = np.clip(solution.y.T.astype(float), a_min=0.0, a_max=None)
    evaluations = [
        system.evaluate(
            dynamic_values={name: float(row[index]) for index, name in enumerate(inputs.assembly.dynamic_state_names)},
            use_cache=False,
        )
        for row in dynamic_matrix
    ]
    full_state_matrix = np.asarray([evaluation.full_state.vector for evaluation in evaluations], dtype=float)
    profiles = translate_backend_profiles(
        full_state_matrix=full_state_matrix,
        parameter_values=inputs.parameter_values,
        assembly=inputs.assembly,
    )
    metadata = {
        "segment_count": 1,
        "solver_status": solution.message,
        "final_internal_state": [float(value) for value in full_state_matrix[-1].tolist()],
        "full_state_columns": list(inputs.assembly.full_state_names),
        "full_dynamic_state_columns": list(inputs.assembly.dynamic_state_names),
        "full_model_liquid_volume_m3": float(inputs.parameter_values["V_liq"]),
        "full_model_gas_volume_m3": float(inputs.parameter_values["V_gas"]),
        "full_model_ph_converged": all(evaluation.acid_base.converged for evaluation in evaluations),
        "full_model_ph_iterations_max": max(evaluation.acid_base.iterations for evaluation in evaluations),
        "full_model_runtime": "native",
        "full_model_active_extensions": list(inputs.assembly.active_extensions),
    }
    return {
        "time_days": [float(value) for value in time_grid.tolist()],
        "profiles": profiles,
        "metadata": metadata,
    }
