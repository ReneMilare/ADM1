"""reactor_modes.py — Full ADM1 ODE right-hand-side variants for non-CSTR configurations.

Implements:
  FullBatchRhs    — batch (no in/out flow)
  FullUASBRhs     — UASB with biomass retention (SRT > HRT, solid states washed out slower)
  FullPlugFlowRhs — tanks-in-series approximation (N segments, distributed gas space)
  FullTwoPhaseRhs — two CSTRs in series (hydrolysis/acidogenesis + methanogenesis)
  FullTPADRhs     — two-phase with Arrhenius temperature correction for phase 1

All modes share the core evaluate() logic (acid-base solver, kinetics, gas transfer) from
FullCSTRRhs. The differences are only in the mass-balance ODE structure.

Temperature correction for TPAD (Batstone 2002, Appendix B):
    k(T) = k(Tref) * exp(Ea_R * (1/Tref - 1/T))
where Ea_R ≈ 5030 K for biochemical processes (corresponds to ~41.8 kJ/mol),
and Ea_R ≈ 6858 K for hydrolysis (corresponds to ~57 kJ/mol).
Reference temperature Tref = 308.15 K (35°C).
"""
from __future__ import annotations

import math
from typing import Mapping

import numpy as np

from simulator.full_model.model import FullModelInputs, dynamic_state_dict
from simulator.full_model.rhs import FullCSTRRhs, FullStateEvaluation, apply_extension_gas_derivatives

# Arrhenius activation energy / R for temperature correction (Batstone 2002 App B, Table B.2)
_EA_R_BIOCHEMICAL = 5030.0  # K — for k_m_*, k_dec_* (≈ 41.8 kJ/mol)
_EA_R_HYDROLYSIS = 6858.0   # K — for k_dis, k_hyd_* (≈ 57 kJ/mol)
_T_REF_K = 308.15           # K = 35°C (ADM1 calibration temperature)

# Parameter names that scale with hydrolysis Ea (pre-sorted for determinism)
_HYDROLYSIS_PARAMS = frozenset(("k_dis", "k_hyd_ch", "k_hyd_pr", "k_hyd_li"))


def _arrhenius_factor(t_k: float, ea_r: float) -> float:
    """Arrhenius scale factor relative to 35°C (308.15 K)."""
    return math.exp(ea_r * (1.0 / _T_REF_K - 1.0 / max(t_k, 273.15)))


