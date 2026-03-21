from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from simulator.full_model.catalog_types import ParameterDefinition, ProcessDefinition, RelationDefinition, StateDefinition
from simulator.full_model.extensions import AssemblyValidationHook, DiagnosticHook, ProcessRateFunction
from simulator.full_model.parameters import FULL_PARAMETER_CATALOG
from simulator.full_model.process_catalog import FULL_PROCESS_CATALOG
from simulator.full_model.state_catalog import FULL_STATE_CATALOG
from simulator.full_model.stoichiometry import ACID_BASE_RELATIONS, BIOCHEMICAL_STOICHIOMETRY_ROWS, GAS_TRANSFER_RELATIONS


@dataclass(frozen=True, slots=True)
class FullModelAssembly:
    active_extensions: tuple[str, ...]
    state_catalog: tuple[StateDefinition, ...]
    process_catalog: tuple[ProcessDefinition, ...]
    parameter_catalog: tuple[ParameterDefinition, ...]
    biochemical_stoichiometry_rows: dict[str, dict[str, str]]
    acid_base_relations: dict[str, RelationDefinition]
    gas_transfer_relations: dict[str, RelationDefinition]
    extension_rate_functions: tuple[ProcessRateFunction, ...]
    diagnostics_hooks: tuple[DiagnosticHook, ...]
    validation_hooks: tuple[AssemblyValidationHook, ...]

    full_state_names: tuple[str, ...]
    full_state_index: dict[str, int]
    dynamic_state_names: tuple[str, ...]
    dynamic_state_index: dict[str, int]
    algebraic_state_names: tuple[str, ...]
    pseudo_state_names: tuple[str, ...]
    dynamic_gas_state_names: tuple[str, ...]
    dynamic_liquid_state_names: tuple[str, ...]

    full_process_names: tuple[str, ...]
    full_process_index: dict[str, int]
    biochemical_process_names: tuple[str, ...]
    acid_base_process_names: tuple[str, ...]
    gas_transfer_process_names: tuple[str, ...]

    parameter_names: tuple[str, ...]
    parameter_index: dict[str, int]
    parameter_defaults: dict[str, float]


