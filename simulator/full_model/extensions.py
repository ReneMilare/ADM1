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
# BaseRateModifierHookType: same signature and application as InhibitionHookType, but semantically
# distinct — intended for substrate-specific or structural modifications of existing process rates
# (e.g., hydrolysis reduction due to cell-wall recalcitrance in microalgae).
# Applied BEFORE inhibition hooks so inhibitions act on the already-modified base rate.
BaseRateModifierHookType = Callable[[Mapping[str, float], Mapping[str, float]], dict[str, float]]
ConditionalStoichiometryPatchesType = Mapping[str, Mapping[str, Mapping[str, str]]]


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
    # conditional_stoichiometry_patches: additive patches gated by the presence of another
    # active extension. Shape: {required_extension: {process_name: {state_name: expression}}}.
    # Used when a state only exists if another extension is active, e.g. E9 consuming S_H2S
    # only when E4 (srb) is co-active.
    conditional_stoichiometry_patches: ConditionalStoichiometryPatchesType = field(default_factory=dict)
    acid_base_relations: Mapping[str, RelationDefinition] = field(default_factory=dict)
    gas_transfer_relations: Mapping[str, RelationDefinition] = field(default_factory=dict)
    rate_function: ProcessRateFunction | None = None
    diagnostics_hook: DiagnosticHook | None = None
    validate_hook: AssemblyValidationHook | None = None
    inhibition_hook: InhibitionHookType | None = None
    # base_rate_modifier_hook: multiplicative modifier for existing process rates, applied before
    # inhibition hooks. Returns {process_name: factor}. Used when a substrate type changes the
    # intrinsic rate of a core process (e.g., cell-wall recalcitrance reducing hydrolysis).
    base_rate_modifier_hook: BaseRateModifierHookType | None = None


class FullModelExtension(Protocol):
    name: str
    description: str

    def contribute(self) -> FullModelExtensionContribution: ...
