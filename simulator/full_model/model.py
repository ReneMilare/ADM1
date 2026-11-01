from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping

import numpy as np

from simulator.core.defaults import make_default_kinetics
from simulator.core.models import FeedDefinition, InitialState, KineticParameters, OperatingConditions
from simulator.core.pyadm1_backend import P_ATM_BAR, V_GAS_RATIO, _build_influent_frame, _build_initial_frame
from simulator.full_model.assembly import FullModelAssembly
from simulator.full_model.extension_registry import resolve_full_model_assembly
from simulator.full_model.state_catalog import FULL_STATE_CATALOG
from simulator.full_model.parameters import THERMOPHILIC_STR_OVERRIDES
from simulator.full_model.stoichiometry import CARBON_SIGMA_TERMS

SAFE_EVAL_GLOBALS = {"__builtins__": {}}
DEFAULT_FULL_MODEL_ASSEMBLY = resolve_full_model_assembly(())
FULL_STATE_NAMES = DEFAULT_FULL_MODEL_ASSEMBLY.full_state_names
FULL_STATE_INDEX = DEFAULT_FULL_MODEL_ASSEMBLY.full_state_index
DYNAMIC_STATE_NAMES = DEFAULT_FULL_MODEL_ASSEMBLY.dynamic_state_names
DYNAMIC_STATE_INDEX = DEFAULT_FULL_MODEL_ASSEMBLY.dynamic_state_index
DYNAMIC_GAS_STATE_NAMES = DEFAULT_FULL_MODEL_ASSEMBLY.dynamic_gas_state_names
DYNAMIC_LIQUID_STATE_NAMES = DEFAULT_FULL_MODEL_ASSEMBLY.dynamic_liquid_state_names


@dataclass(frozen=True, slots=True)
class FullModelInputs:
    influent_values: dict[str, float]
    initial_values: dict[str, float]
    dynamic_influent: np.ndarray
    dynamic_initial: np.ndarray
    parameter_values: dict[str, float]
    assembly: FullModelAssembly
    temperature_kinetics: str = "off"
    parameter_set: str = "mesophilic_bsm2"


@dataclass(frozen=True, slots=True)
class FullModelState:
    values: dict[str, float]
    vector: np.ndarray



def build_full_inputs(
    *,
    operating_conditions: OperatingConditions,
    feed: FeedDefinition,
    initial_state: InitialState,
    parameters: KineticParameters,
    active_extensions: list[str] | tuple[str, ...] | None = None,
    extension_parameter_overrides: Mapping[str, float] | None = None,
    initial_state_overrides: Mapping[str, float] | None = None,
    influent_state_overrides: Mapping[str, float] | None = None,
) -> FullModelInputs:
    influent_frame = _build_influent_frame(
        time_grid=np.asarray([0.0], dtype=float),
        feed=feed,
        operating_conditions=operating_conditions,
    )
    initial_frame = _build_initial_frame(
        initial_state=initial_state, feed=feed, temperature_c=operating_conditions.temperature_c
    )
    influent_values = {name: float(influent_frame.iloc[0][name]) for name in influent_frame.columns if name != "time"}
    initial_values = {name: float(initial_frame.iloc[0][name]) for name in initial_frame.columns}
    for name, value in (influent_state_overrides or {}).items():
        if value in (None, ""):
            continue
        influent_values[name] = float(value)
    for name, value in (initial_state_overrides or {}).items():
        if value in (None, ""):
            continue
        initial_values[name] = float(value)
    return build_full_inputs_from_state_maps(
        operating_conditions=operating_conditions,
        parameters=parameters,
        influent_values=influent_values,
        initial_values=initial_values,
        flow_rate_m3_day=float(feed.flow_rate_m3_day or (operating_conditions.volume_m3 / operating_conditions.hrt_days)),
        active_extensions=active_extensions,
        extension_parameter_overrides=extension_parameter_overrides,
    )



