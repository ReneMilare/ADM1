from __future__ import annotations

import math

import numpy as np
import pytest

from simulator.core.defaults import make_default_feed, make_default_initial_state, make_default_kinetics
from simulator.core.models import FeedDefinition, InitialState, OperatingConditions
from simulator.core.pyadm1_backend import (
    FEED_GROUPS,
    INITIAL_GROUPS,
    _build_influent_frame,
    _build_initial_frame,
    _load_template_row,
)
from simulator.full_model.model import build_full_inputs

PARTICULATE = ("X_xc", "X_ch", "X_pr", "X_li", "X_I")
SOLUBLE_REMAINDER = ("S_su", "S_aa", "S_fa", "S_va", "S_bu", "S_I")
ACIDOGENS = ("X_su", "X_aa", "X_fa", "X_c4")


def _rows(feed: FeedDefinition, initial: InitialState, full: bool) -> tuple[dict[str, float], dict[str, float]]:
    operating = OperatingConditions()
    if full:
        inputs = build_full_inputs(
            operating_conditions=operating,
            feed=feed,
            initial_state=initial,
            parameters=make_default_kinetics(),
        )
        return inputs.influent_values, inputs.initial_values
    influent = _build_influent_frame(time_grid=np.asarray([0.0, 1.0]), feed=feed, operating_conditions=operating)
    assert influent.iloc[0].drop("time").equals(influent.iloc[1].drop("time"))
    return influent.iloc[0].to_dict(), _build_initial_frame(initial_state=initial, feed=feed).iloc[0].to_dict()


def _assert_absolute(row: dict[str, float], state: FeedDefinition | InitialState) -> None:
    assert math.fsum(row[name] for name in PARTICULATE) - state.particulate_cod == pytest.approx(0.0, abs=1e-12)
    soluble = math.fsum(row[name] for name in (*SOLUBLE_REMAINDER, "S_ac", "S_pro"))
    assert soluble - state.soluble_cod == pytest.approx(0.0, abs=1e-12)
    assert row["S_ac"] == pytest.approx(state.acetate, abs=1e-12)
    assert row["S_pro"] == pytest.approx(state.propionate, abs=1e-12)
    assert row["S_h2"] == pytest.approx(state.hydrogen, abs=1e-12)
    assert row["S_IN"] * 14.0 - state.inorganic_nitrogen == pytest.approx(0.0, abs=1e-12)
    assert row["S_nh3"] + row["S_nh4_ion"] - row["S_IN"] == pytest.approx(0.0, abs=1e-12)
    assert 0.0 <= row["S_nh3"] <= row["S_IN"]
    for acid in ("va", "bu", "pro", "ac"):
        assert 0.0 <= row[f"S_{acid}_ion"] <= row[f"S_{acid}"]


@pytest.mark.parametrize("full", [False, True], ids=["pyadm1", "full"])
def test_default_feed_and_initial_are_absolute(full: bool) -> None:
    feed = make_default_feed()
    initial = make_default_initial_state(feed)
    influent, initial_row = _rows(feed, initial, full)
    _assert_absolute(influent, feed)
    _assert_absolute(initial_row, initial)
    assert math.fsum(initial_row[name] for name in ACIDOGENS) == pytest.approx(initial.acidogens)
    for field, column in (("propionate_biomass", "X_pro"), ("acetoclastic_biomass", "X_ac"), ("hydrogenotrophic_biomass", "X_h2")):
        assert initial_row[column] == pytest.approx(getattr(initial, field))
    # Biomass has separate initial-state fields and is outside the legacy particulate group.
    template = _load_template_row("digester_influent.csv")
    for column in (*ACIDOGENS, "X_pro", "X_ac", "X_h2"):
        assert influent[column] == template[column]


@pytest.mark.parametrize("full", [False, True], ids=["pyadm1", "full"])
def test_nondefault_feed_and_initial_are_absolute(full: bool) -> None:
    feed = FeedDefinition(particulate_cod=30.0, soluble_cod=9.0, acetate=2.0, propionate=1.0, hydrogen=0.03, inorganic_nitrogen=2.8)
    initial = InitialState(particulate_cod=22.0, soluble_cod=8.0, acetate=1.5, propionate=0.4, hydrogen=0.02, inorganic_nitrogen=0.7, acidogens=3.0, propionate_biomass=0.6, acetoclastic_biomass=1.4, hydrogenotrophic_biomass=0.8)
    influent, initial_row = _rows(feed, initial, full)
    _assert_absolute(influent, feed)
    _assert_absolute(initial_row, initial)
    assert math.fsum(initial_row[name] for name in ACIDOGENS) == pytest.approx(3.0)


@pytest.mark.parametrize("initial", [False, True], ids=["feed", "initial"])
@pytest.mark.parametrize("columns", [PARTICULATE, SOLUBLE_REMAINDER], ids=["particulate", "soluble"])
def test_distribution_preserves_template_fractions(initial: bool, columns: tuple[str, ...]) -> None:
    feed = make_default_feed()
    rows = _rows(feed, make_default_initial_state(feed), False)
    row = rows[int(initial)]
    template = _load_template_row("digester_initial.csv" if initial else "digester_influent.csv")
    total = math.fsum(row[name] for name in columns)
    template_total = math.fsum(template[name] for name in columns)
    for name in columns:
        assert row[name] / total == pytest.approx(template[name] / template_total, abs=1e-12)