def _scale_params_for_temperature(params: dict[str, float], t_celsius: float) -> dict[str, float]:
    """Return a copy of params with kinetic and equilibrium constants updated for t_celsius.

    Arrhenius scaling (Batstone 2002, App. B, Table B.2):
    - Hydrolysis (k_dis, k_hyd_*): E_a/R = 6858 K  (≈ 57 kJ/mol)
    - Biochemical uptake/decay (k_m_*, k_dec_*, k_lac*, k_et*, k_ads*, k_des*):
      E_a/R = 5030 K  (≈ 41.8 kJ/mol)

    Equilibrium constants recomputed at the new temperature using the same van't Hoff
    formulas as resolve_full_parameter_values() (Batstone 2002, App. A):
    - K_w    : ΔH/R = 55900/100/R   (water dissociation)
    - K_a_co2: ΔH/R = 7646/100/R    (CO2 ↔ HCO3⁻)
    - K_a_IN : ΔH/R = 51965/100/R   (NH3 ↔ NH4⁺)
    - K_H_co2: ΔH/R = −19410/100/R  (Henry, CO2)
    - K_H_ch4: ΔH/R = −14240/100/R  (Henry, CH4)
    - K_H_h2 : ΔH/R = −4180/100/R   (Henry, H2)
    - p_gas_h2o: ΔH = 5290 K        (Antoine, water vapor)

    pH inhibition midpoints are temperature-independent and retain their resolved values.
    """
    t_k = t_celsius + 273.15
    f_hyd = _arrhenius_factor(t_k, _EA_R_HYDROLYSIS)
    f_bio = _arrhenius_factor(t_k, _EA_R_BIOCHEMICAL)
    scaled = dict(params)
    scaled["T_op"] = t_k
    scaled["T_ad"] = t_k

    # Kinetic rate constants — Arrhenius scaling
    for name, value in params.items():
        if name in _HYDROLYSIS_PARAMS:
            scaled[name] = value * f_hyd
        elif (
            name.startswith("k_m_")
            or name.startswith("k_dec_")
            or name.startswith("k_lac")
            or name.startswith("k_et_")
            or name.startswith("k_ads")
            or name.startswith("k_des")
        ):
            scaled[name] = value * f_bio

    # Equilibrium constants — recomputed via van't Hoff at the new temperature
    r = float(params.get("R", 0.083145))
    t_base = float(params.get("T_base", 298.15))
    dt_inv = 1.0 / t_base - 1.0 / t_k
    scaled["K_w"] = 10.0 ** -14.0 * math.exp((55900.0 / (100.0 * r)) * dt_inv)
    scaled["K_a_co2"] = 10.0 ** -6.35 * math.exp((7646.0 / (100.0 * r)) * dt_inv)
    scaled["K_a_IN"] = 10.0 ** -9.25 * math.exp((51965.0 / (100.0 * r)) * dt_inv)
    scaled["K_H_co2"] = 0.035 * math.exp((-19410.0 / (100.0 * r)) * dt_inv)
    scaled["K_H_ch4"] = 0.0014 * math.exp((-14240.0 / (100.0 * r)) * dt_inv)
    scaled["K_H_h2"] = 7.8e-4 * math.exp((-4180.0 / (100.0 * r)) * dt_inv)
    scaled["p_gas_h2o"] = 0.0313 * math.exp(5290.0 * dt_inv)

    return scaled


class FullBatchRhs(FullCSTRRhs):
    """Full ADM1 ODE for batch operation (no influent/effluent).

    Mass balance: dy/dt = bio_dynamic − gas_transfer
    The dilution term (q/V) * (S_in − S) is absent for all liquid states.
    Gas dynamics remain unchanged — gas is still removed by pressure-driven outflow.
    """

    def __call__(self, t: float, y: np.ndarray) -> np.ndarray:
        del t
        dynamic_values = dynamic_state_dict(y, assembly=self.assembly)
        evaluation = self.evaluate(dynamic_values=dynamic_values, use_cache=True)
        rate_vector = np.asarray(
            [evaluation.rates[name] for name in self.assembly.biochemical_process_names], dtype=float
        )
        bio_dynamic = self.biochemical_matrix @ rate_vector
        derivatives = np.zeros(len(self.assembly.dynamic_state_names), dtype=float)

        # Batch: no dilution for liquid states — only biochemistry
        for state_name in self.assembly.dynamic_liquid_state_names:
            state_index = self.assembly.dynamic_state_index[state_name]
            derivatives[state_index] = bio_dynamic[state_index]

        # Gas-phase: same as CSTR (dissolved gas → gas space via k_L_a; gas exits by pressure)
        derivatives[self.assembly.dynamic_state_index["S_h2"]] -= evaluation.gas_transfer.rho_t8
        derivatives[self.assembly.dynamic_state_index["S_ch4"]] -= evaluation.gas_transfer.rho_t9
        derivatives[self.assembly.dynamic_state_index["S_IC"]] -= evaluation.gas_transfer.rho_t10
        derivatives[self.assembly.dynamic_state_index["S_gas_h2"]] = (
            -(evaluation.gas_transfer.q_gas / self.params["V_gas"]) * dynamic_values["S_gas_h2"]
            + evaluation.gas_transfer.rho_t8 * self.params["V_liq"] / self.params["V_gas"]
        )
        derivatives[self.assembly.dynamic_state_index["S_gas_ch4"]] = (
            -(evaluation.gas_transfer.q_gas / self.params["V_gas"]) * dynamic_values["S_gas_ch4"]
            + evaluation.gas_transfer.rho_t9 * self.params["V_liq"] / self.params["V_gas"]
        )
        derivatives[self.assembly.dynamic_state_index["S_gas_co2"]] = (
            -(evaluation.gas_transfer.q_gas / self.params["V_gas"]) * dynamic_values["S_gas_co2"]
            + evaluation.gas_transfer.rho_t10 * self.params["V_liq"] / self.params["V_gas"]
        )
        apply_extension_gas_derivatives(
            derivatives, 0, dynamic_values, bio_dynamic, evaluation.gas_transfer.q_gas,
            self.params, self.assembly,
        )
        return derivatives