def build_full_inputs_from_state_maps(
    *,
    operating_conditions: OperatingConditions,
    parameters: KineticParameters,
    influent_values: Mapping[str, float],
    initial_values: Mapping[str, float],
    flow_rate_m3_day: float | None = None,
    active_extensions: list[str] | tuple[str, ...] | None = None,
    extension_parameter_overrides: Mapping[str, float] | None = None,
) -> FullModelInputs:
    assembly = resolve_full_model_assembly(active_extensions)
    normalized_influent = _normalize_state_map(influent_values, assembly=assembly)
    normalized_initial = _normalize_state_map(initial_values, assembly=assembly)
    _seed_multi_population(normalized_influent)
    _seed_multi_population(normalized_initial)
    parameter_values = resolve_full_parameter_values(
        operating_conditions=operating_conditions,
        parameters=parameters,
        flow_rate_m3_day=flow_rate_m3_day or float(normalized_influent.get("Q", 0.0) or (operating_conditions.volume_m3 / operating_conditions.hrt_days)),
        assembly=assembly,
        extension_parameter_overrides=extension_parameter_overrides,
    )
    return FullModelInputs(
        influent_values=normalized_influent,
        initial_values=normalized_initial,
        dynamic_influent=np.asarray([normalized_influent[name] for name in assembly.dynamic_state_names], dtype=float),
        dynamic_initial=np.asarray([normalized_initial[name] for name in assembly.dynamic_state_names], dtype=float),
        parameter_values=parameter_values,
        assembly=assembly,
        temperature_kinetics=parameters.temperature_kinetics,
        parameter_set=parameters.parameter_set,
    )



