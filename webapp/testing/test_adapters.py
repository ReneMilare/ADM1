"""Testes de round-trip para webapp.state.adapters.

Verifica que session_state → SimulationDraft → session_state preserva todos
os campos relevantes, incluindo os adicionados no Plano 06:
  • ammonia_inhibition_mode
  • variant_config
  • codigestion_fractions  (modo codigestion/__custom__)
"""

from __future__ import annotations

import sys
import os

# Garante que a raiz do projeto está no path
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from webapp.state.adapters import draft_to_session_state, session_state_to_draft


# ─── helpers ─────────────────────────────────────────────────────────────────

def _base_state(**overrides) -> dict:
    """Estado mínimo válido para session_state_to_draft."""
    base = {
        "sim_reactor_type": "cstr",
        "sim_substrate_mode": "preset",
        "sim_manual_input_mode": "manual",
        "sim_preset_id": "swine_slurry",
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


# ─── testes de round-trip ─────────────────────────────────────────────────────

def test_preset_mode_round_trip():
    """Modo preset: todos os campos escalares sobrevivem ao round-trip."""
    state = _base_state(
        sim_preset_id="cattle_manure",
        hydraulic_mode="flow",
        volume_active=1500.0,
        temperature_active=37.0,
        hrt_active=25.0,
        flow_rate_active=60.0,
        duration_days=60.0,
        persist_case=False,
        ammonia_inhibition_mode="detailed",
        variant_config={"k_dis": 0.5},
    )
    draft = session_state_to_draft(state)
    restored = draft_to_session_state(draft)

    assert draft.substrate_mode == "preset"
    assert draft.preset_id == "cattle_manure"
    assert draft.ammonia_inhibition_mode == "detailed"
    assert draft.variant_config == {"k_dis": 0.5}
    assert draft.codigestion_fractions is None

    assert restored["sim_substrate_mode"] == "preset"
    assert restored["sim_preset_id"] == "cattle_manure"
    assert restored["ammonia_inhibition_mode"] == "detailed"
    assert restored["variant_config"] == {"k_dis": 0.5}
    assert restored["volume_active"] == 1500.0
    assert restored["temperature_active"] == 37.0
    assert restored["persist_case"] is False


def test_codigestion_preset_round_trip():
    """Modo codigestion com preset nomeado: preset_id restaurado em codigestion_preset."""
    state = _base_state(
        sim_substrate_mode="codigestion",
        codigestion_preset="pig_cattle_mix",
        ammonia_inhibition_mode="simple",
    )
    draft = session_state_to_draft(state)
    restored = draft_to_session_state(draft)

    assert draft.substrate_mode == "codigestion"
    assert draft.preset_id == "pig_cattle_mix"
    assert draft.codigestion_fractions is None

    assert restored["sim_substrate_mode"] == "codigestion"
    assert restored["codigestion_preset"] == "pig_cattle_mix"
    assert restored.get("codig_custom_substrates") is None


def test_codigestion_custom_blend_round_trip():
    """Modo codigestion/__custom__: frações individuais são preservadas."""
    substrates = ["swine_slurry", "food_waste"]
    state = _base_state(
        sim_substrate_mode="codigestion",
        codigestion_preset="__custom__",
        codig_custom_substrates=substrates,
        codig_frac_swine_slurry=0.6,
        codig_frac_food_waste=0.4,
        ammonia_inhibition_mode="simple",
    )
    draft = session_state_to_draft(state)
    restored = draft_to_session_state(draft)

    assert draft.substrate_mode == "codigestion"
    assert draft.preset_id == "__custom__"
    assert draft.codigestion_fractions == {"swine_slurry": 0.6, "food_waste": 0.4}

    assert restored["codigestion_preset"] == "__custom__"
    assert set(restored["codig_custom_substrates"]) == {"swine_slurry", "food_waste"}
    assert abs(restored["codig_frac_swine_slurry"] - 0.6) < 1e-9
    assert abs(restored["codig_frac_food_waste"] - 0.4) < 1e-9


def test_ammonia_inhibition_mode_default():
    """Sem chave no state → default 'simple'."""
    state = _base_state()
    state.pop("ammonia_inhibition_mode", None)
    draft = session_state_to_draft(state)
    assert draft.ammonia_inhibition_mode == "simple"


def test_variant_config_none_default():
    """Sem chave no state → variant_config é None."""
    state = _base_state()
    state.pop("variant_config", None)
    draft = session_state_to_draft(state)
    assert draft.variant_config is None


def test_extension_state_defaults_round_trip():
    """Extensões sem overrides: round-trip mantém os defaults."""
    state = _base_state()
    draft = session_state_to_draft(state)
    restored = draft_to_session_state(draft)
    draft2 = session_state_to_draft(restored)

    assert draft.extension_state_overrides == draft2.extension_state_overrides
    assert draft.extension_influent_overrides == draft2.extension_influent_overrides
    assert draft.extension_param_overrides == draft2.extension_param_overrides


def test_manual_input_mode_round_trip():
    """O subtipo do modo manual sobrevive ao round-trip de adapters."""
    state = _base_state(
        sim_substrate_mode="manual",
        sim_manual_input_mode="composition_converter",
    )
    draft = session_state_to_draft(state)
    restored = draft_to_session_state(draft)

    assert draft.manual_input_mode == "composition_converter"
    assert restored["sim_manual_input_mode"] == "composition_converter"


def test_session_state_to_draft_uses_defaults_for_none_numeric_values():
    """Campos numéricos explícitos como None não devem quebrar o adapter."""
    state = _base_state(
        sim_substrate_mode="manual",
        manual_particulate_cod=None,
        manual_soluble_cod=None,
        manual_alkalinity=None,
        manual_feed_ph=None,
        volume_active=None,
        duration_days=None,
        evaluation_points=None,
    )

    draft = session_state_to_draft(state)

    assert draft.feed_params["particulate_cod"] == 8.0
    assert draft.feed_params["soluble_cod"] == 4.0
    assert draft.feed_params["alkalinity"] == 4.0
    assert draft.feed_params["ph"] == 7.0
    assert draft.volume_m3 == 3000.0
    assert draft.duration_days == 45.0
    assert draft.evaluation_points == 181


# ─── runner standalone ────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [
        test_preset_mode_round_trip,
        test_codigestion_preset_round_trip,
        test_codigestion_custom_blend_round_trip,
        test_ammonia_inhibition_mode_default,
        test_variant_config_none_default,
        test_extension_state_defaults_round_trip,
        test_manual_input_mode_round_trip,
        test_session_state_to_draft_uses_defaults_for_none_numeric_values,
    ]
    passed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except Exception as exc:
            print(f"  FAIL  {t.__name__}: {exc}")

    print(f"\n{passed}/{len(tests)} tests passed")
    if passed < len(tests):
        raise SystemExit(1)


def test_temperature_kinetics_round_trip():
    draft = session_state_to_draft(_base_state(temperature_kinetics="siegrist2002"))
    assert draft.temperature_kinetics == "siegrist2002"
    assert draft_to_session_state(draft)["temperature_kinetics"] == "siegrist2002"