class FullUASBRhs(FullCSTRRhs):
    """Full ADM1 ODE for UASB operation with biomass retention (SRT > HRT).

    In a UASB, the granular sludge blanket retains biomass. Soluble compounds wash
    out with the HRT (q/V_liq), while solid/biomass states wash out at a reduced
    effective rate: q_x/V = (q/V_liq) * washout_factor.

    washout_factor = 1 / (SRT / HRT) — default 0.35 for UASB
    (i.e. SRT ≈ 2.86 × HRT when washout_factor = 0.35)
    """

    def __init__(self, *, inputs: FullModelInputs, biomass_washout_factor: float = 0.35) -> None:
        super().__init__(inputs=inputs)
        self._washout_factor = float(biomass_washout_factor)
        # Pre-classify liquid states as soluble (phase=="liquid") vs solid (phase=="solid")
        phase_by_name = {state.name: state.phase for state in inputs.assembly.state_catalog}
        self._solid_state_names = frozenset(
            name
            for name in inputs.assembly.dynamic_liquid_state_names
            if phase_by_name.get(name, "liquid") == "solid"
        )

    def __call__(self, t: float, y: np.ndarray) -> np.ndarray:
        del t
        dynamic_values = dynamic_state_dict(y, assembly=self.assembly)
        evaluation = self.evaluate(dynamic_values=dynamic_values, use_cache=True)
        rate_vector = np.asarray(
            [evaluation.rates[name] for name in self.assembly.biochemical_process_names], dtype=float
        )
        bio_dynamic = self.biochemical_matrix @ rate_vector
        derivatives = np.zeros(len(self.assembly.dynamic_state_names), dtype=float)
        q_liq_over_v = self.params["q_ad"] / self.params["V_liq"]
        q_sol_over_v = q_liq_over_v * self._washout_factor

        for state_name in self.assembly.dynamic_liquid_state_names:
            state_index = self.assembly.dynamic_state_index[state_name]
            q_over_v = q_sol_over_v if state_name in self._solid_state_names else q_liq_over_v
            derivatives[state_index] = (
                q_liq_over_v * self.inputs.influent_values.get(state_name, 0.0) - q_over_v * dynamic_values[state_name]
                + bio_dynamic[state_index]
            )

        # Gas dynamics use total V_liq for gas-liquid transfer
        derivatives[self.assembly.dynamic_state_index["S_h2"]] -= evaluation.gas_transfer.rho_t8
        derivatives[self.assembly.dynamic_state_index["S_ch4"]] -= evaluation.gas_transfer.rho_t9
        derivatives[self.assembly.dynamic_state_index["S_IC"]] -= evaluation.gas_transfer.rho_t10
        derivatives[self.assembly.dynamic_state_index["S_gas_h2"]] = (
            -(evaluation.gas_transfer.q_gas / self.params["V_gas"]) * dynamic_values["S_gas_h2"]
            + evaluation.gas_transfer.rho_t8 * self.params["V_liq"] / self.params["V_gas"]
        )
        derivatives[self.assembly.dynamic_state_index["S_gas_ch4"]] = (
            -(evaluation.gas_transfer.q_gas / self.params["V_gas"]) * dynamic_values["S_gas_ch4"]
            + evaluation.gas_transfer.rho_t9 * self.params["V_liq"] / self.params["V_gas"]
        )
        derivatives[self.assembly.dynamic_state_index["S_gas_co2"]] = (
            -(evaluation.gas_transfer.q_gas / self.params["V_gas"]) * dynamic_values["S_gas_co2"]
            + evaluation.gas_transfer.rho_t10 * self.params["V_liq"] / self.params["V_gas"]
        )
        apply_extension_gas_derivatives(
            derivatives, 0, dynamic_values, bio_dynamic, evaluation.gas_transfer.q_gas,
            self.params, self.assembly,
        )
        return derivatives


