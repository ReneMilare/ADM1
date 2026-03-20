from __future__ import annotations

import math
import shutil
import tempfile
from pathlib import Path

import pytest
from pydantic import ValidationError

from simulator.core.defaults import make_default_simulation_config
from simulator.core.models import CoDigestionBlend, FeedDefinition, SubstrateFraction
from simulator.design_pipeline import ADM1DesignPipeline, CODIGESTION_PRESETS, SUBSTRATE_PRESETS
from simulator.scenario_store import ScenarioStore
from simulator.service import ADM1SimulationService

WORKSPACE_TMP = Path("simulator") / "tests" / ".tmp"
WORKSPACE_TMP.mkdir(parents=True, exist_ok=True)


def test_blend_fractions_must_sum_to_one() -> None:
    with pytest.raises(ValidationError):
        CoDigestionBlend(
            components=[
                SubstrateFraction(feed=FeedDefinition(name="A"), volume_fraction=0.7),
                SubstrateFraction(feed=FeedDefinition(name="B"), volume_fraction=0.2),
            ]
        )


def test_blend_two_substrates() -> None:
    feed_a = FeedDefinition(name="A", particulate_cod=10.0, soluble_cod=4.0, acetate=0.2, propionate=0.1, inorganic_nitrogen=1.0, alkalinity=4.0, ph=7.0)
    feed_b = FeedDefinition(name="B", particulate_cod=6.0, soluble_cod=8.0, acetate=0.6, propionate=0.3, inorganic_nitrogen=2.0, alkalinity=5.0, ph=6.5)
    blend = CoDigestionBlend(
        name="AB",
        components=[SubstrateFraction(feed=feed_a, volume_fraction=0.5), SubstrateFraction(feed=feed_b, volume_fraction=0.5)],
    )
    mixed = blend.blend()
    assert mixed.particulate_cod == pytest.approx(8.0)
    assert mixed.soluble_cod == pytest.approx(6.0)
    assert mixed.inorganic_nitrogen == pytest.approx(1.5)


def test_blend_ph_logarithmic() -> None:
    feed_a = FeedDefinition(name="A", ph=6.0)
    feed_b = FeedDefinition(name="B", ph=8.0)
    blend = CoDigestionBlend(
        name="AB",
        components=[SubstrateFraction(feed=feed_a, volume_fraction=0.5), SubstrateFraction(feed=feed_b, volume_fraction=0.5)],
    )
    mixed = blend.blend()
    expected = -math.log10(0.5 * 10 ** (-6.0) + 0.5 * 10 ** (-8.0))
    assert mixed.ph == pytest.approx(expected)
    assert mixed.ph != pytest.approx(7.0)


def test_cn_ratio_calculation() -> None:
    blend = CODIGESTION_PRESETS["lodo_mais_alimentar"]["blend"]
    mixed = blend.blend()
    expected = (mixed.particulate_cod + mixed.soluble_cod + mixed.acetate + mixed.propionate) / mixed.inorganic_nitrogen
    assert blend.cn_ratio() == pytest.approx(expected)


def test_codigestion_preset_resolution() -> None:
    pipeline = ADM1DesignPipeline()
    preset_id, preset = pipeline._resolve_substrate("lodo_mais_alimentar")
    assert preset_id == "lodo_mais_alimentar"
    assert preset["blend"].name == "Lodo + Alimentar 70/30"


def test_codigestion_vs_single_substrate() -> None:
    service = ADM1SimulationService(store=ScenarioStore(WORKSPACE_TMP))
    simulation = make_default_simulation_config().model_copy(update={"duration_days": 25.0, "evaluation_points": 81, "persist": False, "backend": "reduced"})
    sludge = service.simulate("cstr", feed=SUBSTRATE_PRESETS["lodo_de_esgoto"]["feed"], simulation=simulation)
    blend = service.simulate("cstr", blend=CODIGESTION_PRESETS["lodo_mais_alimentar"]["blend"], simulation=simulation)
    assert blend.summary.methane_cumulative_m3 > sludge.summary.methane_cumulative_m3


def test_codigestion_metadata_persisted() -> None:
    tmpdir = Path(tempfile.mkdtemp(dir=WORKSPACE_TMP))
    try:
        service = ADM1SimulationService(store=ScenarioStore(tmpdir))
        simulation = make_default_simulation_config().model_copy(update={"duration_days": 15.0, "evaluation_points": 61, "persist": False, "backend": "reduced"})
        result = service.simulate("cstr", blend=CODIGESTION_PRESETS["alimentar_mais_agricola"]["blend"], simulation=simulation)
        assert result.metadata["codigestion"] is True
        assert result.metadata["blend_name"] == "Alimentar + Agrícola 50/50"
        assert len(result.metadata["blend_components"]) == 2
        assert result.summary.cn_ratio is not None
        assert result.summary.blend_components is not None
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _make_test_blend() -> CoDigestionBlend:
    feed_a = FeedDefinition(name="A", particulate_cod=14.0, soluble_cod=5.5, acetate=0.6, propionate=0.25, inorganic_nitrogen=1.3, alkalinity=4.8, ph=7.1)
    feed_b = FeedDefinition(name="B", particulate_cod=11.5, soluble_cod=7.2, acetate=1.15, propionate=0.55, inorganic_nitrogen=1.45, alkalinity=4.4, ph=6.95)
    return CoDigestionBlend(
        name="Test Blend",
        components=[
            SubstrateFraction(feed=feed_a, volume_fraction=0.6),
            SubstrateFraction(feed=feed_b, volume_fraction=0.4),
        ],
    )


def test_steady_state_with_blend() -> None:
    """Verifica que steady_state() propaga blend para simulate()."""
    service = ADM1SimulationService(store=ScenarioStore(WORKSPACE_TMP))
    blend = _make_test_blend()
    result = service.steady_state("plug_flow", blend=blend, duration_days=25.0)
    assert result["simulation_id"]
    stored = service.get_result(str(result["simulation_id"]))
    assert stored.metadata.get("codigestion") is True
    assert stored.metadata.get("blend_name") == "Test Blend"


def test_compare_reactors_with_blend() -> None:
    """Verifica que compare_reactors() propaga blend."""
    service = ADM1SimulationService(store=ScenarioStore(WORKSPACE_TMP))
    blend = _make_test_blend()
    simulation = make_default_simulation_config().model_copy(update={"duration_days": 15.0, "evaluation_points": 61, "persist": False, "backend": "reduced"})
    ref = service.simulate("uasb", blend=blend, simulation=simulation)
    comparison = service.compare_reactors(["uasb"], blend=blend, simulation=simulation)
    assert comparison.scenarios[0].methane_final_m3_day == pytest.approx(ref.summary.methane_final_m3_day, rel=1e-3)


def test_sensitivity_with_blend() -> None:
    """Verifica que sensitivity_analysis() propaga blend."""
    service = ADM1SimulationService(store=ScenarioStore(WORKSPACE_TMP))
    blend = _make_test_blend()
    simulation = make_default_simulation_config().model_copy(update={"duration_days": 15.0, "evaluation_points": 61, "persist": False, "backend": "reduced"})
    ref = service.simulate("uasb", blend=blend, simulation=simulation)
    result = service.sensitivity_analysis("kinetics.k_hyd", reactor="uasb", blend=blend, simulation=simulation)
    assert result.baseline_objective == pytest.approx(ref.summary.methane_final_m3_day, rel=1e-3)