def resolve_full_parameter_values(
    *,
    operating_conditions: OperatingConditions,
    parameters: KineticParameters,
    feed: FeedDefinition | None = None,
    flow_rate_m3_day: float | None = None,
    assembly: FullModelAssembly = DEFAULT_FULL_MODEL_ASSEMBLY,
    extension_parameter_overrides: Mapping[str, float] | None = None,
) -> dict[str, float]:
    values = dict(assembly.parameter_defaults)
    if parameters.parameter_set == "thermophilic_str":
        values.update(THERMOPHILIC_STR_OVERRIDES)
    default_kinetics = make_default_kinetics()
    temperature_k = float(operating_conditions.temperature_c) + 273.15
    liquid_volume = float(operating_conditions.volume_m3)
    gas_volume = max(liquid_volume * V_GAS_RATIO, 1.0)
    flow_rate = float(
        flow_rate_m3_day
        or (
            feed.flow_rate_m3_day
            if feed is not None and feed.flow_rate_m3_day is not None
            else (liquid_volume / operating_conditions.hrt_days)
        )
    )

    values.update(
        {
            "T_op": temperature_k,
            "T_ad": temperature_k,
            "V_liq": liquid_volume,
            "V_gas": gas_volume,
            "V_ad": liquid_volume + gas_volume,
            "q_ad": flow_rate,
            "p_atm": P_ATM_BAR,
            "k_hyd_ch": values["k_hyd_ch"] * _ratio(parameters.k_hyd, default_kinetics.k_hyd),
            "k_hyd_pr": values["k_hyd_pr"] * _ratio(parameters.k_hyd, default_kinetics.k_hyd),
            "k_hyd_li": values["k_hyd_li"] * _ratio(parameters.k_hyd, default_kinetics.k_hyd),
            "k_m_su": values["k_m_su"] * _ratio(parameters.k_m_su, default_kinetics.k_m_su),
            "k_m_pro": values["k_m_pro"] * _ratio(parameters.k_m_pro, default_kinetics.k_m_pro),
            "k_m_ac": values["k_m_ac"] * _ratio(parameters.k_m_ac, default_kinetics.k_m_ac),
            "k_m_h2": values["k_m_h2"] * _ratio(parameters.k_m_h2, default_kinetics.k_m_h2),
            "K_S_su": values["K_S_su"] * _ratio(parameters.k_s_su, default_kinetics.k_s_su),
            "K_S_pro": values["K_S_pro"] * _ratio(parameters.k_s_pro, default_kinetics.k_s_pro),
            "K_S_ac": values["K_S_ac"] * _ratio(parameters.k_s_ac, default_kinetics.k_s_ac),
            "K_S_h2": values["K_S_h2"] * _ratio(parameters.k_s_h2, default_kinetics.k_s_h2),
            "Y_su": values["Y_su"] * _ratio(parameters.acidogen_yield, default_kinetics.acidogen_yield),
            "Y_aa": values["Y_aa"] * _ratio(parameters.acidogen_yield, default_kinetics.acidogen_yield),
            "Y_fa": values["Y_fa"] * _ratio(parameters.acidogen_yield, default_kinetics.acidogen_yield),
            "Y_c4": values["Y_c4"] * _ratio(parameters.acidogen_yield, default_kinetics.acidogen_yield),
            "Y_pro": values["Y_pro"] * _ratio(parameters.propionate_yield, default_kinetics.propionate_yield),
            "Y_ac": values["Y_ac"] * _ratio(parameters.acetoclastic_yield, default_kinetics.acetoclastic_yield),
            "Y_h2": values["Y_h2"] * _ratio(parameters.hydrogenotrophic_yield, default_kinetics.hydrogenotrophic_yield),
            "k_dec_X_su": values["k_dec_X_su"] * _ratio(parameters.decay_acidogens, default_kinetics.decay_acidogens),
            "k_dec_X_aa": values["k_dec_X_aa"] * _ratio(parameters.decay_acidogens, default_kinetics.decay_acidogens),
            "k_dec_X_fa": values["k_dec_X_fa"] * _ratio(parameters.decay_acidogens, default_kinetics.decay_acidogens),
            "k_dec_X_c4": values["k_dec_X_c4"] * _ratio(parameters.decay_acidogens, default_kinetics.decay_acidogens),
            "k_dec_X_pro": values["k_dec_X_pro"] * _ratio(parameters.decay_propionate_biomass, default_kinetics.decay_propionate_biomass),
            "k_dec_X_ac": values["k_dec_X_ac"] * _ratio(parameters.decay_acetoclastic, default_kinetics.decay_acetoclastic),
            "k_dec_X_h2": values["k_dec_X_h2"] * _ratio(parameters.decay_hydrogenotrophic, default_kinetics.decay_hydrogenotrophic),
            "k_L_a": values["k_L_a"] * _ratio(parameters.gas_stripping_h2, default_kinetics.gas_stripping_h2),
        }
    )

    for name, value in (extension_parameter_overrides or {}).items():
        if name not in assembly.parameter_defaults:
            raise ValueError(f"Parâmetro full desconhecido para override: {name}")
        values[name] = float(value)

    temperature_k = values["T_op"]
    values["K_w"] = 10 ** -14.0 * math.exp((55900.0 / (100.0 * values["R"])) * (1.0 / values["T_base"] - 1.0 / temperature_k))
    values["K_a_co2"] = 10 ** -6.35 * math.exp((7646.0 / (100.0 * values["R"])) * (1.0 / values["T_base"] - 1.0 / temperature_k))
    values["K_a_IN"] = 10 ** -9.25 * math.exp((51965.0 / (100.0 * values["R"])) * (1.0 / values["T_base"] - 1.0 / temperature_k))
    values["p_gas_h2o"] = 0.0313 * math.exp(5290.0 * (1.0 / values["T_base"] - 1.0 / temperature_k))
    values["K_H_co2"] = 0.035 * math.exp((-19410.0 / (100.0 * values["R"])) * (1.0 / values["T_base"] - 1.0 / temperature_k))
    values["K_H_ch4"] = 0.0014 * math.exp((-14240.0 / (100.0 * values["R"])) * (1.0 / values["T_base"] - 1.0 / temperature_k))
    values["K_H_h2"] = 7.8e-4 * math.exp((-4180.0 / (100.0 * values["R"])) * (1.0 / values["T_base"] - 1.0 / temperature_k))
    values["K_pH_aa"] = 10 ** (-(values["pH_LL_aa"] + values["pH_UL_aa"]) / 2.0)
    values["nn_aa"] = 3.0 / max(values["pH_UL_aa"] - values["pH_LL_aa"], 1e-9)
    values["K_pH_ac"] = 10 ** (-(values["pH_LL_ac"] + values["pH_UL_ac"]) / 2.0)
    values["n_ac"] = 3.0 / max(values["pH_UL_ac"] - values["pH_LL_ac"], 1e-9)
    values["K_pH_h2"] = 10 ** (-(values["pH_LL_h2"] + values["pH_UL_h2"]) / 2.0)
    values["n_h2"] = 3.0 / max(values["pH_UL_h2"] - values["pH_LL_h2"], 1e-9)
    values["hydrogen_solver_tol"] = 1e-12
    values["ph_solver_tol"] = 1e-12
    values["max_newton_iterations"] = 1000.0

    values.update({name: float(value) for name, value in (extension_parameter_overrides or {}).items()})
    if parameters.temperature_kinetics == "siegrist2002" and parameters.parameter_set == "mesophilic_bsm2":
        values = scale_siegrist_kinetics(values, float(operating_conditions.temperature_c))
    _require_positive_denominators(values)
    for fraction, extension in (("f_lac_su", "lactate"), ("f_et_su", "ethanol")):
        if values[fraction] > 0.0 and extension not in assembly.active_extensions:
            raise ValueError(f"{fraction} > 0 requer a extensão {extension} ativa para conservar DQO e carbono.")
    return values



