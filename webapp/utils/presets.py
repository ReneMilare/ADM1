from __future__ import annotations

from typing import Any

from simulator.core.defaults import make_default_feed, make_default_operating_conditions
from simulator.core.models import CoDigestionBlend, FeedDefinition, OperatingConditions
from simulator.design_pipeline import CODIGESTION_PRESETS, SUBSTRATE_PRESETS

PRESET_LABELS = {preset_id: preset["label"] for preset_id, preset in SUBSTRATE_PRESETS.items()}
CODIGESTION_PRESET_LABELS = {
    preset_id: f"{preset['label']} (co-digestão)"
    for preset_id, preset in CODIGESTION_PRESETS.items()
}


def get_substrate_options() -> dict[str, str]:
    options = PRESET_LABELS.copy()
    options.update(CODIGESTION_PRESET_LABELS)
    return options


def get_preset_bundle(preset_id: str) -> tuple[FeedDefinition, OperatingConditions, str]:
    if preset_id in SUBSTRATE_PRESETS:
        preset = SUBSTRATE_PRESETS[preset_id]
        return (
            preset["feed"].model_copy(deep=True),
            preset["operating"].model_copy(deep=True),
            str(preset.get("note_link", preset["label"])),
        )
    if preset_id in CODIGESTION_PRESETS:
        preset = CODIGESTION_PRESETS[preset_id]
        blend: CoDigestionBlend = preset["blend"]
        return (
            blend.blend().model_copy(deep=True),
            preset["operating"].model_copy(deep=True),
            str(preset.get("note_link", preset["label"])),
        )
    raise ValueError(f"Unsupported preset '{preset_id}'")


def get_codigestion_blend(preset_id: str) -> CoDigestionBlend | None:
    """Return the CoDigestionBlend for a co-digestion preset, or None if not applicable."""
    if preset_id in CODIGESTION_PRESETS:
        return CODIGESTION_PRESETS[preset_id]["blend"]
    return None


def get_manual_defaults() -> tuple[FeedDefinition, OperatingConditions]:
    return make_default_feed(), make_default_operating_conditions()


def preset_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for preset_id, preset in SUBSTRATE_PRESETS.items():
        rows.append(
            {
                "preset_id": preset_id,
                "label": preset["label"],
                "tipo": "simples",
                "feed_name": preset["feed"].name,
                "temperature_c": preset["operating"].temperature_c,
                "hrt_days": preset["operating"].hrt_days,
                "volume_m3": preset["operating"].volume_m3,
            }
        )
    for preset_id, preset in CODIGESTION_PRESETS.items():
        blend: CoDigestionBlend = preset["blend"]
        blended = blend.blend()
        rows.append(
            {
                "preset_id": preset_id,
                "label": f"{preset['label']} (co-digestão)",
                "tipo": "co-digestão",
                "feed_name": blended.name,
                "temperature_c": preset["operating"].temperature_c,
                "hrt_days": preset["operating"].hrt_days,
                "volume_m3": preset["operating"].volume_m3,
            }
        )
    return rows
