from __future__ import annotations

import time
from collections.abc import Mapping

import numpy as np
from scipy.integrate import solve_ivp

from simulator.core.models import FeedDefinition, InitialState, KineticParameters, OperatingConditions, ReactorConfig, SimulationConfig
from simulator.full_model.adapter import build_backend_inputs, translate_backend_profiles
from simulator.full_model.model import FullModelInputs, dynamic_state_dict
from simulator.full_model.reactor_modes import FullPlugFlowRhs, FullTwoPhaseRhs, build_reactor_mode
from simulator.full_model.rhs import FullCSTRRhs



def _clipping_diagnostics(solution_y, assembly, segment_params):
    """Report the positive mass correction made when negative outputs are set to zero."""
    states = {state.name: state for state in assembly.state_catalog}
    names = assembly.dynamic_state_names
    n = len(names)
    raw = np.asarray(solution_y, dtype=float).reshape(len(segment_params), n, -1)
    deficits = np.maximum(-raw, 0.0)
    minima = {name: float(raw[:, i, :].min()) for i, name in enumerate(names) if raw[:, i, :].min() < 0}
    cod = np.zeros(raw.shape[2])
    nitrogen = np.zeros(raw.shape[2])
    unknown_n = set()
    for seg, params in enumerate(segment_params):
        for i, name in enumerate(names):
            state = states[name]
            volume = params["V_gas"] if state.phase == "gas" else params["V_liq"]
            mass = deficits[seg, i] * volume
            if state.cod_role == "cod":
                cod += mass
            if name == "S_IN":
                nitrogen += mass * 14.0
            elif state.elemental_proxy == "C_bac":
                nitrogen += mass * params["N_bac"] * 14.0
            elif name in ("S_aa", "X_pr"):
                nitrogen += mass * params["N_aa"] * 14.0
            elif name == "X_xc":
                nitrogen += mass * params["N_xc"] * 14.0
            elif name in ("S_I", "X_I"):
                nitrogen += mass * params["N_I"] * 14.0
            elif name == "X_alg":
                nitrogen += mass * params["i_N_alg"]
            elif state.cod_role == "cod" and state.elemental_proxy not in {"C_su", "C_fa", "C_va", "C_bu", "C_pro", "C_ac", "0", "C_ch4", "C_ch", "C_li"} and np.any(mass):
                unknown_n.add(name)
    return {
        "minimum_negative_by_state": minima,
        "cod_kg_final": float(cod[-1]), "cod_kg_max": float(cod.max()),
        "nitrogen_kg_final": float(nitrogen[-1]), "nitrogen_kg_max": float(nitrogen.max()),
        "nitrogen_unclassified_states": sorted(unknown_n),
        "meaning": "positive mass added by clipping negative sampled concentrations to zero",
    }


def simulate_with_full(
    *,
    operating_conditions: OperatingConditions,
    feed: FeedDefinition,
    initial_state: InitialState,
    parameters: KineticParameters,
    simulation: SimulationConfig,
    active_extensions: list[str] | tuple[str, ...] | None = None,
    extension_parameter_overrides: Mapping[str, float] | None = None,
    initial_state_overrides: Mapping[str, float] | None = None,
    influent_state_overrides: Mapping[str, float] | None = None,
    reactor_config: ReactorConfig | None = None,
) -> dict[str, object]:
    backend_inputs = build_backend_inputs(
        operating_conditions=operating_conditions,
        feed=feed,
        initial_state=initial_state,
        parameters=parameters,
        active_extensions=active_extensions,
        extension_parameter_overrides=extension_parameter_overrides,
        initial_state_overrides=initial_state_overrides,
        influent_state_overrides=influent_state_overrides,
    )
    return simulate_with_full_inputs(
        inputs=backend_inputs,
        simulation=simulation,
        reactor_config=reactor_config,
    )



