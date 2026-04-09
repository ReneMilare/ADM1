from __future__ import annotations

import numpy as np
import pytest

from simulator.core.models import CoDigestionBlend, FeedDefinition, InitialState, OperatingConditions, SubstrateFraction
from simulator.core.pyadm1_backend import _build_influent_frame, _build_initial_frame


def test_influent_frame_uses_explicit_sic_instead_of_legacy_proxy() -> None:
    feed = FeedDefinition(
        alkalinity=4.8,
        sic_kmol_m3=0.04,
        flow_rate_m3_day=170.0,
    )
    operating_conditions = OperatingConditions()

    frame = _build_influent_frame(
        time_grid=np.asarray([0.0], dtype=float),
        feed=feed,
        operating_conditions=operating_conditions,
    )

    row = frame.iloc[0]
    assert row["S_IC"] == pytest.approx(0.04)


def test_initial_frame_uses_explicit_sic_instead_of_legacy_proxy(default_feed) -> None:
    initial = InitialState(
        alkalinity=5.1,
        sic_kmol_m3=0.12,
    )

    frame = _build_initial_frame(
        initial_state=initial,
        feed=default_feed,
    )

    row = frame.iloc[0]
    assert row["S_IC"] == pytest.approx(0.12)
    assert row["S_hco3_ion"] < row["S_IC"]
    assert row["S_co2"] == pytest.approx(row["S_IC"] - row["S_hco3_ion"])


def test_codigestion_blend_preserves_explicit_sic_when_all_inputs_define_it() -> None:
    feed_a = FeedDefinition(name="A", sic_kmol_m3=0.04)
    feed_b = FeedDefinition(name="B", sic_kmol_m3=0.10)
    blend = CoDigestionBlend(
        name="AB",
        components=[
            SubstrateFraction(feed=feed_a, volume_fraction=0.25),
            SubstrateFraction(feed=feed_b, volume_fraction=0.75),
        ],
    )

    mixed = blend.blend()
    assert mixed.sic_kmol_m3 == pytest.approx(0.085)