class FullPlugFlowRhs:
    """Full ADM1 ODE for plug-flow (tanks-in-series approximation).

    N segments in series, each with volume V_liq/N and gas space V_gas/N.
    State vector layout: [seg_0_states, seg_1_states, ..., seg_{N-1}_states]
    Feed enters segment 0; effluent of segment i feeds segment i+1.

    Each segment maintains an independent pH cache (Newton-Raphson initial guess)
    for fast acid-base convergence. The biochemical stoichiometry matrix is shared.

    Reference: Batstone et al. (2005). ADM1 extensions — see plug-flow section in
    Bioresource Technology 96(12):1339-1346. doi:10.1016/j.biortech.2004.12.021
    """

    def __init__(self, *, inputs: FullModelInputs, n_segments: int) -> None:
        self.inputs = inputs
        self.assembly = inputs.assembly
        self.n_segments = max(int(n_segments), 2)
        self.n_states = len(self.assembly.dynamic_state_names)

        # Per-segment parameter dicts: same kinetics but scaled V and q
        v_seg = inputs.parameter_values["V_liq"] / self.n_segments
        v_gas_seg = inputs.parameter_values["V_gas"] / self.n_segments
        # q is the same for all segments (volumetric flow through each is q_ad)
        seg_params = dict(inputs.parameter_values)
        seg_params["V_liq"] = v_seg
        seg_params["V_gas"] = v_gas_seg
        seg_params["k_p"] /= self.n_segments
        self._seg_params: dict[str, float] = seg_params

        # Create one FullCSTRRhs per segment for shared biochemical matrix
        # We use the first segment's RHS to share the biochemical matrix and evaluate()
        seg_inputs = _inputs_with_params(inputs, seg_params)
        self._rhs = FullCSTRRhs(inputs=seg_inputs)
        self.biochemical_matrix = self._rhs.biochemical_matrix

        # Per-segment pH cache (initial Newton-Raphson guess)
        self._ph_caches: list[float] = [
            float(inputs.initial_values.get("S_H_ion", 1e-7))
        ] * self.n_segments

    @property
    def params(self) -> dict[str, float]:
        return self._seg_params

    def _evaluate_segment(
        self, dynamic_values: dict[str, float], seg_index: int
    ) -> FullStateEvaluation:
        """Evaluate one segment using its independent pH cache."""
        # Temporarily set the shared RHS pH cache to this segment's cache
        self._rhs._last_h_ion = self._ph_caches[seg_index]
        evaluation = self._rhs.evaluate(dynamic_values=dynamic_values, use_cache=True)
        self._ph_caches[seg_index] = self._rhs._last_h_ion
        return evaluation

    def __call__(self, t: float, y: np.ndarray) -> np.ndarray:
        del t
        n = self.n_segments
        m = self.n_states
        derivatives = np.zeros(n * m, dtype=float)
        q_over_v = self._seg_params["q_ad"] / self._seg_params["V_liq"]
        v_liq_seg = self._seg_params["V_liq"]
        v_gas_seg = self._seg_params["V_gas"]

        # Current segment state (from y vector) — clamp negatives to prevent
        # numeric divergence in multi-segment stiff systems.
        segments = [np.clip(y[i * m : (i + 1) * m], 0.0, None) for i in range(n)]

        for seg_i in range(n):
            seg_y = segments[seg_i]
            dynamic_values = dynamic_state_dict(seg_y, assembly=self.assembly)
            evaluation = self._evaluate_segment(dynamic_values, seg_i)
            rate_vector = np.asarray(
                [evaluation.rates[name] for name in self.assembly.biochemical_process_names], dtype=float
            )
            bio_seg = self.biochemical_matrix @ rate_vector

            # Influent to this segment: feed (seg 0) or previous segment (seg > 0)
            if seg_i == 0:
                influent = self.inputs.influent_values
            else:
                prev_y = segments[seg_i - 1]
                influent = {
                    name: float(max(prev_y[self.assembly.dynamic_state_index[name]], 0.0))
                    for name in self.assembly.dynamic_state_names
                }

            offset = seg_i * m
            for state_name in self.assembly.dynamic_liquid_state_names:
                idx = self.assembly.dynamic_state_index[state_name]
                derivatives[offset + idx] = (
                    q_over_v * (influent.get(state_name, 0.0) - dynamic_values[state_name])
                    + bio_seg[idx]
                )

            # Gas-liquid transfer (subtract from dissolved)
            derivatives[offset + self.assembly.dynamic_state_index["S_h2"]] -= evaluation.gas_transfer.rho_t8
            derivatives[offset + self.assembly.dynamic_state_index["S_ch4"]] -= evaluation.gas_transfer.rho_t9
            derivatives[offset + self.assembly.dynamic_state_index["S_IC"]] -= evaluation.gas_transfer.rho_t10

            # Gas-phase states for this segment
            derivatives[offset + self.assembly.dynamic_state_index["S_gas_h2"]] = (
                -(evaluation.gas_transfer.q_gas / v_gas_seg) * dynamic_values["S_gas_h2"]
                + evaluation.gas_transfer.rho_t8 * v_liq_seg / v_gas_seg
            )
            derivatives[offset + self.assembly.dynamic_state_index["S_gas_ch4"]] = (
                -(evaluation.gas_transfer.q_gas / v_gas_seg) * dynamic_values["S_gas_ch4"]
                + evaluation.gas_transfer.rho_t9 * v_liq_seg / v_gas_seg
            )
            derivatives[offset + self.assembly.dynamic_state_index["S_gas_co2"]] = (
                -(evaluation.gas_transfer.q_gas / v_gas_seg) * dynamic_values["S_gas_co2"]
                + evaluation.gas_transfer.rho_t10 * v_liq_seg / v_gas_seg
            )

            apply_extension_gas_derivatives(
                derivatives, offset, dynamic_values, bio_seg, evaluation.gas_transfer.q_gas,
                self._seg_params, self.assembly,
            )
        return derivatives

    def evaluate_last_segment(self, *, use_cache: bool) -> FullStateEvaluation:
        """Convenience: evaluate the last segment state (effluent) for diagnostics."""
        # Not used during integration; requires last y values passed externally.
        # Returns evaluation at a dummy state — callers should use system.evaluate() directly.
        raise NotImplementedError("Use solver.py post-processing loop for PlugFlow diagnostics.")