@pytest.mark.parametrize("initial", [False, True], ids=["feed", "initial"])
def test_zero_template_groups_use_normalized_fallbacks(monkeypatch: pytest.MonkeyPatch, initial: bool) -> None:
    from simulator.core import pyadm1_backend

    loader = pyadm1_backend._load_template_row

    def zero_groups(filename: str) -> dict[str, float]:
        row = dict(loader(filename))
        for name in (*PARTICULATE, *SOLUBLE_REMAINDER, *ACIDOGENS):
            row[name] = 0.0
        return row

    monkeypatch.setattr(pyadm1_backend, "_load_template_row", zero_groups)
    feed = make_default_feed()
    state = make_default_initial_state(feed) if initial else feed
    row = _rows(feed, make_default_initial_state(feed), False)[int(initial)]
    _assert_absolute(row, state)
    for name in PARTICULATE:
        assert row[name] == pytest.approx(state.particulate_cod / len(PARTICULATE))
    groups = INITIAL_GROUPS if initial else FEED_GROUPS
    weights = groups["soluble_cod"][1]
    remaining = state.soluble_cod - state.acetate - state.propionate
    for name in SOLUBLE_REMAINDER:
        assert row[name] == pytest.approx(remaining * weights.get(name, 0.0) / sum(weights.values()))
    if initial:
        weights = INITIAL_GROUPS["acidogens"][1]
        for name in ACIDOGENS:
            assert row[name] == pytest.approx(state.acidogens * weights[name] / sum(weights.values()))


@pytest.mark.parametrize("initial", [False, True], ids=["feed", "initial"])
def test_zero_nitrogen_hydrogen_and_soluble_remainder(initial: bool) -> None:
    feed = FeedDefinition(soluble_cod=0.85, inorganic_nitrogen=0.0, hydrogen=0.0)
    state = InitialState(soluble_cod=1.8, inorganic_nitrogen=0.0, hydrogen=0.0)
    row = _rows(feed, state, False)[int(initial)]
    _assert_absolute(row, state if initial else feed)
    assert math.fsum(row[name] for name in SOLUBLE_REMAINDER) == pytest.approx(0.0, abs=1e-12)
    assert row["S_nh3"] == row["S_nh4_ion"] == 0.0


@pytest.mark.parametrize("initial", [False, True], ids=["feed", "initial"])
@pytest.mark.parametrize("sic", [None, 0.0, 0.08])
def test_legacy_alkalinity_and_explicit_sic_are_preserved(initial: bool, sic: float | None) -> None:
    feed = FeedDefinition(alkalinity=9.6, sic_kmol_m3=sic)
    state = InitialState(alkalinity=7.0, sic_kmol_m3=sic)
    row = _rows(feed, state, False)[int(initial)]
    template = _load_template_row("digester_initial.csv" if initial else "digester_influent.csv")
    default = make_default_initial_state() if initial else make_default_feed()
    requested = state if initial else feed
    # Legacy alkalinity is absolute: 17 mol HCO3- per unit (reduced-model scale).
    expected = requested.alkalinity * 17.0 / 1000.0 if sic is None else sic
    assert row["S_IC"] == pytest.approx(expected)
    if sic is not None:
        assert row["S_hco3_ion"] == pytest.approx(template["S_hco3_ion"] * sic / template["S_IC"])
        # Initial CO2 retains the existing closure after explicit S_IC is applied.
        expected_co2 = max(sic - row["S_hco3_ion"], 1e-9) if initial else template["S_co2"] * sic / template["S_IC"]
        assert row["S_co2"] == pytest.approx(expected_co2)


@pytest.mark.parametrize("initial", [False, True], ids=["feed", "initial"])
@pytest.mark.parametrize("quantity", ["particulate_cod", "soluble_cod", "acetate", "propionate", "hydrogen", "inorganic_nitrogen"])
def test_each_concentration_is_absolute(initial: bool, quantity: str) -> None:
    feed = make_default_feed()
    state = make_default_initial_state(feed) if initial else feed
    row = _rows(feed, make_default_initial_state(feed), False)[int(initial)]
    actual = {
        "particulate_cod": math.fsum(row[name] for name in PARTICULATE),
        "soluble_cod": math.fsum(row[name] for name in (*SOLUBLE_REMAINDER, "S_ac", "S_pro")),
        "acetate": row["S_ac"],
        "propionate": row["S_pro"],
        "hydrogen": row["S_h2"],
        "inorganic_nitrogen": 14.0 * row["S_IN"],
    }[quantity]
    assert actual == pytest.approx(getattr(state, quantity), abs=1e-12)


def test_initial_soluble_cod_cannot_be_less_than_its_vfas() -> None:
    with pytest.raises(ValueError, match="soluble_cod"):
        _build_initial_frame(initial_state=InitialState(soluble_cod=0.5), feed=make_default_feed())


def test_initial_acidogen_distribution_preserves_template_fractions() -> None:
    feed = make_default_feed()
    initial = make_default_initial_state(feed)
    row = _rows(feed, initial, False)[1]
    template = _load_template_row("digester_initial.csv")
    template_total = math.fsum(template[name] for name in ACIDOGENS)
    for name in ACIDOGENS:
        assert row[name] / initial.acidogens == pytest.approx(template[name] / template_total, abs=1e-12)


@pytest.mark.parametrize("initial", [False, True], ids=["feed", "initial"])
def test_speciation_preserves_template_fraction_and_gas_hydrogen(initial: bool) -> None:
    feed = make_default_feed()
    row = _rows(feed, make_default_initial_state(feed), False)[int(initial)]
    template = _load_template_row("digester_initial.csv" if initial else "digester_influent.csv")
    assert row["S_nh3"] / row["S_IN"] == pytest.approx(template["S_nh3"] / template["S_IN"])
    assert row["S_gas_h2"] == template["S_gas_h2"]
