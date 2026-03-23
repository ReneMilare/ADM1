"""Tests for the ASM1→ADM1 interface (E14).

Tests validate:
  1. asm1_to_adm1_influent returns all expected ADM1 keys
  2. COD balance error < 1% when fractions sum to 1.0
  3. S_S fractions sum to 1.0 (f_su_Ss + f_aa_Ss == 1.0)
  4. X_S fractions sum to 1.0 (f_ch_Xs + f_pr_Xs + f_li_Xs == 1.0)
  5. ASM1State with all zeros returns influent without NaN or errors
  6. verify_asm1_adm1_balance returns a dict with cod_error_pct and n_error_pct
"""
from __future__ import annotations

import math

import pytest

from simulator.full_model.asm_adm1_interface import (
    ASM1State,
    ASM1ToADM1Fractions,
    asm1_to_adm1_influent,
    verify_asm1_adm1_balance,
)

_EXPECTED_KEYS = {
    "S_su", "S_aa", "S_I",
    "X_ch", "X_pr", "X_li", "X_xc", "X_I",
    "S_IN", "S_IC", "S_cation", "S_anion",
}


def _typical_asm1() -> ASM1State:
    """Return a typical municipal wastewater ASM1 state (g/m³ = mg/L)."""
    return ASM1State(
        S_S=100.0,    # 100 mg/L readily biodegradable COD
        S_I=30.0,     # 30 mg/L soluble inert COD
        X_S=200.0,    # 200 mg/L slowly biodegradable COD
        X_I=50.0,     # 50 mg/L particulate inert COD
        X_BH=300.0,   # 300 mg/L active heterotrophic biomass
        X_BA=40.0,    # 40 mg/L active autotrophic biomass
        X_P=80.0,     # 80 mg/L endogenous residue
        S_ND=2.0,     # 2 mg/L soluble organic N
        X_ND=4.0,     # 4 mg/L particulate organic N
        S_NH=20.0,    # 20 mg/L ammonia-N
        S_NO=5.0,     # 5 mg/L nitrate-N
        S_ALK=4.0,    # 4 mol HCO3-/m³ (approx. 200 mg/L as CaCO3)
    )


class TestAsmAdm1Keys:
    def test_returns_all_expected_keys(self):
        asm1 = _typical_asm1()
        result = asm1_to_adm1_influent(asm1)
        assert _EXPECTED_KEYS <= set(result.keys()), (
            f"Missing keys: {_EXPECTED_KEYS - set(result.keys())}"
        )

    def test_no_nan_in_output(self):
        asm1 = _typical_asm1()
        result = asm1_to_adm1_influent(asm1)
        for key, val in result.items():
            assert not math.isnan(val), f"{key} = NaN"
            assert not math.isinf(val), f"{key} = Inf"

    def test_all_values_nonnegative(self):
        asm1 = _typical_asm1()
        result = asm1_to_adm1_influent(asm1)
        for key, val in result.items():
            assert val >= 0.0, f"{key} = {val} < 0"


class TestFractionSums:
    def test_default_ss_fractions_sum_to_one(self):
        fracs = ASM1ToADM1Fractions()
        total = fracs.f_su_Ss + fracs.f_aa_Ss
        assert abs(total - 1.0) < 1e-10, f"f_su_Ss + f_aa_Ss = {total} ≠ 1.0"

    def test_default_xs_fractions_sum_to_one(self):
        fracs = ASM1ToADM1Fractions()
        total = fracs.f_ch_Xs + fracs.f_pr_Xs + fracs.f_li_Xs
        assert abs(total - 1.0) < 1e-10, f"f_ch + f_pr + f_li = {total} ≠ 1.0"


class TestCODBalance:
    def test_cod_balance_error_lt_1pct_with_default_fractions(self):
        """COD balance should be exact when all fractions sum to 1.0."""
        asm1 = _typical_asm1()
        fracs = ASM1ToADM1Fractions()
        assert abs(fracs.f_su_Ss + fracs.f_aa_Ss - 1.0) < 1e-10
        assert abs(fracs.f_ch_Xs + fracs.f_pr_Xs + fracs.f_li_Xs - 1.0) < 1e-10

        result = asm1_to_adm1_influent(asm1, fracs)
        balance = verify_asm1_adm1_balance(asm1, result)
        assert balance["cod_error_pct"] < 1.0, (
            f"COD error {balance['cod_error_pct']:.3f}% exceeds 1%"
        )

    def test_cod_balance_custom_fractions(self):
        """Custom fractions that sum exactly to 1.0 should also balance."""
        asm1 = _typical_asm1()
        fracs = ASM1ToADM1Fractions(
            f_su_Ss=0.6, f_aa_Ss=0.4,
            f_ch_Xs=0.33, f_pr_Xs=0.33, f_li_Xs=0.34,
        )
        result = asm1_to_adm1_influent(asm1, fracs)
        balance = verify_asm1_adm1_balance(asm1, result)
        assert balance["cod_error_pct"] < 1.0


