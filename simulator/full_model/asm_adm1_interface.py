"""E14 — Interface ASM1 ↔ ADM1 (BSM2 interface).

Provides utility functions to convert a vector of ASM1 state variables into
the influent_values dict expected by FullCSTRRhs (ADM1 full model), enabling
integrated plant simulation where the primary clarifier effluent (ASM1 output)
feeds directly into the anaerobic digester (ADM1 input).

This interface follows the methodology of the Benchmark Simulation Model No. 2
(BSM2), which couples the IWA Activated Sludge Model No. 1 (ASM1) with IWA
ADM1 at the primary sludge/WAS feed point.

Key assumptions:
  - ASM1 state units are g/m³ (gCOD/m³ for organic fractions, gN/m³ for nitrogen).
  - ADM1 output units: kgCOD/m³ for COD fractions, kmol/m³ for inorganic species.
  - Biomass fractions (X_BH, X_BA, X_P) are lumped into X_xc (composite particulate).
  - Alkalinity S_ALK (mol HCO3-/m³) is used as a proxy for S_IC.
  - Inorganic nitrogen S_IN is derived from S_NH only (organic N ignored in S_IN;
    S_ND and X_ND remain in the particulate/soluble pools but are not individually
    tracked in ADM1 core).
  - S_NO3 is treated as a conservative anion (S_anion contribution).
  - Ion charge balance uses typical pH 7 speciation: 90% NH4+, 10% NH3.

Reference:
    Nopens I, Batstone DJ, Copp JB, Jeppsson U, Volcke E, Alex J, Vanrolleghem PA
    (2009). "An ASM/ADM model interface for dynamic plant-wide simulation."
    Water Research 43(7):1913–1923. doi:10.1016/j.watres.2009.01.012

    Alex J, Benedetti L, Copp JB, Gernaey KV, Jeppsson U, Nopens I, Pons MN,
    Rosen C, Steyer JP, Vanrolleghem PA (2008). Benchmark Simulation Model No. 2
    (BSM2). IWA Task Group on Benchmarking of Control Strategies for WWTPs.
"""
from __future__ import annotations

from dataclasses import dataclass

from simulator.full_model.mappings.asm1_fractions import ASM1ToADM1Fractions  # re-exported


@dataclass
class ASM1State:
    """State vector of IWA ASM1.

    All concentrations in g/m³ (= mg/L).
    COD fractions (S_S, S_I, X_S, X_I, X_BH, X_BA, X_P) are in gCOD/m³.
    Nitrogen fractions (S_ND, X_ND, S_NH, S_NO) are in gN/m³.
    S_ALK is alkalinity in mol HCO3-/m³.
    """

    S_S: float    # Readily biodegradable soluble substrate (gCOD/m³)
    S_I: float    # Soluble inert organic matter (gCOD/m³)
    X_S: float    # Slowly biodegradable particulate substrate (gCOD/m³)
    X_I: float    # Particulate inert organic matter (gCOD/m³)
    X_BH: float   # Active heterotrophic biomass (gCOD/m³)
    X_BA: float   # Active autotrophic (nitrifying) biomass (gCOD/m³)
    X_P: float    # Particulate products from biomass decay (gCOD/m³)
    S_ND: float   # Soluble biodegradable organic nitrogen (gN/m³)
    X_ND: float   # Particulate biodegradable organic nitrogen (gN/m³)
    S_NH: float   # Free and saline ammonia (gN/m³)
    S_NO: float   # Nitrate and nitrite nitrogen (gN/m³)
    S_ALK: float  # Alkalinity (mol HCO3-/m³)


# ASM1ToADM1Fractions is defined in mappings/asm1_fractions.py and re-exported
# here to keep the public API stable (importers of asm_adm1_interface still work).
__all__ = ["ASM1State", "ASM1ToADM1Fractions", "asm1_to_adm1_influent", "verify_asm1_adm1_balance"]


