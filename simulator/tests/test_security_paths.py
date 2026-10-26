from __future__ import annotations

import pytest

from simulator.core.models import FeedDefinition, KineticParameters, OperatingConditions, ReactorConfig
from simulator.design_pipeline import ADM1DesignPipeline, _normalize_key, _slugify
from simulator.service import ADM1SimulationService


@pytest.mark.parametrize(
    ("title", "expected"),
    [("/tmp/x", "tmp_x"), ("../../x", "x"), ("..", "note"), ("", "note"), ("Estudo Normal", "estudo_normal")],
)
def test_note_slug_is_safe(title: str, expected: str) -> None:
    assert _slugify(title) == expected
    assert len(_slugify("x" * 200)) == 120
    assert _normalize_key("a-b") == "a_b"


@pytest.mark.parametrize("title", ["/tmp/x", "../../x", "..", "", "Estudo Normal"])
def test_note_is_persisted_inside_root(tmp_path, monkeypatch, title: str) -> None:
    monkeypatch.setattr("simulator.design_pipeline._render_note", lambda **kwargs: "note")
    pipeline = ADM1DesignPipeline(note_root=tmp_path / "notes")
    path = pipeline._write_note(
        preset={"label": "Test"}, design_goal="balanced", backend="auto", operating=OperatingConditions(),
        scored_candidates=[], recommended={}, note_title=title,
    )
    assert path.parent == pipeline.note_root.resolve()
    assert path.read_text(encoding="utf-8") == "note"


def test_note_rejects_symlink_outside_root(tmp_path, monkeypatch) -> None:
    root = tmp_path / "notes"
    root.mkdir()
    (root / "escape.md").symlink_to(tmp_path / "outside.md")
    monkeypatch.setattr("simulator.design_pipeline._render_note", lambda **kwargs: "note")
    pipeline = ADM1DesignPipeline(note_root=root)
    with pytest.raises(ValueError, match="inside the note root"):
        pipeline._write_note(preset={}, design_goal="balanced", backend="auto", operating=OperatingConditions(),
                             scored_candidates=[], recommended={}, note_title="escape")
    assert not (tmp_path / "outside.md").exists()


@pytest.mark.parametrize("path", ["kinetics.__class__", "kinetics..k_hyd", "kinetics._private"])
def test_parameter_path_rejects_private_or_empty_segments(path: str) -> None:
    service = ADM1SimulationService()
    with pytest.raises(ValueError):
        service._resolve_target(path, ReactorConfig(), OperatingConditions(), FeedDefinition(), KineticParameters())


def test_parameter_path_accepts_public_parameter() -> None:
    service = ADM1SimulationService()
    kinetics = KineticParameters()
    target, attribute = service._resolve_target(
        "kinetics.k_hyd", ReactorConfig(), OperatingConditions(), FeedDefinition(), kinetics
    )
    assert target is kinetics
    assert attribute == "k_hyd"
