from __future__ import annotations

from simulator.core.defaults import (
    make_default_feed,
    make_default_initial_state,
    make_default_kinetics,
    make_default_operating_conditions,
)
from simulator.full_model.model import build_full_inputs


def test_build_full_inputs_ignores_none_in_state_overrides() -> None:
    feed = make_default_feed()
    operating = make_default_operating_conditions()
    initial = make_default_initial_state(feed)
    parameters = make_default_kinetics()

    inputs = build_full_inputs(
        operating_conditions=operating,
        feed=feed,
        initial_state=initial,
        parameters=parameters,
        influent_state_overrides={"X_ch": 12.34, "S_IN": None, "ph": None},
        initial_state_overrides={"S_IN": None},
    )

    assert inputs.influent_values["X_ch"] == 12.34
    assert inputs.influent_values["S_IN"] >= 0.0
    assert inputs.dynamic_influent[inputs.assembly.dynamic_state_index["X_ch"]] == 12.34
