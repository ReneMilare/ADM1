from __future__ import annotations

from collections.abc import Mapping

from simulator.core.models import FeedDefinition, InitialState, KineticParameters, OperatingConditions
from simulator.full_model.diagnostics import translate_full_profiles
from simulator.full_model.model import FullModelInputs, build_full_inputs, build_full_inputs_from_state_maps

__all__ = ["FullModelInputs", "build_backend_inputs", "build_backend_inputs_from_state_maps", "translate_backend_profiles"]



def build_backend_inputs(
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
    return build_full_inputs(
        operating_conditions=operating_conditions,
        feed=feed,
        initial_state=initial_state,
        parameters=parameters,
        active_extensions=active_extensions,
        extension_parameter_overrides=extension_parameter_overrides,
        initial_state_overrides=initial_state_overrides,
        influent_state_overrides=influent_state_overrides,
    )



def build_backend_inputs_from_state_maps(
    *,
    operating_conditions: OperatingConditions,
    parameters: KineticParameters,
    influent_values: Mapping[str, float],
    initial_values: Mapping[str, float],
    flow_rate_m3_day: float | None = None,
    active_extensions: list[str] | tuple[str, ...] | None = None,
    extension_parameter_overrides: Mapping[str, float] | None = None,
) -> FullModelInputs:
    return build_full_inputs_from_state_maps(
        operating_conditions=operating_conditions,
        parameters=parameters,
        influent_values=influent_values,
        initial_values=initial_values,
        flow_rate_m3_day=flow_rate_m3_day,
        active_extensions=active_extensions,
        extension_parameter_overrides=extension_parameter_overrides,
    )



def translate_backend_profiles(*, full_state_matrix, parameter_values, assembly):
    return translate_full_profiles(full_state_matrix=full_state_matrix, parameter_values=parameter_values, assembly=assembly)