# Parameter families used as denominators in rate laws (inhibition constants,
# half-saturations, acid/Henry/trace-element constants) and the reactor volumes.
_DENOMINATOR_PREFIXES = ("K_I_", "K_S_", "K_TE_", "K_a_", "K_H_", "K_c_", "Ksp_")
_DENOMINATOR_NAMES = ("K_w", "V_liq", "V_gas", "V_ad")


def _require_positive_denominators(values: Mapping[str, float]) -> None:
    """Reject zero or negative values (after overrides) that would divide rate laws by zero."""
    for name, value in values.items():
        if name.startswith(_DENOMINATOR_PREFIXES) or name in _DENOMINATOR_NAMES:
            if not float(value) > 0.0:
                raise ValueError(f"Parâmetro {name} deve ser estritamente positivo (recebido {value}).")


# Siegrist et al. (2002), Table 3, doi:10.1021/es010139p. C4 has no
# separate group: use anaerobic oxidation for rates and propionate for K_S.
_SIEGRIST_THETA = {
    **dict.fromkeys(("k_hyd_ch", "k_hyd_pr", "k_hyd_li"), 0.024),
    **dict.fromkeys(("k_m_su", "k_m_aa", "k_m_ac", "k_m_h2",
                     "k_dec_X_su", "k_dec_X_aa", "k_dec_X_ac", "k_dec_X_h2",
                     "K_S_su", "K_S_aa"), 0.069),
    **dict.fromkeys(("k_m_fa", "k_m_c4", "k_m_pro", "k_dec_X_fa",
                     "k_dec_X_c4", "k_dec_X_pro"), 0.055),
    "K_S_fa": 0.035,
    **dict.fromkeys(("K_S_c4", "K_S_pro", "K_S_ac"), 0.10),
    **dict.fromkeys(("K_S_h2", "K_I_h2_fa", "K_I_h2_c4", "K_I_h2_pro"), 0.08),
    "K_I_nh3": 0.086,
}

def scale_siegrist_kinetics(values: Mapping[str, float], temperature_c: float, reference_c: float = 35.0) -> dict[str, float]:
    """Scale base ADM1 kinetics between temperatures; extension parameters stay unchanged."""
    scaled = dict(values)
    for name, theta in _SIEGRIST_THETA.items():
        scaled[name] *= math.exp(theta * (temperature_c - reference_c))
    return scaled


_MULTI_POPULATION_SEEDS = (("X_ac", ("X_ac_1", "X_ac_2")), ("X_h2", ("X_h2_1", "X_h2_2")))


