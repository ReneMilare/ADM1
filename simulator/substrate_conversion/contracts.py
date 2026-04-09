from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CompositionInput:
    """Raw substrate biochemical composition as entered by the user (wet basis)."""

    sample_name: str
    dry_matter_pct: float
    organic_matter_pct: float
    protein_pct: float
    lipids_pct: float
    cellulose_pct: float
    lignin_pct: float
    ph: float | None = None
    alkalinity_meq_l: float | None = None
    tan_mg_l: float | None = None
    analysis_basis: str = "wet"


@dataclass
class DerivedValues:
    """Values calculated from the composition input."""

    moisture_pct: float
    ash_pct: float
    other_carbohydrates_pct: float
    organic_closure_ok: bool


@dataclass
class FullInfluentStateOverrides:
    """Full ADM1 state variable overrides (kgCOD/m3 unless noted)."""

    X_ch: float
    X_pr: float
    X_li: float
    X_I: float
    S_su: float
    S_aa: float
    S_fa: float
    S_I: float
    S_ac: float
    S_pro: float
    S_h2: float
    S_IN: float | None = None   # kgN/m3; None → use FeedDefinition default
    S_IC: float | None = None   # kmol/m3; None → use existing fallback
    ph: float | None = None


@dataclass
class ReducedFeedValues:
    """Collapsed values compatible with FeedDefinition."""

    particulate_cod: float
    soluble_cod: float
    acetate: float
    propionate: float
    hydrogen: float
    inorganic_nitrogen: float
    alkalinity: float
    sic_kmol_m3: float | None
    ph: float
    name: str


@dataclass
class ConversionAssumption:
    """A single assumption made during conversion when a measurement was absent."""

    field: str
    assumed_value: Any
    reason: str


@dataclass
class ConversionResult:
    """Full output produced by the substrate composition converter."""

    composition_input: CompositionInput
    derived_values: DerivedValues
    full_influent_state_overrides: FullInfluentStateOverrides
    reduced_feed_values: ReducedFeedValues
    assumptions_used: list[ConversionAssumption] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
