from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, Mapping, Protocol

import numpy as np

from simulator.full_model.catalog_types import ParameterDefinition, ProcessDefinition, RelationDefinition, StateDefinition

if TYPE_CHECKING:
    import numpy as np

    from simulator.full_model.assembly import FullModelAssembly


ProcessRateFunction = Callable[[Mapping[str, float], Mapping[str, float]], Mapping[str, float]]
DiagnosticHook = Callable[[np.ndarray, "FullModelAssembly", Mapping[str, float]], dict[str, list[float]]]
AssemblyValidationHook = Callable[["FullModelAssembly"], None]
# InhibitionHookType returns {process_name: float} where each float is a multiplicative factor (0–1)
# applied to the named core or extension process rate after all rates are computed.
# Use this to implement cross-process inhibition (e.g., H2S on methanogenesis, LCFA contact inhibition).
InhibitionHookType = Callable[[Mapping[str, float], Mapping[str, float]], dict[str, float]]


@dataclass(frozen=True, slots=True)
class FullModelExtensionContribution:
    states: tuple[StateDefinition, ...] = ()
    processes: tuple[ProcessDefinition, ...] = ()
    parameters: tuple[ParameterDefinition, ...] = ()
    biochemical_stoichiometry_rows: Mapping[str, Mapping[str, str]] = field(default_factory=dict)
    # stoichiometry_patches: additive modifications to existing core stoichiometry rows.
    # Each entry {process_name: {state_name: expression}} adds new state columns to an
    # existing row without replacing it. Used by E6/E10 to add S_lac/S_et to rho_5_uptake_sugars.
    stoichiometry_patches: Mapping[str, Mapping[str, str]] = field(default_factory=dict)
    acid_base_relations: Mapping[str, RelationDefinition] = field(default_factory=dict)
    gas_transfer_relations: Mapping[str, RelationDefinition] = field(default_factory=dict)
    rate_function: ProcessRateFunction | None = None
    diagnostics_hook: DiagnosticHook | None = None
    validate_hook: AssemblyValidationHook | None = None
    inhibition_hook: InhibitionHookType | None = None


class FullModelExtension(Protocol):
    name: str
    description: str

    def contribute(self) -> FullModelExtensionContribution: ...
