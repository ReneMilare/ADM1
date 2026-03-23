from __future__ import annotations

from simulator.full_model.assembly import FullModelAssembly, build_full_model_assembly
from simulator.full_model.extensions import FullModelExtension
from simulator.full_model.pilot_tracer_extension import PILOT_TRACER_EXTENSION
from simulator.full_model.lactate_extension import LACTATE_EXTENSION
from simulator.full_model.ethanol_extension import ETHANOL_EXTENSION
from simulator.full_model.phenolics_extension import PHENOLICS_EXTENSION
from simulator.full_model.lcfa_extension import LCFA_EXTENSION
from simulator.full_model.srb_extension import SRB_EXTENSION
from simulator.full_model.multi_population_extension import MULTI_POPULATION_EXTENSION
from simulator.full_model.phosphorus_extension import PHOSPHORUS_EXTENSION
from simulator.full_model.iron_extension import IRON_EXTENSION
from simulator.full_model.microalgae_extension import MICROALGAE_EXTENSION
from simulator.full_model.syngas_extension import SYNGAS_EXTENSION
from simulator.full_model.trace_elements_extension import TRACE_ELEMENTS_EXTENSION

_REGISTERED_EXTENSIONS: dict[str, FullModelExtension] = {
    PILOT_TRACER_EXTENSION.name: PILOT_TRACER_EXTENSION,
    LACTATE_EXTENSION.name: LACTATE_EXTENSION,
    ETHANOL_EXTENSION.name: ETHANOL_EXTENSION,
    PHENOLICS_EXTENSION.name: PHENOLICS_EXTENSION,
    LCFA_EXTENSION.name: LCFA_EXTENSION,
    SRB_EXTENSION.name: SRB_EXTENSION,
    MULTI_POPULATION_EXTENSION.name: MULTI_POPULATION_EXTENSION,
    PHOSPHORUS_EXTENSION.name: PHOSPHORUS_EXTENSION,
    IRON_EXTENSION.name: IRON_EXTENSION,
    MICROALGAE_EXTENSION.name: MICROALGAE_EXTENSION,
    SYNGAS_EXTENSION.name: SYNGAS_EXTENSION,
    TRACE_ELEMENTS_EXTENSION.name: TRACE_ELEMENTS_EXTENSION,
}


def list_registered_extensions() -> tuple[str, ...]:
    return tuple(sorted(_REGISTERED_EXTENSIONS))


def resolve_full_model_assembly(active_extensions: list[str] | tuple[str, ...] | None = None) -> FullModelAssembly:
    requested = tuple(dict.fromkeys(active_extensions or ()))
    unknown = sorted(name for name in requested if name not in _REGISTERED_EXTENSIONS)
    if unknown:
        raise ValueError(f"Extensões full desconhecidas: {unknown}")
    extensions = tuple(_REGISTERED_EXTENSIONS[name] for name in requested)
    return build_full_model_assembly(extensions=extensions, extension_names=requested)
