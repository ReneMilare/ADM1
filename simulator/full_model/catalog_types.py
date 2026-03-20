from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

StateRole = Literal["dynamic", "algebraic", "pseudo_state"]
ProcessFamily = Literal["biochemical", "acid_base", "gas_transfer"]
ParameterGroup = Literal["reference", "stoichiometric", "biochemical", "physicochemical", "operating"]
ParameterClassification = Literal["canonical", "derived", "calibrated", "provisional"]


@dataclass(frozen=True, slots=True)
class StateDefinition:
    name: str
    description: str
    unit: str
    phase: str
    domain: str
    role: StateRole
    cod_role: str
    elemental_proxy: str | None
    source: str
    pyadm1_name: str | None = None
    result_alias: str | None = None
    notes: str = ""


@dataclass(frozen=True, slots=True)
class ProcessDefinition:
    name: str
    vendor_symbol: str
    family: ProcessFamily
    description: str
    rate_expression: str
    affected_states: tuple[str, ...]
    parameters: tuple[str, ...]
    inhibitions: tuple[str, ...]
    source: str
    notes: str = ""


@dataclass(frozen=True, slots=True)
class ParameterDefinition:
    name: str
    value: float
    unit: str
    group: ParameterGroup
    classification: ParameterClassification
    description: str
    source: str
    notes: str = ""


@dataclass(frozen=True, slots=True)
class RelationDefinition:
    process_name: str
    expression: str
    affected_states: tuple[str, ...]
    source: str
    notes: str = ""