def asm1_to_adm1_influent(
    asm1: ASM1State,
    fractions: ASM1ToADM1Fractions | None = None,
) -> dict[str, float]:
    """Convert an ASM1 state vector to ADM1 influent_values for FullCSTRRhs.

    Follows the BSM2 interface methodology (Nopens et al. 2009).

    Units of output:
      - kgCOD/m³ for COD fractions (S_su, S_aa, S_I, X_ch, X_pr, X_li, X_xc, X_I)
      - kmolN/m³ for inorganic nitrogen (S_IN)
      - kmolC/m³ for inorganic carbon (S_IC)
      - kmol/m³ for charge-balance ions (S_cation, S_anion)

    Args:
        asm1: ASM1 state vector (concentrations in g/m³).
        fractions: COD fractionation factors. Defaults to BSM2 values.

    Returns:
        Dictionary of ADM1 influent state names and values in ADM1 units.
    """
    if fractions is None:
        fractions = ASM1ToADM1Fractions()

    # --- Soluble COD fractions (g/m³ → kgCOD/m³, divide by 1000) ---
    s_su = fractions.f_su_Ss * asm1.S_S / 1000.0
    s_aa = fractions.f_aa_Ss * asm1.S_S / 1000.0
    s_i_adm1 = asm1.S_I / 1000.0

    # --- Particulate COD fractions (g/m³ → kgCOD/m³) ---
    # X_S distributed into carbohydrates, proteins, lipids
    x_ch = fractions.f_ch_Xs * asm1.X_S / 1000.0
    x_pr = fractions.f_pr_Xs * asm1.X_S / 1000.0
    x_li = fractions.f_li_Xs * asm1.X_S / 1000.0

    # Biomass (active + endogenous residue) lumped into composite particulate X_xc.
    # This is degradable in ADM1 via disintegration (rho_1).
    x_xc = (asm1.X_BH + asm1.X_BA + asm1.X_P) / 1000.0

    # Particulate inerts pass through as X_I
    x_i_adm1 = asm1.X_I / 1000.0

    # --- Inorganic nitrogen (gN/m³ → kmolN/m³, divide by 14*1000) ---
    # ADM1 S_IN = total inorganic nitrogen (NH4+ + NH3).
    # S_ND and X_ND are organic N embedded in soluble/particulate fractions;
    # they do not directly contribute to S_IN (they will be released via hydrolysis
    # in ADM1). This is a known simplification of the BSM2 interface.
    s_in = asm1.S_NH / (14.0 * 1000.0)

    # --- Inorganic carbon (mol HCO3-/m³ → kmolC/m³, divide by 1000) ---
    # Alkalinity ≈ [HCO3-] at typical digester pH range (6-8).
    # S_IC in ADM1 is total dissolved inorganic carbon; we approximate S_IC ≈ S_ALK.
    s_ic = asm1.S_ALK / 1000.0

    # --- Charge balance ions (kmol/m³) ---
    # S_cation: NH4+ represents the dominant cation from ammonia at pH 7.
    # At pH 7.0, ~90% of S_NH is NH4+ (pKa NH4+/NH3 ≈ 9.25 at 25°C).
    s_cation = asm1.S_NH / (14.0 * 1000.0) * 0.9

    # S_anion: NO3- is a conservative anion in the digester (anaerobic conditions
    # consume it rapidly, but as an influent it contributes to charge balance).
    s_anion = asm1.S_NO / (14.0 * 1000.0)

    return {
        "S_su": s_su,
        "S_aa": s_aa,
        "S_I": s_i_adm1,
        "X_ch": x_ch,
        "X_pr": x_pr,
        "X_li": x_li,
        "X_xc": x_xc,
        "X_I": x_i_adm1,
        "S_IN": s_in,
        "S_IC": s_ic,
        "S_cation": s_cation,
        "S_anion": s_anion,
    }


def verify_asm1_adm1_balance(
    asm1: ASM1State,
    adm1_influent: dict[str, float],
) -> dict[str, float]:
    """Verify COD and nitrogen conservation across the ASM1→ADM1 interface.

    Returns percentage errors for COD and nitrogen balances.
    Small errors (< 1%) are expected when f_ch + f_pr + f_li = 1.0 and f_su + f_aa = 1.0.
    Large nitrogen errors are expected because S_ND and X_ND are not included in S_IN.

    Args:
        asm1: Original ASM1 state vector (g/m³).
        adm1_influent: ADM1 influent dict produced by asm1_to_adm1_influent (kgCOD/m³).

    Returns:
        Dictionary with 'cod_error_pct' and 'n_error_pct' (both ≥ 0, in percent).
    """
    # Total COD in ASM1 side (gCOD/m³ → kgCOD/m³)
    cod_total_asm1 = (
        asm1.S_S + asm1.S_I + asm1.X_S + asm1.X_I
        + asm1.X_BH + asm1.X_BA + asm1.X_P
    ) / 1000.0

    # Total COD in ADM1 side (kgCOD/m³)
    cod_total_adm1 = (
        adm1_influent.get("S_su", 0.0)
        + adm1_influent.get("S_aa", 0.0)
        + adm1_influent.get("S_I", 0.0)
        + adm1_influent.get("X_ch", 0.0)
        + adm1_influent.get("X_pr", 0.0)
        + adm1_influent.get("X_li", 0.0)
        + adm1_influent.get("X_xc", 0.0)
        + adm1_influent.get("X_I", 0.0)
    )

    cod_error_pct = (
        abs(cod_total_asm1 - cod_total_adm1) / max(cod_total_asm1, 1e-9) * 100.0
    )

    # Total Kjeldahl nitrogen in ASM1 side (gN/m³ → kmolN/m³)
    # TKN = S_NH + S_ND + X_ND (free ammonia + soluble + particulate organic N)
    tkn_asm1 = (asm1.S_NH + asm1.S_ND + asm1.X_ND) / (14.0 * 1000.0)

    # ADM1 S_IN = only inorganic N (organic N embedded in COD fractions, not tracked here)
    n_adm1 = adm1_influent.get("S_IN", 0.0)

    n_error_pct = abs(tkn_asm1 - n_adm1) / max(tkn_asm1, 1e-9) * 100.0

    return {
        "cod_error_pct": float(cod_error_pct),
        "n_error_pct": float(n_error_pct),
    }