class FullTwoPhaseRhs:
    """Full ADM1 ODE for two-phase operation (hydrolysis/acidogenesis + methanogenesis).

    Two CSTRs in series sharing the same feed flow q_ad.
    State vector: [phase1_states..., phase2_states...]

    Phase 1 (hydrolysis/acidogenesis): V1 = f_vol * V_liq
    Phase 2 (methanogenesis):          V2 = (1−f_vol) * V_liq

    Since q is conserved in series: HRT1 = V1/q = f_vol * HRT_total,
    HRT2 = V2/q = (1−f_vol) * HRT_total. Volume fraction = HRT fraction.
    Gas volume is split proportionally to liquid volume.
    Phase 1 effluent is the influent to Phase 2. Phase 2 effluent leaves the system.
    """

    def __init__(
        self,
        *,
        inputs: FullModelInputs,
        phase1_volume_fraction: float = 0.3,
    ) -> None:
        self.inputs = inputs
        self.assembly = inputs.assembly
        self.n_states = len(self.assembly.dynamic_state_names)

        q_ad = float(inputs.parameter_values["q_ad"])
        v_liq = float(inputs.parameter_values["V_liq"])
        v_gas = float(inputs.parameter_values["V_gas"])
        f_vol = float(phase1_volume_fraction)

        # Volumes per phase — gas volume proportional to liquid volume
        v1_liq = v_liq * f_vol
        v2_liq = v_liq * (1.0 - f_vol)
        v1_gas = v_gas * f_vol
        v2_gas = v_gas * (1.0 - f_vol)

        # Build per-phase parameter dicts (q_ad is the same for both)
        params1 = dict(inputs.parameter_values)
        params1["V_liq"] = v1_liq
        params1["V_gas"] = max(v1_gas, 1.0)
        params1["V_ad"] = v1_liq + params1["V_gas"]
        self._params1 = params1

        params2 = dict(inputs.parameter_values)
        params2["V_liq"] = v2_liq
        params2["V_gas"] = max(v2_gas, 1.0)
        params2["V_ad"] = v2_liq + params2["V_gas"]
        self._params2 = params2

        # Per-phase RHS for shared evaluate() logic
        self._rhs1 = FullCSTRRhs(inputs=_inputs_with_params(inputs, params1))
        self._rhs2 = FullCSTRRhs(inputs=_inputs_with_params(inputs, params2))
        self.biochemical_matrix = self._rhs1.biochemical_matrix

        # q/V per phase
        self._q_over_v1 = q_ad / v1_liq
        self._q_over_v2 = q_ad / v2_liq

    def __call__(self, t: float, y: np.ndarray) -> np.ndarray:
        del t
        m = self.n_states
        derivatives = np.zeros(2 * m, dtype=float)
        y1 = y[:m]
        y2 = y[m:]

        # Phase 1: fed by system influent
        dv1 = y[:m].copy()
        dynamic1 = dynamic_state_dict(y1, assembly=self.assembly)
        ev1 = self._rhs1.evaluate(dynamic_values=dynamic1, use_cache=True)
        rv1 = np.asarray([ev1.rates[n] for n in self.assembly.biochemical_process_names], dtype=float)
        bio1 = self._rhs1.biochemical_matrix @ rv1

        for state_name in self.assembly.dynamic_liquid_state_names:
            idx = self.assembly.dynamic_state_index[state_name]
            derivatives[idx] = (
                self._q_over_v1 * (self.inputs.influent_values.get(state_name, 0.0) - dynamic1[state_name])
                + bio1[idx]
            )
        _apply_gas_derivatives(derivatives, 0, dynamic1, ev1, self._params1, self.assembly)
        apply_extension_gas_derivatives(
            derivatives, 0, dynamic1, bio1, ev1.gas_transfer.q_gas, self._params1, self.assembly,
        )

        # Phase 2: fed by phase 1 effluent (current phase 1 state)
        dynamic2 = dynamic_state_dict(y2, assembly=self.assembly)
        ev2 = self._rhs2.evaluate(dynamic_values=dynamic2, use_cache=True)
        rv2 = np.asarray([ev2.rates[n] for n in self.assembly.biochemical_process_names], dtype=float)
        bio2 = self._rhs2.biochemical_matrix @ rv2

        for state_name in self.assembly.dynamic_liquid_state_names:
            idx = self.assembly.dynamic_state_index[state_name]
            # Influent to phase 2 = current state of phase 1
            influent2 = float(max(dynamic1.get(state_name, 0.0), 0.0))
            derivatives[m + idx] = (
                self._q_over_v2 * (influent2 - dynamic2[state_name])
                + bio2[idx]
            )
        _apply_gas_derivatives(derivatives, m, dynamic2, ev2, self._params2, self.assembly)
        apply_extension_gas_derivatives(
            derivatives, m, dynamic2, bio2, ev2.gas_transfer.q_gas, self._params2, self.assembly,
        )

        return derivatives


