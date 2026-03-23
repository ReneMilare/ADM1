"""ASM1 → ADM1 fractionation parameters (BSM2 defaults and sludge-type presets).

Defines the fractionation factors that distribute ASM1 COD pools into ADM1
substrate categories following the BSM2 interface (Nopens et al. 2009).

Two constraints must always hold:
    f_su_Ss + f_aa_Ss          = 1.0   (S_S fractions)
    f_ch_Xs + f_pr_Xs + f_li_Xs = 1.0  (X_S fractions)

Reference:
    Nopens I, Batstone DJ, Copp JB, Jeppsson U, Volcke E, Alex J, Vanrolleghem PA
    (2009). "An ASM/ADM model interface for dynamic plant-wide simulation."
    Water Research 43(7):1913–1923. doi:10.1016/j.watres.2009.01.012

    Alex J et al. (2008). Benchmark Simulation Model No. 2 (BSM2). IWA Task Group.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ASM1ToADM1Fractions:
    """Fractionation factors for distributing ASM1 COD pools into ADM1 substrates.

    Defaults follow BSM2 interface (Nopens et al. 2009, Table 1).

    S_S splits into soluble sugars (S_su) and amino acids (S_aa).
    X_S splits into particulate carbohydrates (X_ch), proteins (X_pr), lipids (X_li).

    Constraint: f_su_Ss + f_aa_Ss = 1.0 and f_ch_Xs + f_pr_Xs + f_li_Xs = 1.0.
    """

    f_su_Ss: float = 0.75    # Fraction of S_S → S_su (sugars)
    f_aa_Ss: float = 0.25    # Fraction of S_S → S_aa (amino acids)
    f_ch_Xs: float = 0.275   # Fraction of X_S → X_ch (carbohydrates)
    f_pr_Xs: float = 0.275   # Fraction of X_S → X_pr (proteins)
    f_li_Xs: float = 0.45    # Fraction of X_S → X_li (lipids)


# ---------------------------------------------------------------------------
# Presets by sludge type (calibrated from literature)
# ---------------------------------------------------------------------------

def bsm2_fractions() -> ASM1ToADM1Fractions:
    """BSM2 default fractions for mixed municipal sludge (Nopens et al. 2009)."""
    return ASM1ToADM1Fractions(
        f_su_Ss=0.75, f_aa_Ss=0.25,
        f_ch_Xs=0.275, f_pr_Xs=0.275, f_li_Xs=0.45,
    )


def primary_sludge_fractions() -> ASM1ToADM1Fractions:
    """Fractions for raw primary sludge.

    Higher lipid fraction (fat/grease from kitchen/food waste) and lower
    protein fraction compared to secondary sludge.
    Calibrated from Nopens et al. (2009) and Batstone et al. (2002).
    """
    return ASM1ToADM1Fractions(
        f_su_Ss=0.80, f_aa_Ss=0.20,   # more sugars, less amino acids
        f_ch_Xs=0.25, f_pr_Xs=0.25, f_li_Xs=0.50,  # higher lipids
    )


def secondary_sludge_fractions() -> ASM1ToADM1Fractions:
    """Fractions for waste activated sludge (WAS) from aerobic secondary treatment.

    Higher protein fraction (bacterial biomass is ~55% protein by mass).
    Lower lipid fraction compared to primary sludge.
    Calibrated from Nopens et al. (2009) and Batstone et al. (2002).
    """
    return ASM1ToADM1Fractions(
        f_su_Ss=0.70, f_aa_Ss=0.30,   # more amino acids from cell lysis
        f_ch_Xs=0.25, f_pr_Xs=0.40, f_li_Xs=0.35,  # higher proteins
    )
