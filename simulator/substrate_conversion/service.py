"""Pure Python conversion engine: substrate biochemical composition → ADM1 inputs.

No Streamlit dependency. Deterministic: same input produces same output.
"""
from __future__ import annotations

from simulator.substrate_conversion.contracts import (
    CompositionInput,
    ConversionAssumption,
    ConversionResult,
    DerivedValues,
    FullInfluentStateOverrides,
    ReducedFeedValues,
)
from simulator.substrate_conversion.policies import (
    ALKALINITY_MEQ_L_TO_LEGACY,
    CELLULOSE_COD_FACTOR,
    DEFAULT_ALKALINITY,
    DEFAULT_INORGANIC_NITROGEN_KGN_M3,
    DEFAULT_PH,
    FAST_CARB_COD_FACTOR,
    LIGNIN_COD_FACTOR,
    LIPIDS_COD_FACTOR,
    MIN_PCT,
    PCT_TO_KG_PER_M3,
    PROTEIN_COD_FACTOR,
    TAN_MG_L_TO_KGN_M3,
)

_PH_MIN = 5.0
_PH_MAX = 8.5


def convert_composition_to_adm1(inp: CompositionInput) -> ConversionResult:
    """Convert substrate biochemical composition to ADM1 inputs.

    Steps:
    1. Validate input
    2. Calculate derived values
    3. Map to full ADM1 state overrides
    4. Collapse to reduced feed values
    5. Collect assumptions and warnings

    Raises:
        ValueError: when input is internally inconsistent (other_carbohydrates < 0,
                    organic_matter > dry_matter, or any pct field is negative).
    """
    assumptions: list[ConversionAssumption] = []
    warnings: list[str] = []

    # ------------------------------------------------------------------
    # 1. Validate input
    # ------------------------------------------------------------------
    pct_fields = {
        "dry_matter_pct": inp.dry_matter_pct,
        "organic_matter_pct": inp.organic_matter_pct,
        "protein_pct": inp.protein_pct,
        "lipids_pct": inp.lipids_pct,
        "cellulose_pct": inp.cellulose_pct,
        "lignin_pct": inp.lignin_pct,
    }
    for name, value in pct_fields.items():
        if value < MIN_PCT:
            raise ValueError(f"'{name}' must be >= 0, got {value}")

    if inp.organic_matter_pct > inp.dry_matter_pct:
        raise ValueError(
            f"organic_matter_pct ({inp.organic_matter_pct}) cannot exceed "
            f"dry_matter_pct ({inp.dry_matter_pct})"
        )

    other_carbohydrates_pct = (
        inp.organic_matter_pct
        - inp.protein_pct
        - inp.lipids_pct
        - inp.cellulose_pct
        - inp.lignin_pct
    )
    if other_carbohydrates_pct < -1e-9:
        raise ValueError(
            f"Sum of protein + lipids + cellulose + lignin "
            f"({inp.protein_pct + inp.lipids_pct + inp.cellulose_pct + inp.lignin_pct}) "
            f"exceeds organic_matter_pct ({inp.organic_matter_pct}). "
            "other_carbohydrates would be negative."
        )
    other_carbohydrates_pct = max(0.0, other_carbohydrates_pct)

    # pH: warn and clamp when out of range
    ph_measured: float | None = inp.ph
    if ph_measured is not None:
        if ph_measured < _PH_MIN or ph_measured > _PH_MAX:
            warnings.append(
                f"Measured pH {ph_measured} is outside the valid range "
                f"[{_PH_MIN}, {_PH_MAX}]; clamped to {max(_PH_MIN, min(_PH_MAX, ph_measured)):.2f}."
            )
            ph_measured = max(_PH_MIN, min(_PH_MAX, ph_measured))

    # ------------------------------------------------------------------
    # 2. Derived values
    # ------------------------------------------------------------------
    moisture_pct = 100.0 - inp.dry_matter_pct
    ash_pct = inp.dry_matter_pct - inp.organic_matter_pct
    organic_sum = (
        inp.protein_pct
        + inp.lipids_pct
        + inp.cellulose_pct
        + inp.lignin_pct
        + other_carbohydrates_pct
    )
    organic_closure_ok = abs(organic_sum - inp.organic_matter_pct) < 1e-6

    derived = DerivedValues(
        moisture_pct=moisture_pct,
        ash_pct=ash_pct,
        other_carbohydrates_pct=other_carbohydrates_pct,
        organic_closure_ok=organic_closure_ok,
    )

    # ------------------------------------------------------------------
    # 3. Map to full ADM1 state overrides
    # ------------------------------------------------------------------
    X_pr = inp.protein_pct * PCT_TO_KG_PER_M3 * PROTEIN_COD_FACTOR
    X_li = inp.lipids_pct * PCT_TO_KG_PER_M3 * LIPIDS_COD_FACTOR
    X_ch = inp.cellulose_pct * PCT_TO_KG_PER_M3 * CELLULOSE_COD_FACTOR
    X_I = inp.lignin_pct * PCT_TO_KG_PER_M3 * LIGNIN_COD_FACTOR
    S_su = other_carbohydrates_pct * PCT_TO_KG_PER_M3 * FAST_CARB_COD_FACTOR

    # v1: unmeasured soluble fractions set to zero
    S_aa = 0.0
    S_fa = 0.0
    S_I = 0.0
    S_ac = 0.0
    S_pro = 0.0
    S_h2 = 0.0

    # S_IN from TAN measurement
    if inp.tan_mg_l is not None:
        S_IN: float | None = inp.tan_mg_l * TAN_MG_L_TO_KGN_M3
    else:
        S_IN = None
        assumptions.append(
            ConversionAssumption(
                field="inorganic_nitrogen",
                assumed_value=DEFAULT_INORGANIC_NITROGEN_KGN_M3,
                reason="TAN/NH4 not measured; inorganic nitrogen set to application default (low confidence)",
            )
        )

    # S_IC: keep None (complex conversion; rely on existing fallback)
    S_IC: float | None = None

    # pH override for state
    state_ph: float | None = ph_measured
    if state_ph is None:
        assumptions.append(
            ConversionAssumption(
                field="ph",
                assumed_value=DEFAULT_PH,
                reason="pH not measured; using application default",
            )
        )

    full_state = FullInfluentStateOverrides(
        X_ch=X_ch,
        X_pr=X_pr,
        X_li=X_li,
        X_I=X_I,
        S_su=S_su,
        S_aa=S_aa,
        S_fa=S_fa,
        S_I=S_I,
        S_ac=S_ac,
        S_pro=S_pro,
        S_h2=S_h2,
        S_IN=S_IN,
        S_IC=S_IC,
        ph=state_ph,
    )

    # ------------------------------------------------------------------
    # 4. Collapse to reduced feed values
    # ------------------------------------------------------------------
    particulate_cod = X_ch + X_pr + X_li + X_I
    soluble_cod = S_su + S_aa + S_fa + S_I

    # Inorganic nitrogen for reduced feed
    if S_IN is not None:
        feed_inorganic_nitrogen = S_IN
    else:
        feed_inorganic_nitrogen = DEFAULT_INORGANIC_NITROGEN_KGN_M3

    # Alkalinity for reduced feed
    if inp.alkalinity_meq_l is not None:
        feed_alkalinity = inp.alkalinity_meq_l * ALKALINITY_MEQ_L_TO_LEGACY
    else:
        feed_alkalinity = DEFAULT_ALKALINITY
        assumptions.append(
            ConversionAssumption(
                field="alkalinity",
                assumed_value=DEFAULT_ALKALINITY,
                reason="Alkalinity not measured; using application default",
            )
        )

    # pH for reduced feed (clamped measured or default)
    feed_ph = ph_measured if ph_measured is not None else DEFAULT_PH

    reduced = ReducedFeedValues(
        particulate_cod=particulate_cod,
        soluble_cod=soluble_cod,
        acetate=S_ac,
        propionate=S_pro,
        hydrogen=S_h2,
        inorganic_nitrogen=feed_inorganic_nitrogen,
        alkalinity=feed_alkalinity,
        sic_kmol_m3=S_IC,
        ph=feed_ph,
        name=inp.sample_name,
    )

    return ConversionResult(
        composition_input=inp,
        derived_values=derived,
        full_influent_state_overrides=full_state,
        reduced_feed_values=reduced,
        assumptions_used=assumptions,
        warnings=warnings,
    )