class FullTPADRhs(FullTwoPhaseRhs):
    """Full ADM1 ODE for Temperature-Phased Anaerobic Digestion (TPAD).

    Extends FullTwoPhaseRhs with Arrhenius temperature correction for phase 1
    (thermophilic). Phase 2 operates at the reference temperature (35°C) with
    unscaled parameters.

    Kinetic parameters in phase 1 are scaled by:
        k(T1) = k(Tref) * exp(Ea/R * (1/Tref − 1/T1))
    where Ea/R = 6858 K for hydrolysis and 5030 K for biochemical processes.

    Reference: Batstone 2002, App. B; Guwy et al. (2008). "Temperature-phased
    anaerobic digestion of sewage sludge." Water Science and Technology 58(4):
    865-871. doi:10.2166/wst.2008.455
    """

    def __init__(
        self,
        *,
        inputs: FullModelInputs,
        phase1_volume_fraction: float = 0.25,
        thermo_temperature_c: float = 55.0,
        meso_temperature_c: float = 35.0,
        effective_hrt_days: float | None = None,
    ) -> None:
        # Phase HRTs are absolute: total volume = Q x (HRT_thermo + HRT_meso).
        # Without flow (batch) there is no HRT, so the given volume is kept.
        if effective_hrt_days is not None and inputs.parameter_values["q_ad"] > 0.0:
            params = dict(inputs.parameter_values)
            scale = params["q_ad"] * effective_hrt_days / params["V_liq"]
            params["V_liq"] *= scale
            params["V_gas"] *= scale
            params["V_ad"] = params["V_liq"] + params["V_gas"]
            inputs = _inputs_with_params(inputs, params)
        super().__init__(
            inputs=inputs,
            phase1_volume_fraction=phase1_volume_fraction,
        )
        # Override phase 1 parameters with thermophilic temperature-scaled kinetics
        scaled_params1 = _scale_params_for_temperature(self._params1, thermo_temperature_c)
        self._params1 = scaled_params1
        self._rhs1 = FullCSTRRhs(inputs=_inputs_with_params(inputs, scaled_params1))
        # Override phase 2 parameters with mesophilic temperature-scaled kinetics
        scaled_params2 = _scale_params_for_temperature(self._params2, meso_temperature_c)
        self._params2 = scaled_params2
        self._rhs2 = FullCSTRRhs(inputs=_inputs_with_params(inputs, scaled_params2))
        self.biochemical_matrix = self._rhs1.biochemical_matrix