def build_full_model_assembly(*, extensions: tuple[object, ...] = (), extension_names: tuple[str, ...] = ()) -> FullModelAssembly:
    state_catalog = list(FULL_STATE_CATALOG)
    process_catalog = list(FULL_PROCESS_CATALOG)
    parameter_catalog = list(FULL_PARAMETER_CATALOG)
    biochemical_rows = {name: dict(row) for name, row in BIOCHEMICAL_STOICHIOMETRY_ROWS.items()}
    acid_base_relations = dict(ACID_BASE_RELATIONS)
    gas_transfer_relations = dict(GAS_TRANSFER_RELATIONS)
    rate_functions: list[ProcessRateFunction] = []
    diagnostics_hooks: list[DiagnosticHook] = []
    validation_hooks: list[AssemblyValidationHook] = []

    for extension in extensions:
        contribution = extension.contribute()
        _ensure_unique_names(state_catalog, contribution.states, "estado")
        _ensure_unique_names(process_catalog, contribution.processes, "processo")
        _ensure_unique_names(parameter_catalog, contribution.parameters, "par?metro")
        state_catalog.extend(contribution.states)
        process_catalog.extend(contribution.processes)
        parameter_catalog.extend(contribution.parameters)
        for process_name, row in contribution.biochemical_stoichiometry_rows.items():
            if process_name in biochemical_rows:
                raise ValueError(f"Linha estequiom?trica duplicada para '{process_name}'")
            biochemical_rows[process_name] = {name: str(expression) for name, expression in row.items()}
        _merge_unique_relations(acid_base_relations, contribution.acid_base_relations, "?cido-base")
        _merge_unique_relations(gas_transfer_relations, contribution.gas_transfer_relations, "gasosa")
        if contribution.rate_function is not None:
            rate_functions.append(contribution.rate_function)
        if contribution.diagnostics_hook is not None:
            diagnostics_hooks.append(contribution.diagnostics_hook)
        if contribution.validate_hook is not None:
            validation_hooks.append(contribution.validate_hook)

    full_state_names = tuple(state.name for state in state_catalog)
    full_state_index = {name: index for index, name in enumerate(full_state_names)}
    dynamic_state_names = tuple(state.name for state in state_catalog if state.role == "dynamic")
    dynamic_state_index = {name: index for index, name in enumerate(dynamic_state_names)}
    algebraic_state_names = tuple(state.name for state in state_catalog if state.role == "algebraic")
    pseudo_state_names = tuple(state.name for state in state_catalog if state.role == "pseudo_state")
    dynamic_gas_state_names = tuple(
        state.name for state in state_catalog if state.role == "dynamic" and state.phase == "gas"
    )
    dynamic_liquid_state_names = tuple(name for name in dynamic_state_names if name not in dynamic_gas_state_names)

    full_process_names = tuple(process.name for process in process_catalog)
    full_process_index = {name: index for index, name in enumerate(full_process_names)}
    biochemical_process_names = tuple(process.name for process in process_catalog if process.family == "biochemical")
    acid_base_process_names = tuple(process.name for process in process_catalog if process.family == "acid_base")
    gas_transfer_process_names = tuple(process.name for process in process_catalog if process.family == "gas_transfer")

    parameter_names = tuple(parameter.name for parameter in parameter_catalog)
    parameter_index = {name: index for index, name in enumerate(parameter_names)}
    parameter_defaults = {parameter.name: float(parameter.value) for parameter in parameter_catalog}

    assembly = FullModelAssembly(
        active_extensions=extension_names,
        state_catalog=tuple(state_catalog),
        process_catalog=tuple(process_catalog),
        parameter_catalog=tuple(parameter_catalog),
        biochemical_stoichiometry_rows=biochemical_rows,
        acid_base_relations=acid_base_relations,
        gas_transfer_relations=gas_transfer_relations,
        extension_rate_functions=tuple(rate_functions),
        diagnostics_hooks=tuple(diagnostics_hooks),
        validation_hooks=tuple(validation_hooks),
        full_state_names=full_state_names,
        full_state_index=full_state_index,
        dynamic_state_names=dynamic_state_names,
        dynamic_state_index=dynamic_state_index,
        algebraic_state_names=algebraic_state_names,
        pseudo_state_names=pseudo_state_names,
        dynamic_gas_state_names=dynamic_gas_state_names,
        dynamic_liquid_state_names=dynamic_liquid_state_names,
        full_process_names=full_process_names,
        full_process_index=full_process_index,
        biochemical_process_names=biochemical_process_names,
        acid_base_process_names=acid_base_process_names,
        gas_transfer_process_names=gas_transfer_process_names,
        parameter_names=parameter_names,
        parameter_index=parameter_index,
        parameter_defaults=parameter_defaults,
    )
    validate_full_model_assembly(assembly)
    return assembly


def validate_full_model_assembly(assembly: FullModelAssembly) -> None:
    state_set = set(assembly.full_state_names)
    process_family = {process.name: process.family for process in assembly.process_catalog}

    for process_name, row in assembly.biochemical_stoichiometry_rows.items():
        unknown_states = set(row) - state_set
        if unknown_states:
            raise ValueError(f"Estados desconhecidos na estequiometria do assembly full: {sorted(unknown_states)}")
        if process_family.get(process_name) != "biochemical":
            raise ValueError(f"A linha '{process_name}' n?o referencia um processo bioqu?mico do assembly.")

    if set(assembly.biochemical_stoichiometry_rows) != set(assembly.biochemical_process_names):
        raise ValueError("As linhas bioqu?micas do assembly n?o cobrem exatamente os processos bioqu?micos ativos.")
    if set(assembly.acid_base_relations) != set(assembly.acid_base_process_names):
        raise ValueError("As rela??es ?cido-base do assembly n?o cobrem exatamente os processos ativos.")
    if set(assembly.gas_transfer_relations) != set(assembly.gas_transfer_process_names):
        raise ValueError("As rela??es gasosas do assembly n?o cobrem exatamente os processos ativos.")

    for hook in assembly.validation_hooks:
        hook(assembly)


def _ensure_unique_names(existing_items: list[object], new_items: tuple[object, ...], item_kind: str) -> None:
    existing_names = {item.name for item in existing_items}
    duplicate_names = sorted(item.name for item in new_items if item.name in existing_names)
    if duplicate_names:
        raise ValueError(f"{item_kind.capitalize()}s duplicados no assembly full: {duplicate_names}")


def _merge_unique_relations(
    target: dict[str, RelationDefinition],
    new_relations: Mapping[str, RelationDefinition],
    relation_kind: str,
) -> None:
    duplicated = sorted(name for name in new_relations if name in target)
    if duplicated:
        raise ValueError(f"Rela??es {relation_kind} duplicadas no assembly full: {duplicated}")
    target.update(new_relations)
