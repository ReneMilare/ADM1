"""Unit tests for the substrate-composition → ADM1 converter engine.

Tests cover the pure Python service (simulator.substrate_conversion.service)
with no Streamlit dependency.
"""
from __future__ import annotations

import math
import pytest

from simulator.substrate_conversion.contracts import CompositionInput
from simulator.substrate_conversion.policies import (
    ALKALINITY_MEQ_L_TO_LEGACY,
    CELLULOSE_COD_FACTOR,
    DEFAULT_ALKALINITY,
    DEFAULT_INORGANIC_NITROGEN_KGN_M3,
    DEFAULT_PH,
    FAST_CARB_COD_FACTOR,
    LIGNIN_COD_FACTOR,
    LIPIDS_COD_FACTOR,
    PCT_TO_KG_PER_M3,
    PROTEIN_COD_FACTOR,
    TAN_MG_L_TO_KGN_M3,
)
from simulator.substrate_conversion.service import convert_composition_to_adm1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _food_waste(**overrides) -> CompositionInput:
    """Reference input: typical food waste (Resíduo alimentar típico)."""
    defaults = dict(
        sample_name="Resíduo alimentar típico",
        dry_matter_pct=15.0,
        organic_matter_pct=12.0,
        protein_pct=4.0,
        lipids_pct=2.0,
        cellulose_pct=3.0,
        lignin_pct=1.0,
    )
    defaults.update(overrides)
    return CompositionInput(**defaults)


def _cattle_manure(**overrides) -> CompositionInput:
    """Reference input: cattle manure (Dejeto bovino)."""
    defaults = dict(
        sample_name="Dejeto bovino",
        dry_matter_pct=10.0,
        organic_matter_pct=8.0,
        protein_pct=2.0,
        lipids_pct=0.5,
        cellulose_pct=3.0,
        lignin_pct=1.5,
    )
    defaults.update(overrides)
    return CompositionInput(**defaults)


# ---------------------------------------------------------------------------
# 1. Happy path — reference case "Resíduo alimentar típico"
# ---------------------------------------------------------------------------

class TestFoodWasteReferenceCase:
    """Full numeric verification of the canonical food-waste reference case."""

    def test_particulate_fractions(self):
        result = convert_composition_to_adm1(_food_waste())
        fs = result.full_influent_state_overrides

        assert math.isclose(fs.X_pr, 4.0 * PCT_TO_KG_PER_M3 * PROTEIN_COD_FACTOR, rel_tol=1e-9)   # 56.8
        assert math.isclose(fs.X_li, 2.0 * PCT_TO_KG_PER_M3 * LIPIDS_COD_FACTOR, rel_tol=1e-9)    # 58.0
        assert math.isclose(fs.X_ch, 3.0 * PCT_TO_KG_PER_M3 * CELLULOSE_COD_FACTOR, rel_tol=1e-9) # 35.7
        assert math.isclose(fs.X_I,  1.0 * PCT_TO_KG_PER_M3 * LIGNIN_COD_FACTOR, rel_tol=1e-9)    # 19.2

    def test_soluble_fraction(self):
        # other_carb = 12 - 4 - 2 - 3 - 1 = 2.0 → S_su = 2.0 * 10 * 1.07 = 21.4
        result = convert_composition_to_adm1(_food_waste())
        fs = result.full_influent_state_overrides
        assert math.isclose(fs.S_su, 2.0 * PCT_TO_KG_PER_M3 * FAST_CARB_COD_FACTOR, rel_tol=1e-9)

    def test_particulate_cod_sum(self):
        result = convert_composition_to_adm1(_food_waste())
        fs = result.full_influent_state_overrides
        expected_particulate = fs.X_ch + fs.X_pr + fs.X_li + fs.X_I
        assert math.isclose(result.reduced_feed_values.particulate_cod, expected_particulate, rel_tol=1e-9)
        assert math.isclose(result.reduced_feed_values.particulate_cod, 169.7, rel_tol=1e-4)

    def test_soluble_cod_sum(self):
        result = convert_composition_to_adm1(_food_waste())
        fs = result.full_influent_state_overrides
        expected_soluble = fs.S_su + fs.S_aa + fs.S_fa + fs.S_I
        assert math.isclose(result.reduced_feed_values.soluble_cod, expected_soluble, rel_tol=1e-9)
        assert math.isclose(result.reduced_feed_values.soluble_cod, 21.4, rel_tol=1e-4)

    def test_v1_unmeasured_soluble_fractions_are_zero(self):
        result = convert_composition_to_adm1(_food_waste())
        fs = result.full_influent_state_overrides
        assert fs.S_aa == 0.0
        assert fs.S_fa == 0.0
        assert fs.S_I == 0.0
        assert fs.S_ac == 0.0
        assert fs.S_pro == 0.0
        assert fs.S_h2 == 0.0

    def test_derived_values(self):
        result = convert_composition_to_adm1(_food_waste())
        dv = result.derived_values
        assert math.isclose(dv.moisture_pct, 85.0, rel_tol=1e-9)   # 100 - 15
        assert math.isclose(dv.ash_pct, 3.0, rel_tol=1e-9)         # 15 - 12
        assert math.isclose(dv.other_carbohydrates_pct, 2.0, rel_tol=1e-9)
        assert dv.organic_closure_ok is True


