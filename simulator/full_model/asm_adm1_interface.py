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
  - Alkalinity S_ALK (mol HCO3-/m³) is used as a proxy for S_IC.
  - S_NO3 is treated as a conservative anion (S_anion contribution).
  - Ammonium charge is computed from S_IN by the ADM1 charge balance.

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
        fractions: Optional carbohydrate/lipid ratio for residual X_S COD.
            Protein and amino acid allocation is determined by available nitrogen.

    Returns:
        Dictionary of ADM1 influent state names and values in ADM1 units.
    """
    # Nopens et al. (2009), section 4.1: allocate N to amino acids and
    # proteins before mapping the residual N to soluble inerts and S_IN.
    n_aa = 0.007
    n_i = 0.06 / 14.0
    snd, xnd, nh = (asm1.S_ND / 14000.0, asm1.X_ND / 14000.0, asm1.S_NH / 14000.0)
    ss, xs = asm1.S_S / 1000.0, asm1.X_S / 1000.0
    s_aa = min(ss, snd / n_aa)
    snd -= s_aa * n_aa
    s_su = ss - s_aa
    x_pr = min(xs, xnd / n_aa)
    xnd -= x_pr * n_aa
    xs_remainder = xs - x_pr
    lipid_fraction = 0.7
    if fractions is not None:
        nonprotein = fractions.f_ch_Xs + fractions.f_li_Xs
        if nonprotein > 0:
            lipid_fraction = fractions.f_li_Xs / nonprotein
    x_li = lipid_fraction * xs_remainder
    x_ch = (1.0 - lipid_fraction) * xs_remainder

    biomass = (asm1.X_BH + asm1.X_BA) / 1000.0
    inert_biomass = 0.32 * biomass
    biomass_n = 0.08 / 14.0 * biomass - n_i * inert_biomass
    degradable = 0.68 * biomass
    biomass_protein = min(degradable, (biomass_n + xnd) / n_aa)
    used_xnd = max(0.0, biomass_protein * n_aa - biomass_n)
    xnd -= used_xnd
    biomass_n = max(0.0, biomass_n - biomass_protein * n_aa)
    x_pr += biomass_protein
    x_ch += 0.6 * (degradable - biomass_protein)
    x_li += 0.4 * (degradable - biomass_protein)
    x_i_adm1 = (asm1.X_I + asm1.X_P) / 1000.0 + inert_biomass
    x_xc = 0.0

    available_n = snd + xnd + nh + biomass_n
    s_i_adm1 = min(asm1.S_I / 1000.0, available_n / n_i)
    x_ch += asm1.S_I / 1000.0 - s_i_adm1
    s_in = available_n - s_i_adm1 * n_i

    # --- Inorganic carbon (mol HCO3-/m³ → kmolC/m³, divide by 1000) ---
    # Alkalinity ≈ [HCO3-] at typical digester pH range (6-8).
    # S_IC in ADM1 is total dissolved inorganic carbon; we approximate S_IC ≈ S_ALK.
    s_ic = asm1.S_ALK / 1000.0

    # --- Charge balance ions (kmol/m³) ---
    # ADM1 accounts for NH4+ through S_IN - S_NH3. At pH 7 and pKa 9.25,
    # approximately 99.4% of inorganic ammonia is NH4+.
    s_cation = 0.0

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
    COD and total Kjeldahl nitrogen include organic ADM1 pools.

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
        + sum(adm1_influent.get(name, 0.0) for name in
              ("S_fa", "S_va", "S_bu", "S_pro", "S_ac", "S_h2", "S_ch4"))
        + adm1_influent.get("S_I", 0.0)
        + adm1_influent.get("X_ch", 0.0)
        + adm1_influent.get("X_pr", 0.0)
        + adm1_influent.get("X_li", 0.0)
        + adm1_influent.get("X_xc", 0.0)
        + adm1_influent.get("X_I", 0.0)
        + sum(adm1_influent.get(name, 0.0) for name in
              ("X_su", "X_aa", "X_fa", "X_c4", "X_pro", "X_ac", "X_h2"))
    )

    cod_error_pct = (
        abs(cod_total_asm1 - cod_total_adm1) / max(cod_total_asm1, 1e-9) * 100.0
    )

    # Nopens et al. (2009), Table 2: ASM1 inerts use 0.06 kg N/kg COD,
    # biomass uses 0.08, and soluble inerts contain no N.
    tkn_asm1 = (asm1.S_NH + asm1.S_ND + asm1.X_ND
                + 0.08 * (asm1.X_BH + asm1.X_BA)
                + 0.06 * (asm1.X_I + asm1.X_P)) / 14000.0
    n_adm1 = (adm1_influent.get("S_IN", 0.0)
              + 0.007 * (adm1_influent.get("S_aa", 0.0) + adm1_influent.get("X_pr", 0.0))
              + 0.06 / 14.0 * (adm1_influent.get("S_I", 0.0) + adm1_influent.get("X_I", 0.0))
              + 0.0376 / 14.0 * adm1_influent.get("X_xc", 0.0)
              + 0.08 / 14.0 * sum(adm1_influent.get(name, 0.0) for name in
                                  ("X_su", "X_aa", "X_fa", "X_c4", "X_pro", "X_ac", "X_h2")))

    n_error_pct = abs(tkn_asm1 - n_adm1) / max(tkn_asm1, 1e-9) * 100.0

    return {
        "cod_error_pct": float(cod_error_pct),
        "n_error_pct": float(n_error_pct),
    }
