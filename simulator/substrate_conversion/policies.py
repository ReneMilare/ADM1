"""
Stoichiometric factors, default values, and conversion constants used by the
substrate-composition-to-ADM1 converter.

Unit convention
---------------
All % values are on a wet-mass basis (g per 100 g wet sample).
Density is assumed to be ~1000 kg/m³, so 1 %wet = 10 kg/m³ of that fraction.
Multiplying by the COD factor gives kgCOD/m³.

Example
-------
    X_pr [kgCOD/m³] = protein_pct * PCT_TO_KG_PER_M3 * PROTEIN_COD_FACTOR

Collapsed COD formulas (implemented in service.py)
---------------------------------------------------
    particulate_cod = X_ch + X_pr + X_li + X_I
    soluble_cod     = S_su + S_aa + S_fa + S_I
"""

# ---------------------------------------------------------------------------
# Wet-% to kg/m³ base factor
# ---------------------------------------------------------------------------

PCT_TO_KG_PER_M3 = 10.0  # 1 %wet × 10 = 10 kg/m³ (density ≈ 1000 kg/m³)

# ---------------------------------------------------------------------------
# COD equivalent factors (kgCOD / kgVS)
# ---------------------------------------------------------------------------

PROTEIN_COD_FACTOR = 1.42       # Buswell-like average for amino acids
LIPIDS_COD_FACTOR = 2.90        # Average lipid Buswell factor
CELLULOSE_COD_FACTOR = 1.19     # C₆H₁₀O₅ stoichiometry
LIGNIN_COD_FACTOR = 1.92        # Lignin treated as inert (X_I)
FAST_CARB_COD_FACTOR = 1.07    # Simple sugars (other_carbohydrates → S_su)

# ---------------------------------------------------------------------------
# Default values (mirrors FeedDefinition defaults for unmeasured fields)
# ---------------------------------------------------------------------------

DEFAULT_PH = 7.0
DEFAULT_ALKALINITY = 4.0            # Legacy equivalent scale
DEFAULT_INORGANIC_NITROGEN_KGN_M3 = 1.0  # kgN/m³

# ---------------------------------------------------------------------------
# Unit conversion factors
# ---------------------------------------------------------------------------

# TAN (mg N/L) → kgN/m³
# TAN is already expressed as N, so: mg N/L × 1e-3 = g N/L = kgN/m³ × 1e-3
# i.e. kgN/m³ = tan_mg_l × TAN_MG_L_TO_KGN_M3
TAN_MG_L_TO_KGN_M3 = 1e-3

# Alkalinity (mEq/L) → legacy scale used by FeedDefinition
# Approximation: 1 mEq/L HCO₃⁻ ≈ 50 mg/L as CaCO₃; legacy scale ≈ g/L range
ALKALINITY_MEQ_L_TO_LEGACY = 0.05

# ---------------------------------------------------------------------------
# Validation thresholds
# ---------------------------------------------------------------------------

MAX_PCT = 100.0
MIN_PCT = 0.0
ORGANIC_CLOSURE_TOLERANCE = 1e-6  # Numerical tolerance for fraction-sum check