def _apply_gas_derivatives(
    derivatives: np.ndarray,
    offset: int,
    dynamic_values: dict[str, float],
    evaluation: FullStateEvaluation,
    params: dict[str, float],
    assembly,
) -> None:
    """Apply gas-liquid transfer and gas-phase dynamics for one CSTR segment."""
    v_liq = params["V_liq"]
    v_gas = params["V_gas"]
    q_gas = evaluation.gas_transfer.q_gas
    rho_t8 = evaluation.gas_transfer.rho_t8
    rho_t9 = evaluation.gas_transfer.rho_t9
    rho_t10 = evaluation.gas_transfer.rho_t10

    derivatives[offset + assembly.dynamic_state_index["S_h2"]] -= rho_t8
    derivatives[offset + assembly.dynamic_state_index["S_ch4"]] -= rho_t9
    derivatives[offset + assembly.dynamic_state_index["S_IC"]] -= rho_t10
    derivatives[offset + assembly.dynamic_state_index["S_gas_h2"]] = (
        -(q_gas / v_gas) * dynamic_values["S_gas_h2"]
        + rho_t8 * v_liq / v_gas
    )
    derivatives[offset + assembly.dynamic_state_index["S_gas_ch4"]] = (
        -(q_gas / v_gas) * dynamic_values["S_gas_ch4"]
        + rho_t9 * v_liq / v_gas
    )
    derivatives[offset + assembly.dynamic_state_index["S_gas_co2"]] = (
        -(q_gas / v_gas) * dynamic_values["S_gas_co2"]
        + rho_t10 * v_liq / v_gas
    )


