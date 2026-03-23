"""Tests for cross-field input validation in FeedDefinition and SimulationConfig."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from simulator.core.models import FeedDefinition, SimulationConfig


# ---------------------------------------------------------------------------
# FeedDefinition: validate_feed_composition
# ---------------------------------------------------------------------------


class TestFeedCompositionValidation:
    def test_valid_defaults_pass(self) -> None:
        """Default BSM2 values must pass validation without error."""
        feed = FeedDefinition()
        assert feed.acetate + feed.propionate <= feed.soluble_cod + 1e-6

    def test_valid_vfa_within_soluble_cod(self) -> None:
        """Acetate + propionate exactly equal to soluble_cod is allowed."""
        feed = FeedDefinition(soluble_cod=1.0, acetate=0.6, propionate=0.4)
        assert feed.soluble_cod == 1.0

    def test_vfa_exceeds_soluble_cod_raises(self) -> None:
        """acetate + propionate > soluble_cod must raise ValidationError."""
        with pytest.raises(ValidationError, match="exceeds soluble_cod"):
            FeedDefinition(soluble_cod=0.5, acetate=0.4, propionate=0.3)

    def test_vfa_slightly_above_with_tolerance_accepted(self) -> None:
        """Floating-point noise within 1e-6 tolerance must not raise."""
        # 0.3 + 0.2 + floating-point noise <= 0.5 + 1e-6
        feed = FeedDefinition(soluble_cod=0.5, acetate=0.3, propionate=0.2)
        assert feed is not None

    def test_zero_total_cod_raises(self) -> None:
        """particulate_cod = 0 AND soluble_cod = 0 must raise ValidationError."""
        with pytest.raises(ValidationError, match="Total feed COD"):
            FeedDefinition(particulate_cod=0.0, soluble_cod=0.0, acetate=0.0, propionate=0.0)

    def test_only_particulate_cod_is_valid(self) -> None:
        """particulate_cod > 0 with soluble_cod = 0 is a valid feed (e.g. solid waste)."""
        feed = FeedDefinition(particulate_cod=10.0, soluble_cod=0.0, acetate=0.0, propionate=0.0)
        assert feed.particulate_cod == 10.0

    def test_only_soluble_cod_is_valid(self) -> None:
        """soluble_cod > 0 with particulate_cod = 0 is a valid feed."""
        feed = FeedDefinition(particulate_cod=0.0, soluble_cod=5.0, acetate=2.0)
        assert feed.soluble_cod == 5.0


# ---------------------------------------------------------------------------
# SimulationConfig: validate_solver_tolerances
# ---------------------------------------------------------------------------


class TestSolverToleranceValidation:
    def test_valid_defaults_pass(self) -> None:
        """Default atol=1e-7 < rtol=1e-5 must pass."""
        cfg = SimulationConfig()
        assert cfg.atol < cfg.rtol

    def test_atol_equal_rtol_passes(self) -> None:
        """atol == rtol is the edge case that should pass."""
        cfg = SimulationConfig(rtol=1e-5, atol=1e-5)
        assert cfg.rtol == cfg.atol

    def test_atol_greater_than_rtol_raises(self) -> None:
        """atol > rtol must raise ValidationError with descriptive message."""
        with pytest.raises(ValidationError, match="atol.*must be ≤ rtol"):
            SimulationConfig(rtol=1e-7, atol=1e-5)

    def test_relaxed_tolerances_still_ordered(self) -> None:
        """Multi-segment solvers use rtol=1e-4, atol=1e-6 — must pass."""
        cfg = SimulationConfig(rtol=1e-4, atol=1e-6)
        assert cfg.atol <= cfg.rtol

    def test_very_tight_tolerances_ordered(self) -> None:
        """Very tight tolerances are valid as long as atol <= rtol."""
        cfg = SimulationConfig(rtol=1e-8, atol=1e-10)
        assert cfg.atol <= cfg.rtol