class TestZeroInput:
    def test_zero_asm1_state_returns_no_nan(self):
        asm1 = ASM1State(
            S_S=0.0, S_I=0.0, X_S=0.0, X_I=0.0,
            X_BH=0.0, X_BA=0.0, X_P=0.0,
            S_ND=0.0, X_ND=0.0, S_NH=0.0, S_NO=0.0,
            S_ALK=0.0,
        )
        result = asm1_to_adm1_influent(asm1)
        for key, val in result.items():
            assert not math.isnan(val), f"{key} = NaN for all-zero input"
        # All outputs should be zero for zero input
        for key, val in result.items():
            assert val == pytest.approx(0.0), f"{key} = {val} ≠ 0 for zero input"

    def test_zero_balance_returns_no_nan(self):
        asm1 = ASM1State(
            S_S=0.0, S_I=0.0, X_S=0.0, X_I=0.0,
            X_BH=0.0, X_BA=0.0, X_P=0.0,
            S_ND=0.0, X_ND=0.0, S_NH=0.0, S_NO=0.0,
            S_ALK=0.0,
        )
        result = asm1_to_adm1_influent(asm1)
        balance = verify_asm1_adm1_balance(asm1, result)
        # With zero input, errors should be 0% (no division by zero because of max guard)
        assert not math.isnan(balance["cod_error_pct"])
        assert not math.isnan(balance["n_error_pct"])


class TestUnitConversions:
    def test_s_su_unit_conversion(self):
        """S_su = f_su_Ss * S_S / 1000 (g/m³ → kgCOD/m³)."""
        asm1 = ASM1State(
            S_S=1000.0, S_I=0.0, X_S=0.0, X_I=0.0,
            X_BH=0.0, X_BA=0.0, X_P=0.0,
            S_ND=0.0, X_ND=0.0, S_NH=0.0, S_NO=0.0,
            S_ALK=0.0,
        )
        fracs = ASM1ToADM1Fractions(f_su_Ss=0.75, f_aa_Ss=0.25)
        result = asm1_to_adm1_influent(asm1, fracs)
        assert result["S_su"] == pytest.approx(0.75, rel=1e-9)   # 0.75 * 1000 / 1000
        assert result["S_aa"] == pytest.approx(0.25, rel=1e-9)

    def test_s_in_unit_conversion(self):
        """S_IN = S_NH / (14 * 1000)."""
        asm1 = ASM1State(
            S_S=0.0, S_I=0.0, X_S=0.0, X_I=0.0,
            X_BH=0.0, X_BA=0.0, X_P=0.0,
            S_ND=0.0, X_ND=0.0,
            S_NH=14000.0,  # 14000 gN/m³ → 1.0 kmolN/m³
            S_NO=0.0, S_ALK=0.0,
        )
        result = asm1_to_adm1_influent(asm1)
        assert result["S_IN"] == pytest.approx(1.0, rel=1e-9)

    def test_s_ic_unit_conversion(self):
        """S_IC = S_ALK / 1000 (mol/m³ → kmol/m³)."""
        asm1 = ASM1State(
            S_S=0.0, S_I=0.0, X_S=0.0, X_I=0.0,
            X_BH=0.0, X_BA=0.0, X_P=0.0,
            S_ND=0.0, X_ND=0.0, S_NH=0.0, S_NO=0.0,
            S_ALK=4000.0,  # 4000 mol/m³ → 4.0 kmol/m³
        )
        result = asm1_to_adm1_influent(asm1)
        assert result["S_IC"] == pytest.approx(4.0, rel=1e-9)


class TestVerifyBalance:
    def test_returns_cod_and_n_error_keys(self):
        asm1 = _typical_asm1()
        result = asm1_to_adm1_influent(asm1)
        balance = verify_asm1_adm1_balance(asm1, result)
        assert "cod_error_pct" in balance
        assert "n_error_pct" in balance

    def test_errors_are_nonnegative(self):
        asm1 = _typical_asm1()
        result = asm1_to_adm1_influent(asm1)
        balance = verify_asm1_adm1_balance(asm1, result)
        assert balance["cod_error_pct"] >= 0.0
        assert balance["n_error_pct"] >= 0.0

    def test_n_error_high_because_organic_n_not_in_sin(self):
        """N error should be non-trivial because S_ND and X_ND are not in S_IN."""
        asm1 = ASM1State(
            S_S=0.0, S_I=0.0, X_S=0.0, X_I=0.0,
            X_BH=0.0, X_BA=0.0, X_P=0.0,
            S_ND=100.0,   # Significant organic N
            X_ND=100.0,
            S_NH=10.0,    # Small inorganic N
            S_NO=0.0,
            S_ALK=4.0,
        )
        result = asm1_to_adm1_influent(asm1)
        balance = verify_asm1_adm1_balance(asm1, result)
        # With large organic N fractions, S_IN << TKN → large n_error
        assert balance["n_error_pct"] > 0.0