def simulate_with_full_inputs(
    *,
    inputs: FullModelInputs,
    simulation: SimulationConfig,
    reactor_config: ReactorConfig | None = None,
    initial_dynamic_state: np.ndarray | None = None,
    t_start_days: float = 0.0,
) -> dict[str, object]:
    reactor_type = reactor_config.reactor_type if reactor_config is not None else "cstr"
    system = build_reactor_mode(reactor_type, inputs, reactor_config=reactor_config)

    if initial_dynamic_state is not None:
        if reactor_type != "cstr" or not isinstance(system, FullCSTRRhs):
            raise ValueError("initial_dynamic_state requires a single-segment CSTR")
        initial_dynamic_state = np.asarray(initial_dynamic_state, dtype=float)
        if initial_dynamic_state.shape != inputs.dynamic_initial.shape or not np.all(np.isfinite(initial_dynamic_state)):
            raise ValueError("initial_dynamic_state must be a finite vector matching the dynamic state")

    # Build initial condition vector.
    # For multi-segment reactors (plug_flow, two_phase, tpad), replicate initial state.
    if isinstance(system, FullPlugFlowRhs):
        n_seg = system.n_segments
        y0 = np.tile(inputs.dynamic_initial, n_seg)
        segment_count = n_seg
    elif isinstance(system, FullTwoPhaseRhs):
        y0 = np.tile(inputs.dynamic_initial, 2)
        segment_count = 2
    else:
        y0 = inputs.dynamic_initial.copy() if initial_dynamic_state is None else initial_dynamic_state.copy()
        segment_count = 1

    # Batch inoculum dilution: the reactor starts with f_inoc fraction of inoculum and
    # (1 - f_inoc) fraction of fresh feed.
    # y0_actual = f_inoc * inoculum_state + (1 - f_inoc) * feed_state
    # This implements the standard batch setup procedure (BSM2 convention):
    # the inoculum provides the active biomass; the substrate fills the remaining volume.
    if (
        reactor_config is not None
        and reactor_config.reactor_type == "batch"
        and reactor_config.batch is not None
        and segment_count == 1
    ):
        f_inoc = float(reactor_config.batch.inoculum_fraction)
        y0 = f_inoc * y0 + (1.0 - f_inoc) * inputs.dynamic_influent

    time_grid = np.linspace(t_start_days, t_start_days + simulation.duration_days, simulation.evaluation_points)
    # Multi-segment reactors (plug_flow) create very large ODE systems that are
    # extremely stiff.  Radau (implicit Runge-Kutta) handles the Jacobian better
    # than BDF for these systems and avoids numerical overflow in the finite-diff
    # Jacobian estimation.  We also relax tolerances for large systems to keep
    # wall-clock time practical while maintaining engineering accuracy (< 1% error).
    solver_method = simulation.solver
    rtol = simulation.rtol
    atol = simulation.atol
    if segment_count > 1:
        if solver_method == "BDF":
            solver_method = "Radau"
        rtol = max(rtol, 1e-4)
        atol = max(atol, 1e-6)
    max_step = simulation.duration_days / 20.0

    # Contagens de dimensão para metadados técnicos
    n_dynamic = len(inputs.assembly.dynamic_state_names)
    n_algebraic = len(inputs.assembly.algebraic_state_names)
    n_pseudo = len(inputs.assembly.pseudo_state_names)
    n_full = len(inputs.assembly.full_state_names)
    # Dimensão efetiva do sistema de EDOs = estados dinâmicos × número de segmentos
    effective_ode_dimension = n_dynamic * segment_count

    t_start = time.perf_counter()
    solution = solve_ivp(
        system,
        t_span=(t_start_days, t_start_days + simulation.duration_days),
        y0=y0,
        method=solver_method,
        t_eval=time_grid,
        rtol=rtol,
        atol=atol,
        max_step=max_step,
    )
    runtime_seconds = time.perf_counter() - t_start

    if not solution.success:
        raise RuntimeError(f"Full ADM1 simulation failed ({reactor_type}): {solution.message}")

    # Para reatores multi-segmento, extrai o último segmento (efluente) para pós-processamento.
    m = len(inputs.assembly.dynamic_state_names)
    if segment_count > 1:
        # solution.y shape: (n_seg*m, n_time) → pega as linhas do último segmento para perfis
        last_seg_rows = solution.y[(segment_count - 1) * m : segment_count * m, :]
        dynamic_matrix = np.clip(last_seg_rows.T.astype(float), a_min=0.0, a_max=None)
    else:
        dynamic_matrix = np.clip(solution.y.T.astype(float), a_min=0.0, a_max=None)

    # Avalia o estado completo (equilíbrio ácido-base + transferência gasosa) em cada ponto de tempo.
    # Para multi-segmento, reutiliza a lógica evaluate() do CSTR no segmento efluente.
    _eval_rhs: FullCSTRRhs
    if isinstance(system, FullCSTRRhs):
        _eval_rhs = system
    elif isinstance(system, FullPlugFlowRhs):
        _eval_rhs = system._rhs
    elif isinstance(system, FullTwoPhaseRhs):
        _eval_rhs = system._rhs2
    else:
        _eval_rhs = FullCSTRRhs(inputs=inputs)

    evaluations = [
        _eval_rhs.evaluate(
            dynamic_values=dynamic_state_dict(row, assembly=inputs.assembly),
            use_cache=False,
        )
        for row in dynamic_matrix
    ]
    full_state_matrix = np.asarray([ev.full_state.vector for ev in evaluations], dtype=float)
    profiles = translate_backend_profiles(
        full_state_matrix=full_state_matrix,
        parameter_values=_eval_rhs.params,
        assembly=inputs.assembly,
    )
    if segment_count > 1:
        segment_rhs = (
            [system._rhs] * segment_count
            if isinstance(system, FullPlugFlowRhs)
            else [system._rhs1, system._rhs2]
        )
        gas_flow_names = (
            "biogas_m3_day", "methane_m3_day", "co2_m3_day", "h2_m3_day",
            "q_gas_headspace_m3_day", "co_m3_day", "h2s_m3_day",
        )
        gas_totals = {name: np.asarray(profiles[name], dtype=float) for name in gas_flow_names if name in profiles}
        for segment, rhs in enumerate(segment_rhs[:-1]):
            rows = solution.y[segment * m : (segment + 1) * m, :].T
            segment_evaluations = [
                rhs.evaluate(dynamic_values=dynamic_state_dict(row, assembly=inputs.assembly), use_cache=False)
                for row in rows
            ]
            segment_profiles = translate_backend_profiles(
                full_state_matrix=np.asarray([ev.full_state.vector for ev in segment_evaluations]),
                parameter_values=rhs.params,
                assembly=inputs.assembly,
            )
            for name in gas_totals:
                gas_totals[name] += np.asarray(segment_profiles[name], dtype=float)
        profiles.update({name: values.tolist() for name, values in gas_totals.items()})
        profiles["ch4_fraction"] = np.clip(
            gas_totals["methane_m3_day"] / np.maximum(gas_totals["biogas_m3_day"], 1e-12), 0.0, 1.0,
        ).tolist()
    if isinstance(system, FullPlugFlowRhs):
        segment_params = [system._seg_params] * segment_count
    elif isinstance(system, FullTwoPhaseRhs):
        segment_params = [system._params1, system._params2]
    else:
        segment_params = [system.params]
    clipping = _clipping_diagnostics(solution.y, inputs.assembly, segment_params)
    metadata = {
        "full_model_clipping": clipping,
        "segment_count": segment_count,
        "reactor_type": reactor_type,
        "solver_status": solution.message,
        "final_internal_state": [float(v) for v in full_state_matrix[-1].tolist()],
        "full_state_columns": list(inputs.assembly.full_state_names),
        "full_dynamic_state_columns": list(inputs.assembly.dynamic_state_names),
        "full_model_liquid_volume_m3": float(inputs.parameter_values["V_liq"]),
        "full_model_gas_volume_m3": float(inputs.parameter_values["V_gas"]),
        "full_model_ph_converged": all(ev.acid_base.converged for ev in evaluations),
        "full_model_ph_iterations_max": max(ev.acid_base.iterations for ev in evaluations),
        "full_model_runtime": "native",
        "full_model_active_extensions": list(inputs.assembly.active_extensions),
        # ── Metadados técnicos do solver (Plano 2) ──────────────────────────
        # Contagens de estados para observabilidade do sistema
        "full_model_state_count": n_full,
        "full_model_dynamic_state_count": n_dynamic,
        "full_model_algebraic_state_count": n_algebraic,
        "full_model_pseudo_state_count": n_pseudo,
        "full_model_segment_count": segment_count,
        # Dimensão efetiva = n_dynamic × n_segmentos (tamanho do vetor de estado integrado)
        "full_model_effective_ode_dimension": effective_ode_dimension,
        # Diagnóstico do solver scipy
        "full_model_runtime_seconds": round(runtime_seconds, 4),
        "full_model_solver_method": str(solver_method),
        "full_model_solver_rtol": float(rtol),
        "full_model_solver_atol": float(atol),
        "full_model_solver_method_requested": str(simulation.solver),
        "full_model_solver_rtol_requested": float(simulation.rtol),
        "full_model_solver_atol_requested": float(simulation.atol),
        "full_model_time_grid_points": int(simulation.evaluation_points),
        # Estatísticas de chamadas do solver (disponíveis na maioria dos métodos scipy)
        "full_model_solver_nfev": int(getattr(solution, "nfev", 0) or 0),
        "full_model_solver_njev": int(getattr(solution, "njev", 0) or 0),
        "full_model_solver_nlu": int(getattr(solution, "nlu", 0) or 0),
    }
    if reactor_type == "tpad" and reactor_config is not None and reactor_config.tpad is not None:
        effective_hrt = reactor_config.tpad.thermo_hrt_days + reactor_config.tpad.meso_hrt_days
        q_ad = inputs.parameter_values["q_ad"]
        requested_hrt = inputs.parameter_values["V_liq"] / q_ad if q_ad > 0.0 else effective_hrt
        metadata["effective_hrt_days"] = float(effective_hrt)
        metadata["full_model_liquid_volume_m3"] = float(system._params1["V_liq"] + system._params2["V_liq"])
        metadata["full_model_gas_volume_m3"] = float(system._params1["V_gas"] + system._params2["V_gas"])
        if not np.isclose(effective_hrt, requested_hrt, rtol=1e-9, atol=1e-9):
            metadata["hrt_warning"] = "A soma dos HRTs das fases difere do HRT total; foram usados os HRTs das fases."
    return {
        "time_days": [float(v) for v in time_grid.tolist()],
        "profiles": profiles,
        "metadata": metadata,
    }
