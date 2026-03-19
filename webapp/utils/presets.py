from __future__ import annotations

from typing import Any

from simulator.core.defaults import make_default_feed, make_default_operating_conditions
from simulator.core.models import FeedDefinition, OperatingConditions
from simulator.design_pipeline import SUBSTRATE_PRESETS

PRESET_LABELS = {preset_id: preset["label"] for preset_id, preset in SUBSTRATE_PRESETS.items()}


def get_substrate_options() -> dict[str, str]:
    return PRESET_LABELS.copy()


def get_preset_bundle(preset_id: str) -> tuple[FeedDefinition, OperatingConditions, str]:
    if preset_id not in SUBSTRATE_PRESETS:
        raise ValueError(f"Unsupported preset '{preset_id}'")
    preset = SUBSTRATE_PRESETS[preset_id]
    return (
        preset["feed"].model_copy(deep=True),
        preset["operating"].model_copy(deep=True),
        str(preset.get("note_link", preset["label"])),
    )


def get_manual_defaults() -> tuple[FeedDefinition, OperatingConditions]:
    return make_default_feed(), make_default_operating_conditions()


def preset_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for preset_id, preset in SUBSTRATE_PRESETS.items():
        rows.append(
            {
                "preset_id": preset_id,
                "label": preset["label"],
                "feed_name": preset["feed"].name,
                "temperature_c": preset["operating"].temperature_c,
                "hrt_days": preset["operating"].hrt_days,
                "volume_m3": preset["operating"].volume_m3,
            }
        )
    return rows
