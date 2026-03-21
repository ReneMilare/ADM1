"""Catalogs, runtime helpers and canonical metadata for the native ADM1 full model."""

from simulator.full_model.acid_base import AcidBaseState, solve_acid_base
from simulator.full_model.adapter import FullModelInputs, build_backend_inputs, build_backend_inputs_from_state_maps, translate_backend_profiles
from simulator.full_model.assembly import FullModelAssembly, build_full_model_assembly, validate_full_model_assembly
from simulator.full_model.diagnostics import translate_full_profiles
from simulator.full_model.extension_registry import list_registered_extensions, resolve_full_model_assembly
from simulator.full_model.extensions import FullModelExtension, FullModelExtensionContribution
from simulator.full_model.model import (
    DEFAULT_FULL_MODEL_ASSEMBLY,
    DYNAMIC_STATE_INDEX,
    DYNAMIC_STATE_NAMES,
    FULL_STATE_INDEX,
    FULL_STATE_NAMES,
    FullModelState,
    assemble_full_state,
    build_full_inputs,
    build_full_inputs_from_state_maps,
    build_numeric_biochemical_matrix,
    dynamic_state_dict,
    resolve_full_parameter_values,
)
from simulator.full_model.parameters import FULL_PARAMETER_CATALOG, FULL_PARAMETER_DEFAULTS, FULL_PARAMETER_INDEX, FULL_PARAMETER_NAMES
from simulator.full_model.pilot_tracer_extension import PILOT_TRACER_EXTENSION
from simulator.full_model.process_catalog import (
    ACID_BASE_PROCESS_NAMES,
    BIOCHEMICAL_PROCESS_NAMES,
    FULL_PROCESS_CATALOG,
    FULL_PROCESS_INDEX,
    FULL_PROCESS_NAMES,
    GAS_TRANSFER_PROCESS_NAMES,
)
from simulator.full_model.rhs import FullCSTRRhs, FullStateEvaluation
from simulator.full_model.solver import simulate_with_full, simulate_with_full_inputs
from simulator.full_model.state_catalog import (
    ALGEBRAIC_STATE_NAMES,
    FULL_STATE_CATALOG,
    PSEUDO_STATE_NAMES,
)
from simulator.full_model.stoichiometry import (
    ACID_BASE_RELATIONS,
    BIOCHEMICAL_STOICHIOMETRY_ROWS,
    CARBON_SIGMA_TERMS,
    CHARGE_BALANCE_RESIDUAL,
    GAS_TRANSFER_RELATIONS,
    dense_biochemical_symbolic_matrix,
)

__all__ = [
    "ACID_BASE_PROCESS_NAMES",
    "ACID_BASE_RELATIONS",
    "AcidBaseState",
    "ALGEBRAIC_STATE_NAMES",
    "assemble_full_state",
    "BIOCHEMICAL_PROCESS_NAMES",
    "BIOCHEMICAL_STOICHIOMETRY_ROWS",
    "build_backend_inputs",
    "build_backend_inputs_from_state_maps",
    "build_full_inputs",
    "build_full_inputs_from_state_maps",
    "build_full_model_assembly",
    "build_numeric_biochemical_matrix",
    "CARBON_SIGMA_TERMS",
    "CHARGE_BALANCE_RESIDUAL",
    "DEFAULT_FULL_MODEL_ASSEMBLY",
    "DYNAMIC_STATE_INDEX",
    "DYNAMIC_STATE_NAMES",
    "dynamic_state_dict",
    "FULL_PARAMETER_CATALOG",
    "FULL_PARAMETER_DEFAULTS",
    "FULL_PARAMETER_INDEX",
    "FULL_PARAMETER_NAMES",
    "FULL_PROCESS_CATALOG",
    "FULL_PROCESS_INDEX",
    "FULL_PROCESS_NAMES",
    "FULL_STATE_CATALOG",
    "FULL_STATE_INDEX",
    "FULL_STATE_NAMES",
    "FullCSTRRhs",
    "FullModelAssembly",
    "FullModelExtension",
    "FullModelExtensionContribution",
    "FullModelInputs",
    "FullModelState",
    "FullStateEvaluation",
    "GAS_TRANSFER_PROCESS_NAMES",
    "GAS_TRANSFER_RELATIONS",
    "list_registered_extensions",
    "PILOT_TRACER_EXTENSION",
    "PSEUDO_STATE_NAMES",
    "resolve_full_model_assembly",
    "resolve_full_parameter_values",
    "simulate_with_full",
    "simulate_with_full_inputs",
    "solve_acid_base",
    "translate_backend_profiles",
    "translate_full_profiles",
    "validate_full_model_assembly",
    "dense_biochemical_symbolic_matrix",
]