def _inputs_with_params(inputs: FullModelInputs, new_params: dict[str, float]) -> FullModelInputs:
    """Return a new FullModelInputs sharing the same states/assembly but with new_params."""
    from simulator.full_model.model import FullModelInputs as _FMI
    return _FMI(
        influent_values=inputs.influent_values,
        initial_values=inputs.initial_values,
        dynamic_influent=inputs.dynamic_influent,
        dynamic_initial=inputs.dynamic_initial,
        parameter_values=new_params,
        assembly=inputs.assembly,
    )


def build_reactor_mode(
    reactor_type: str,
    inputs: FullModelInputs,
    *,
    reactor_config: object | None = None,
) -> FullCSTRRhs | FullBatchRhs | FullUASBRhs | FullPlugFlowRhs | FullTwoPhaseRhs | FullTPADRhs:
    """Factory: create the appropriate RHS object for the given reactor type.

    Parameters
    ----------
    reactor_type : str
        One of "cstr", "batch", "uasb", "plug_flow", "two_phase", "tpad".
    inputs : FullModelInputs
        Assembled model inputs (assembly + parameters + influent + initial).
    reactor_config : ReactorConfig | None
        Optional reactor configuration object. When None, defaults are used.
    """
    from simulator.core.models import ReactorConfig, TwoPhaseConfig, TPADConfig, BatchConfig

    if isinstance(reactor_config, ReactorConfig):
        cfg = reactor_config
    else:
        cfg = None

    if reactor_type == "cstr":
        return FullCSTRRhs(inputs=inputs)

    if reactor_type == "batch":
        return FullBatchRhs(inputs=inputs)

    if reactor_type == "uasb":
        washout = 0.35  # UASB default
        if cfg is not None and cfg.biomass_washout_factor is not None:
            washout = float(cfg.biomass_washout_factor)
        return FullUASBRhs(inputs=inputs, biomass_washout_factor=washout)

    if reactor_type == "plug_flow":
        # Default 2 segments for full model (35+ states per segment → ~70 ODEs).
        # More segments can be requested via ReactorConfig but increase computation time significantly.
        n_seg = 2
        if cfg is not None:
            n_seg = cfg.segments
        return FullPlugFlowRhs(inputs=inputs, n_segments=n_seg)

    if reactor_type == "two_phase":
        two_phase_cfg = TwoPhaseConfig()
        if cfg is not None and cfg.two_phase is not None:
            two_phase_cfg = cfg.two_phase
        return FullTwoPhaseRhs(
            inputs=inputs,
            phase1_volume_fraction=float(two_phase_cfg.phase1_volume_fraction),
        )

    if reactor_type == "tpad":
        tpad_cfg = TPADConfig()
        if cfg is not None and cfg.tpad is not None:
            tpad_cfg = cfg.tpad
        return FullTPADRhs(
            inputs=inputs,
            phase1_volume_fraction=float(tpad_cfg.thermo_volume_fraction),
            effective_hrt_days=float(tpad_cfg.thermo_hrt_days + tpad_cfg.meso_hrt_days),
            thermo_temperature_c=float(tpad_cfg.thermo_temperature_c),
            meso_temperature_c=float(tpad_cfg.meso_temperature_c),
        )

    raise ValueError(f"Reactor type não suportado pelo backend full: '{reactor_type}'")