# ---------------------------------------------------------------------------
# 2. ValueError when other_carbohydrates < 0
# ---------------------------------------------------------------------------

def test_negative_other_carbohydrates_raises_value_error():
    """protein + lipids + cellulose + lignin > organic_matter → ValueError."""
    inp = CompositionInput(
        sample_name="Inconsistente",
        dry_matter_pct=10.0,
        organic_matter_pct=5.0,
        protein_pct=3.0,
        lipids_pct=2.0,
        cellulose_pct=1.0,
        lignin_pct=0.5,
    )
    with pytest.raises(ValueError, match="negative"):
        convert_composition_to_adm1(inp)


# ---------------------------------------------------------------------------
# 3. Lignin maps to X_I
# ---------------------------------------------------------------------------

def test_lignin_maps_to_x_i():
    """Lignin fraction maps exclusively to X_I (kgCOD/m³)."""
    lignin_pct = 2.5
    inp = _food_waste(lignin_pct=lignin_pct, organic_matter_pct=13.5)  # keep other_carb >= 0
    result = convert_composition_to_adm1(inp)
    expected_x_i = lignin_pct * PCT_TO_KG_PER_M3 * LIGNIN_COD_FACTOR
    assert math.isclose(result.full_influent_state_overrides.X_I, expected_x_i, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# 4. Fast carbohydrates map to S_su
# ---------------------------------------------------------------------------

def test_fast_carbohydrates_map_to_s_su():
    """Other carbohydrates (residual) map exclusively to S_su."""
    # Force a known other_carb by setting everything so other_carb = 3.0
    inp = CompositionInput(
        sample_name="Test S_su",
        dry_matter_pct=20.0,
        organic_matter_pct=15.0,
        protein_pct=4.0,
        lipids_pct=3.0,
        cellulose_pct=3.0,
        lignin_pct=2.0,
        # other_carb = 15 - 4 - 3 - 3 - 2 = 3.0
    )
    result = convert_composition_to_adm1(inp)
    expected_s_su = 3.0 * PCT_TO_KG_PER_M3 * FAST_CARB_COD_FACTOR
    assert math.isclose(result.full_influent_state_overrides.S_su, expected_s_su, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# 5. pH default assumed when not provided; used when provided
# ---------------------------------------------------------------------------

def test_ph_default_assumed_when_not_provided():
    """No pH → reduced_feed_values.ph == DEFAULT_PH and assumption recorded."""
    result = convert_composition_to_adm1(_food_waste())  # no ph
    assert result.reduced_feed_values.ph == DEFAULT_PH
    assert result.full_influent_state_overrides.ph is None
    ph_assumptions = [a for a in result.assumptions_used if a.field == "ph"]
    assert len(ph_assumptions) == 1
    assert ph_assumptions[0].assumed_value == DEFAULT_PH


def test_ph_used_when_provided():
    """Measured pH in range → used as-is, no pH assumption recorded."""
    result = convert_composition_to_adm1(_food_waste(ph=6.5))
    assert result.reduced_feed_values.ph == 6.5
    assert result.full_influent_state_overrides.ph == 6.5
    ph_assumptions = [a for a in result.assumptions_used if a.field == "ph"]
    assert len(ph_assumptions) == 0


# ---------------------------------------------------------------------------
# 6. Alkalinity default assumed when not provided; converted when provided
# ---------------------------------------------------------------------------

def test_alkalinity_default_assumed_when_not_provided():
    """No alkalinity → DEFAULT_ALKALINITY used and assumption recorded."""
    result = convert_composition_to_adm1(_food_waste())
    assert result.reduced_feed_values.alkalinity == DEFAULT_ALKALINITY
    alk_assumptions = [a for a in result.assumptions_used if a.field == "alkalinity"]
    assert len(alk_assumptions) == 1
    assert alk_assumptions[0].assumed_value == DEFAULT_ALKALINITY


def test_alkalinity_converted_when_provided():
    """Alkalinity in mEq/L → converted to legacy scale; no alkalinity assumption."""
    result = convert_composition_to_adm1(_food_waste(alkalinity_meq_l=80.0))
    expected = 80.0 * ALKALINITY_MEQ_L_TO_LEGACY
    assert math.isclose(result.reduced_feed_values.alkalinity, expected, rel_tol=1e-9)
    alk_assumptions = [a for a in result.assumptions_used if a.field == "alkalinity"]
    assert len(alk_assumptions) == 0


# ---------------------------------------------------------------------------
# 7. TAN converts to S_IN
# ---------------------------------------------------------------------------

def test_tan_converts_to_s_in():
    """TAN (mg N/L) → S_IN (kgN/m³) in full_influent_state_overrides."""
    tan_mg_l = 500.0
    result = convert_composition_to_adm1(_food_waste(tan_mg_l=tan_mg_l))
    expected_s_in = tan_mg_l * TAN_MG_L_TO_KGN_M3
    assert result.full_influent_state_overrides.S_IN is not None
    assert math.isclose(result.full_influent_state_overrides.S_IN, expected_s_in, rel_tol=1e-9)
    # S_IN provided → reduced feed uses S_IN value
    assert math.isclose(result.reduced_feed_values.inorganic_nitrogen, expected_s_in, rel_tol=1e-9)
    # No TAN assumption
    tan_assumptions = [a for a in result.assumptions_used if a.field == "inorganic_nitrogen"]
    assert len(tan_assumptions) == 0


def test_tan_not_provided_s_in_is_none_and_assumed():
    """No TAN → S_IN is None in full_influent_state_overrides and assumption recorded."""
    result = convert_composition_to_adm1(_food_waste())
    assert result.full_influent_state_overrides.S_IN is None
    # Reduced feed gets DEFAULT_INORGANIC_NITROGEN_KGN_M3 as fallback
    assert result.reduced_feed_values.inorganic_nitrogen == DEFAULT_INORGANIC_NITROGEN_KGN_M3
    tan_assumptions = [a for a in result.assumptions_used if a.field == "inorganic_nitrogen"]
    assert len(tan_assumptions) == 1
    assert tan_assumptions[0].assumed_value == DEFAULT_INORGANIC_NITROGEN_KGN_M3


# ---------------------------------------------------------------------------
# 8. Reduced feed values are non-negative and structurally valid
# ---------------------------------------------------------------------------

def test_reduced_feed_values_non_negative():
    """All ReducedFeedValues numeric fields must be >= 0."""
    result = convert_composition_to_adm1(_food_waste())
    rfv = result.reduced_feed_values
    assert rfv.particulate_cod >= 0.0
    assert rfv.soluble_cod >= 0.0
    assert rfv.acetate >= 0.0
    assert rfv.propionate >= 0.0
    assert rfv.hydrogen >= 0.0
    assert rfv.inorganic_nitrogen >= 0.0
    assert rfv.alkalinity >= 0.0
    # sic_kmol_m3 is optional (None is acceptable)
    assert rfv.sic_kmol_m3 is None or rfv.sic_kmol_m3 >= 0.0
    assert rfv.ph >= 0.0


def test_reduced_feed_values_name_matches_sample_name():
    """ReducedFeedValues.name mirrors CompositionInput.sample_name."""
    result = convert_composition_to_adm1(_food_waste(sample_name="Meu Substrato"))
    assert result.reduced_feed_values.name == "Meu Substrato"


# ---------------------------------------------------------------------------
# 9. Assumptions list tracks what was assumed
# ---------------------------------------------------------------------------

def test_no_optional_fields_produces_three_assumptions():
    """No pH, alkalinity, or TAN → at least 3 assumptions (ph, alkalinity, inorganic_nitrogen)."""
    result = convert_composition_to_adm1(_food_waste())
    assumption_fields = {a.field for a in result.assumptions_used}
    assert "ph" in assumption_fields
    assert "alkalinity" in assumption_fields
    assert "inorganic_nitrogen" in assumption_fields
    assert len(result.assumptions_used) >= 3


def test_all_optional_fields_provided_produces_zero_assumptions():
    """pH + alkalinity + TAN all provided → no assumptions needed."""
    result = convert_composition_to_adm1(_food_waste(ph=7.0, alkalinity_meq_l=40.0, tan_mg_l=300.0))
    assert len(result.assumptions_used) == 0


# ---------------------------------------------------------------------------
# 10. Warnings emitted for out-of-range pH
# ---------------------------------------------------------------------------

def test_ph_out_of_range_low_emits_warning_and_clamps():
    """pH below 5.0 → warning emitted and value clamped to 5.0."""
    result = convert_composition_to_adm1(_food_waste(ph=4.0))
    assert len(result.warnings) >= 1
    assert any("clamp" in w.lower() or "5.0" in w for w in result.warnings)
    assert result.reduced_feed_values.ph == 5.0
    assert result.full_influent_state_overrides.ph == 5.0


def test_ph_out_of_range_high_emits_warning_and_clamps():
    """pH above 8.5 → warning emitted and value clamped to 8.5."""
    result = convert_composition_to_adm1(_food_waste(ph=9.5))
    assert len(result.warnings) >= 1
    assert result.reduced_feed_values.ph == 8.5
    assert result.full_influent_state_overrides.ph == 8.5


def test_ph_within_range_no_warning():
    """pH within [5.0, 8.5] → no warnings emitted."""
    result = convert_composition_to_adm1(_food_waste(ph=7.2))
    assert len(result.warnings) == 0


# ---------------------------------------------------------------------------
# 11. Validation: negative pct fields raise ValueError
# ---------------------------------------------------------------------------

def test_negative_dry_matter_raises():
    with pytest.raises(ValueError, match="dry_matter_pct"):
        convert_composition_to_adm1(CompositionInput(
            sample_name="Bad", dry_matter_pct=-1.0, organic_matter_pct=0.0,
            protein_pct=0.0, lipids_pct=0.0, cellulose_pct=0.0, lignin_pct=0.0,
        ))


def test_organic_matter_exceeds_dry_matter_raises():
    with pytest.raises(ValueError, match="organic_matter_pct"):
        convert_composition_to_adm1(CompositionInput(
            sample_name="Bad", dry_matter_pct=10.0, organic_matter_pct=15.0,
            protein_pct=0.0, lipids_pct=0.0, cellulose_pct=0.0, lignin_pct=0.0,
        ))


# ---------------------------------------------------------------------------
# 12. Reference case "Dejeto bovino" — self-consistency check
# ---------------------------------------------------------------------------

class TestCattleManureReferenceCase:
    """Self-consistency checks for a realistic cattle manure composition."""

    def test_particulate_cod_equals_component_sum(self):
        result = convert_composition_to_adm1(_cattle_manure())
        fs = result.full_influent_state_overrides
        rfv = result.reduced_feed_values
        expected = fs.X_ch + fs.X_pr + fs.X_li + fs.X_I
        assert math.isclose(rfv.particulate_cod, expected, rel_tol=1e-9)

    def test_soluble_cod_equals_s_su_in_v1(self):
        # other_carb = 8 - 2 - 0.5 - 3 - 1.5 = 1.0
        result = convert_composition_to_adm1(_cattle_manure())
        fs = result.full_influent_state_overrides
        rfv = result.reduced_feed_values
        expected = fs.S_su + fs.S_aa + fs.S_fa + fs.S_I
        assert math.isclose(rfv.soluble_cod, expected, rel_tol=1e-9)

    def test_x_ch_value(self):
        result = convert_composition_to_adm1(_cattle_manure())
        expected = 3.0 * PCT_TO_KG_PER_M3 * CELLULOSE_COD_FACTOR  # 35.7
        assert math.isclose(result.full_influent_state_overrides.X_ch, expected, rel_tol=1e-9)

    def test_x_i_value(self):
        result = convert_composition_to_adm1(_cattle_manure())
        expected = 1.5 * PCT_TO_KG_PER_M3 * LIGNIN_COD_FACTOR  # 28.8
        assert math.isclose(result.full_influent_state_overrides.X_I, expected, rel_tol=1e-9)

    def test_s_ic_is_none(self):
        """S_IC fallback: always None in v1 (complex conversion deferred)."""
        result = convert_composition_to_adm1(_cattle_manure())
        assert result.full_influent_state_overrides.S_IC is None
        assert result.reduced_feed_values.sic_kmol_m3 is None

    def test_composition_input_preserved(self):
        inp = _cattle_manure()
        result = convert_composition_to_adm1(inp)
        assert result.composition_input is inp

    def test_other_carbohydrates_derived_value(self):
        # other_carb = 8.0 - 2.0 - 0.5 - 3.0 - 1.5 = 1.0
        result = convert_composition_to_adm1(_cattle_manure())
        assert math.isclose(result.derived_values.other_carbohydrates_pct, 1.0, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# 13. Edge case: zero organic matter (pure mineral input)
# ---------------------------------------------------------------------------

def test_zero_organic_matter_all_zeros():
    """All organic fractions = 0 → all COD values = 0 (no division errors)."""
    inp = CompositionInput(
        sample_name="Mineral puro",
        dry_matter_pct=5.0,
        organic_matter_pct=0.0,
        protein_pct=0.0,
        lipids_pct=0.0,
        cellulose_pct=0.0,
        lignin_pct=0.0,
    )
    result = convert_composition_to_adm1(inp)
    fs = result.full_influent_state_overrides
    assert fs.X_ch == 0.0
    assert fs.X_pr == 0.0
    assert fs.X_li == 0.0
    assert fs.X_I == 0.0
    assert fs.S_su == 0.0
    assert result.reduced_feed_values.particulate_cod == 0.0
    assert result.reduced_feed_values.soluble_cod == 0.0
