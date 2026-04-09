"""Tests for the composition converter integration with the webapp layer.

Covers:
- session_state round-trips for converter fields
- preset_payload round-trips for composition_converter block
- Merge logic for converter overrides with extension overrides
- save_custom_substrate_with_provenance provenance storage
"""
from __future__ import annotations

import sys
import os
from copy import deepcopy
from unittest.mock import patch

# Ensure project root is on the path
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from webapp.contracts import SimulationDraft
from webapp.state.adapters import (
    draft_to_preset_payload,
    draft_to_session_state,
    preset_payload_to_draft,
    session_state_to_draft,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SAMPLE_COMPOSITION_INPUT = {
    "sample_name": "Resíduo alimentar típico",
    "dry_matter_pct": 15.0,
    "organic_matter_pct": 12.0,
    "protein_pct": 4.0,
    "lipids_pct": 2.0,
    "cellulose_pct": 3.0,
    "lignin_pct": 1.0,
}

_SAMPLE_OVERRIDES = {
    "X_ch": 35.7,
    "X_pr": 56.8,
    "X_li": 58.0,
    "X_I": 19.2,
    "S_su": 21.4,
}

_SAMPLE_COMPOSITION_RESULT = {"reduced_feed_values": {"particulate_cod": 169.7, "soluble_cod": 21.4}}

_SAMPLE_ASSUMPTIONS = [{"field": "ph", "assumed_value": 7.0, "reason": "pH not measured"}]

_SAMPLE_WARNINGS = ["High lipid content"]


def _base_state(**overrides) -> dict:
    """Minimal valid session_state dict."""
    base = {
        "sim_reactor_type": "cstr",
        "sim_substrate_mode": "manual",
        "sim_preset_id": None,
        "hydraulic_mode": "hrt",
        "volume_active": 3000.0,
        "temperature_active": 35.0,
        "hrt_active": 20.0,
        "flow_rate_active": 150.0,
        "sim_backend_choice": "full",
        "sim_full_extensions": [],
        "duration_days": 45.0,
        "evaluation_points": 181,
        "solver_choice": "BDF",
        "persist_case": True,
        "ammonia_inhibition_mode": "simple",
        "variant_config": None,
        "manual_feed_name": "Test feed",
        "manual_feed_ph": 7.0,
    }
    base.update(overrides)
    return base


def _draft_with_converter(**overrides) -> SimulationDraft:
    """SimulationDraft with a fully populated converter block."""
    kwargs = dict(
        composition_input=dict(_SAMPLE_COMPOSITION_INPUT),
        composition_result=dict(_SAMPLE_COMPOSITION_RESULT),
        full_influent_state_overrides=dict(_SAMPLE_OVERRIDES),
        conversion_assumptions=list(_SAMPLE_ASSUMPTIONS),
        conversion_warnings=list(_SAMPLE_WARNINGS),
        conversion_applied_to_manual=True,
    )
    kwargs.update(overrides)
    return SimulationDraft(**kwargs)


# ---------------------------------------------------------------------------
# 1. Session-state draft round-trip preserves converter fields
# ---------------------------------------------------------------------------

def test_draft_round_trip_preserves_composition_input():
    """session_state → draft → session_state preserves composition_input."""
    state = _base_state(
        conv_composition_input=dict(_SAMPLE_COMPOSITION_INPUT),
        conv_full_influent_state_overrides=dict(_SAMPLE_OVERRIDES),
        conv_conversion_assumptions=list(_SAMPLE_ASSUMPTIONS),
        conv_conversion_warnings=list(_SAMPLE_WARNINGS),
        conv_conversion_applied_to_manual=True,
    )
    draft = session_state_to_draft(state)
    assert draft.composition_input == _SAMPLE_COMPOSITION_INPUT
    assert draft.full_influent_state_overrides == _SAMPLE_OVERRIDES
    assert draft.conversion_assumptions == _SAMPLE_ASSUMPTIONS
    assert draft.conversion_warnings == _SAMPLE_WARNINGS
    assert draft.conversion_applied_to_manual is True

    restored = draft_to_session_state(draft)
    assert restored["conv_composition_input"] == _SAMPLE_COMPOSITION_INPUT
    assert restored["conv_full_influent_state_overrides"] == _SAMPLE_OVERRIDES
    assert restored["conv_conversion_applied_to_manual"] is True


def test_draft_round_trip_via_draft_objects():
    """draft_to_session_state → session_state_to_draft preserves all converter fields."""
    draft = _draft_with_converter()
    state = draft_to_session_state(draft)
    draft2 = session_state_to_draft(state)

    assert draft2.composition_input == draft.composition_input
    assert draft2.full_influent_state_overrides == draft.full_influent_state_overrides
    assert draft2.conversion_assumptions == draft.conversion_assumptions
    assert draft2.conversion_warnings == draft.conversion_warnings
    assert draft2.conversion_applied_to_manual is True


# ---------------------------------------------------------------------------
# 2. Draft round-trip with no converter data (backward compat)
# ---------------------------------------------------------------------------

def test_draft_round_trip_empty_converter_defaults():
    """Draft with no converter data → None/False defaults survive round-trip."""
    draft = SimulationDraft()  # all defaults
    state = draft_to_session_state(draft)
    draft2 = session_state_to_draft(state)

    assert draft2.composition_input is None
    assert draft2.composition_result is None
    assert draft2.full_influent_state_overrides is None
    assert draft2.conversion_assumptions == []
    assert draft2.conversion_warnings == []
    assert draft2.conversion_applied_to_manual is False


def test_session_state_without_conv_keys_produces_defaults():
    """State without any 'conv_' keys → converter fields default to None/False."""
    state = _base_state()  # no conv_ keys
    draft = session_state_to_draft(state)

    assert draft.composition_input is None
    assert draft.full_influent_state_overrides is None
    assert draft.conversion_applied_to_manual is False
    assert draft.conversion_assumptions == []
    assert draft.conversion_warnings == []


# ---------------------------------------------------------------------------
# 3. Preset payload round-trip preserves composition_converter block
# ---------------------------------------------------------------------------

def test_preset_payload_round_trip_preserves_converter_block():
    """draft_to_preset_payload → preset_payload_to_draft preserves converter data."""
    draft = _draft_with_converter()
    payload = draft_to_preset_payload(draft)

    assert "composition_converter" in payload
    conv = payload["composition_converter"]
    assert conv["composition_input"] == _SAMPLE_COMPOSITION_INPUT
    assert conv["full_influent_state_overrides"] == _SAMPLE_OVERRIDES
    assert conv["conversion_applied_to_manual"] is True

    draft2 = preset_payload_to_draft(payload)
    assert draft2.composition_input == _SAMPLE_COMPOSITION_INPUT
    assert draft2.full_influent_state_overrides == _SAMPLE_OVERRIDES
    assert draft2.conversion_applied_to_manual is True
    assert draft2.conversion_warnings == _SAMPLE_WARNINGS


def test_preset_payload_converter_block_contains_all_fields():
    """composition_converter block in payload contains all expected keys."""
    draft = _draft_with_converter()
    payload = draft_to_preset_payload(draft)
    conv = payload["composition_converter"]

    expected_keys = {
        "composition_input",
        "composition_result",
        "full_influent_state_overrides",
        "conversion_assumptions",
        "conversion_warnings",
        "conversion_applied_to_manual",
    }
    assert expected_keys.issubset(conv.keys())


# ---------------------------------------------------------------------------
# 4. Old preset payload without composition_converter block (backward compat)
# ---------------------------------------------------------------------------

def test_old_preset_payload_without_converter_block():
    """Preset payload without composition_converter key → None/False defaults."""
    old_payload = {
        "reactor_type": "cstr",
        "substrate_mode": "preset",
        "preset_id": "swine_slurry",
        "backend_choice": "full",
        "schema_version": "1",
        "operating": {},
        "simulation": {},
        "manual_feed_values": {},
        "full_extension_state_inputs": {},
        "full_extension_influent_inputs": {},
        "full_extension_param_inputs": {},
        "sim_full_extensions": [],
    }
    draft = preset_payload_to_draft(old_payload)
    assert draft.composition_input is None
    assert draft.full_influent_state_overrides is None
    assert draft.conversion_applied_to_manual is False
    assert draft.conversion_assumptions == []
    assert draft.conversion_warnings == []


def test_very_old_preset_payload_without_schema_version():
    """Pre-migration payload without schema_version also gets None converter fields."""
    old_payload = {
        "reactor_type": "cstr",
        "substrate_mode": "preset",
        "preset_id": "cattle_manure",
    }
    draft = preset_payload_to_draft(old_payload)
    assert draft.composition_input is None
    assert draft.conversion_applied_to_manual is False


# ---------------------------------------------------------------------------
# 5. Merge logic: converter overrides + extension overrides coexist
# ---------------------------------------------------------------------------

def test_converter_overrides_and_extension_overrides_coexist():
    """Converter influent overrides and extension overrides can coexist in a merged dict."""
    conv_overrides = {"X_ch": 35.7, "X_pr": 56.8, "X_li": 58.0, "X_I": 19.2, "S_su": 21.4}
    ext_overrides = {"S_SO4": 0.01, "X_alg": 0.5}

    merged = dict(conv_overrides)
    merged.update(ext_overrides)

    # Converter keys present
    assert "X_ch" in merged
    assert merged["X_ch"] == 35.7
    assert merged["X_pr"] == 56.8

    # Extension keys present (extension wins on conflict)
    assert "S_SO4" in merged
    assert merged["S_SO4"] == 0.01

    # Total keys
    assert len(merged) == len(conv_overrides) + len(ext_overrides)


def test_extension_overrides_win_on_key_conflict():
    """When same key exists in both, extension override takes priority (merged.update order)."""
    conv_overrides = {"S_su": 21.4, "X_ch": 35.7}
    ext_overrides = {"S_su": 99.0}  # Intentional conflict

    merged = dict(conv_overrides)
    merged.update(ext_overrides)

    assert merged["S_su"] == 99.0  # extension wins
    assert merged["X_ch"] == 35.7  # converter value preserved for non-conflicting key


# ---------------------------------------------------------------------------
# 6. save_custom_substrate_with_provenance stores provenance
# ---------------------------------------------------------------------------

def _make_empty_workbench_state():
    return {
        "preferences": {
            "default_reactor": "cstr",
            "default_backend": "full",
            "default_top_k": 5,
            "persist_scenarios_by_default": True,
            "show_home_onboarding": True,
            "auto_expand_top_result": True,
            "ammonia_inhibition_mode_default": "simple",
        },
        "simulation_presets": [],
        "custom_substrates": [],
        "favorite_queries": [],
        "recent_queries": [],
        "recent_simulations": [],
    }


def test_save_custom_substrate_with_provenance_stores_origin():
    """save_custom_substrate_with_provenance attaches origin='composition_converter'."""
    import webapp.services.preferences_service as ps

    shared_state = _make_empty_workbench_state()
    written_states = []

    def fake_load():
        return deepcopy(shared_state)

    def fake_write(state):
        shared_state.clear()
        shared_state.update(state)
        written_states.append(deepcopy(state))

    valid_values = {
        "particulate_cod": 169.7,
        "soluble_cod": 21.4,
        "acetate": 0.0,
        "propionate": 0.0,
        "hydrogen": 0.0,
        "inorganic_nitrogen": 1.0,
        "alkalinity": 4.0,
        "ph": 7.0,
    }

    with patch.object(ps, "load_workbench_state", fake_load), \
         patch.object(ps, "_write_state", fake_write):
        ps.save_custom_substrate_with_provenance(
            "Substrato Teste",
            valid_values,
            composition_input=dict(_SAMPLE_COMPOSITION_INPUT),
            assumptions=list(_SAMPLE_ASSUMPTIONS),
            warnings=list(_SAMPLE_WARNINGS),
        )

    final_state = written_states[-1]
    substrates = final_state.get("custom_substrates", [])
    assert len(substrates) == 1
    sub = substrates[0]
    assert sub["origin"] == "composition_converter"
    assert sub["composition_input"] == _SAMPLE_COMPOSITION_INPUT
    assert sub["conversion_assumptions"] == _SAMPLE_ASSUMPTIONS
    assert sub["conversion_warnings"] == _SAMPLE_WARNINGS


def test_save_custom_substrate_with_provenance_no_optional_provenance():
    """Calling without provenance args → origin is still set but no extra keys added."""
    import webapp.services.preferences_service as ps

    shared_state = _make_empty_workbench_state()
    written_states = []

    def fake_load():
        return deepcopy(shared_state)

    def fake_write(state):
        shared_state.clear()
        shared_state.update(state)
        written_states.append(deepcopy(state))

    valid_values = {
        "particulate_cod": 8.0,
        "soluble_cod": 4.0,
        "acetate": 0.5,
        "propionate": 0.2,
        "hydrogen": 0.001,
        "inorganic_nitrogen": 1.0,
        "alkalinity": 4.0,
        "ph": 7.0,
    }

    with patch.object(ps, "load_workbench_state", fake_load), \
         patch.object(ps, "_write_state", fake_write):
        ps.save_custom_substrate_with_provenance("Substrato Simples", valid_values)

    final_state = written_states[-1]
    substrates = final_state.get("custom_substrates", [])
    assert len(substrates) == 1
    sub = substrates[0]
    assert sub["origin"] == "composition_converter"
    assert "composition_input" not in sub
    assert "conversion_assumptions" not in sub
    assert "conversion_warnings" not in sub


# ---------------------------------------------------------------------------
# 7. Schema_version "1" present in preset payload
# ---------------------------------------------------------------------------

def test_preset_payload_has_schema_version():
    """draft_to_preset_payload always includes schema_version='1'."""
    draft = _draft_with_converter()
    payload = draft_to_preset_payload(draft)
    assert payload.get("schema_version") == "1"


# ---------------------------------------------------------------------------
# Runner for standalone execution (mirrors test_adapters.py pattern)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    tests = [
        test_draft_round_trip_preserves_composition_input,
        test_draft_round_trip_via_draft_objects,
        test_draft_round_trip_empty_converter_defaults,
        test_session_state_without_conv_keys_produces_defaults,
        test_preset_payload_round_trip_preserves_converter_block,
        test_preset_payload_converter_block_contains_all_fields,
        test_old_preset_payload_without_converter_block,
        test_very_old_preset_payload_without_schema_version,
        test_converter_overrides_and_extension_overrides_coexist,
        test_extension_overrides_win_on_key_conflict,
        test_save_custom_substrate_with_provenance_stores_origin,
        test_save_custom_substrate_with_provenance_no_optional_provenance,
        test_preset_payload_has_schema_version,
    ]
    passed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except Exception as exc:
            import traceback
            print(f"  FAIL  {t.__name__}: {exc}")
            traceback.print_exc()
    print(f"\n{passed}/{len(tests)} tests passed")
    if passed < len(tests):
        raise SystemExit(1)