def _seed_multi_population(values: dict[str, float]) -> None:
    # With the multi-population extension the core X_ac/X_h2 have no active
    # process (inert biomass that would only wash out). Always move their COD
    # into the sub-populations, split evenly and added to any given values,
    # so total biomass COD is conserved and no core biomass remains.
    for core, populations in _MULTI_POPULATION_SEEDS:
        if not all(name in values for name in populations):
            continue
        core_value = max(values.get(core, 0.0), 0.0)
        for name in populations:
            values[name] = max(values[name], 0.0) + core_value / len(populations)
        values[core] = 0.0


def _normalize_state_map(values: Mapping[str, float], *, assembly: FullModelAssembly) -> dict[str, float]:
    normalized = {name: float(values.get(name, 0.0)) for name in assembly.full_state_names}
    for extra_name in ("Q", "T (C)"):
        if extra_name in values:
            normalized[extra_name] = float(values[extra_name])
    return normalized



def build_numeric_biochemical_matrix(
    parameter_values: Mapping[str, float],
    assembly: FullModelAssembly = DEFAULT_FULL_MODEL_ASSEMBLY,
) -> np.ndarray:
    namespace = dict(parameter_values)
    sigma_terms = {
        name: float(eval(expression, SAFE_EVAL_GLOBALS, namespace))
        for name, expression in CARBON_SIGMA_TERMS.items()
    }
    namespace.update(sigma_terms)
    matrix = np.zeros((len(assembly.dynamic_state_names), len(assembly.biochemical_process_names)), dtype=float)
    for process_index, process_name in enumerate(assembly.biochemical_process_names):
        row = assembly.biochemical_stoichiometry_rows[process_name]
        for state_name, expression in row.items():
            if state_name not in assembly.dynamic_state_index:
                continue
            matrix[assembly.dynamic_state_index[state_name], process_index] = float(eval(expression, SAFE_EVAL_GLOBALS, namespace))
    return matrix



def dynamic_state_dict(
    dynamic_vector: np.ndarray,
    assembly: FullModelAssembly = DEFAULT_FULL_MODEL_ASSEMBLY,
) -> dict[str, float]:
    clipped = np.clip(np.asarray(dynamic_vector, dtype=float), a_min=0.0, a_max=None)
    return {name: float(clipped[index]) for index, name in enumerate(assembly.dynamic_state_names)}



def assemble_full_state(
    dynamic_values: Mapping[str, float],
    *,
    s_h2: float,
    s_h_ion: float,
    acid_values: Mapping[str, float],
    assembly: FullModelAssembly = DEFAULT_FULL_MODEL_ASSEMBLY,
) -> FullModelState:
    values = {name: float(dynamic_values.get(name, 0.0)) for name in assembly.dynamic_state_names}
    values.update(
        {
            "S_h2": float(max(s_h2, 0.0)),
            "S_H_ion": float(max(s_h_ion, 1e-14)),
            "S_va_ion": float(max(acid_values["S_va_ion"], 0.0)),
            "S_bu_ion": float(max(acid_values["S_bu_ion"], 0.0)),
            "S_pro_ion": float(max(acid_values["S_pro_ion"], 0.0)),
            "S_ac_ion": float(max(acid_values["S_ac_ion"], 0.0)),
            "S_hco3_ion": float(max(acid_values["S_hco3_ion"], 0.0)),
            "S_co2": float(max(acid_values["S_co2"], 0.0)),
            "S_nh3": float(max(acid_values["S_nh3"], 0.0)),
            "S_nh4_ion": float(max(acid_values["S_nh4_ion"], 0.0)),
        }
    )
    for name in assembly.full_state_names:
        values.setdefault(name, float(dynamic_values.get(name, 0.0)))
    vector = np.asarray([float(values[name]) for name in assembly.full_state_names], dtype=float)
    return FullModelState(values=values, vector=vector)



def _ratio(value: float, baseline: float) -> float:
    if abs(baseline) <= 1e-12:
        return 1.0
    return max(float(value) / float(baseline), 1e-6)
