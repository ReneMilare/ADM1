from __future__ import annotations

from simulator.full_model.assembly import FullModelAssembly, build_full_model_assembly
from simulator.full_model.extensions import FullModelExtension
from simulator.full_model.pilot_tracer_extension import PILOT_TRACER_EXTENSION

_REGISTERED_EXTENSIONS: dict[str, FullModelExtension] = {
    PILOT_TRACER_EXTENSION.name: PILOT_TRACER_EXTENSION,
}


def list_registered_extensions() -> tuple[str, ...]:
    return tuple(sorted(_REGISTERED_EXTENSIONS))


def resolve_full_model_assembly(active_extensions: list[str] | tuple[str, ...] | None = None) -> FullModelAssembly:
    requested = tuple(dict.fromkeys(active_extensions or ()))
    unknown = sorted(name for name in requested if name not in _REGISTERED_EXTENSIONS)
    if unknown:
        raise ValueError(f"Extens?es full desconhecidas: {unknown}")
    extensions = tuple(_REGISTERED_EXTENSIONS[name] for name in requested)
    return build_full_model_assembly(extensions=extensions, extension_names=requested)
