from __future__ import annotations

from dataclasses import replace

import pytest

from simulator.full_model.acid_base import solve_acid_base
from simulator.full_model.asm_adm1_interface import ASM1State, asm1_to_adm1_influent, verify_asm1_adm1_balance
from simulator.tests.test_extensions import _make_params


def _asm(**updates: float) -> ASM1State:
    state = ASM1State(S_S=100.0, S_I=30.0, X_S=200.0, X_I=50.0,
                      X_BH=300.0, X_BA=40.0, X_P=80.0,
                      S_ND=2.0, X_ND=4.0, S_NH=20.0, S_NO=5.0, S_ALK=4.0)
    return replace(state, **updates)


def _cod(influent: dict[str, float]) -> float:
    return sum(influent[name] for name in ("S_su", "S_aa", "S_I", "X_ch", "X_pr", "X_li", "X_xc", "X_I"))


def test_nitrate_consumes_cod_and_reports_n2_without_losing_nitrogen():
    state = _asm()
    influent = asm1_to_adm1_influent(state)
    baseline = asm1_to_adm1_influent(replace(state, S_NO=0.0))
    assert _cod(baseline) - _cod(influent) == pytest.approx(5.0 * 2.86 / 1000)
    balance = verify_asm1_adm1_balance(state, influent)
    assert balance["n2_lost_kmol_n_m3"] == pytest.approx(5 / 14000)
    assert balance["cod_oxidized_kg_m3"] == pytest.approx(5 * 2.86 / 1000)
    assert balance["cod_error_pct"] < 1e-12
    assert balance["n_error_pct"] < 1e-12
    tampered = {**influent, "S_IN": influent["S_IN"] + 0.001}
    assert verify_asm1_adm1_balance(state, tampered)["n_error_pct"] > 1
    tampered = {**influent, "S_su": influent["S_su"] + 0.1}
    assert verify_asm1_adm1_balance(state, tampered)["cod_error_pct"] > 1


@pytest.mark.parametrize("oxygen", [1.0, 110.0, 350.0, 620.0])
def test_oxygen_and_nitrate_consume_donors_in_order_and_preserve_tkn(oxygen):
    state = _asm(S_O=oxygen)
    influent = asm1_to_adm1_influent(state)
    demand = oxygen + state.S_NO * 2.86
    baseline = asm1_to_adm1_influent(replace(state, S_O=0.0, S_NO=0.0))
    assert _cod(baseline) - _cod(influent) == pytest.approx(demand / 1000)
    ss = max(100 - demand, 0)
    xs = max(200 - max(demand - 100, 0), 0)
    bh = max(300 - max(demand - 300, 0), 0)
    ba = max(40 - max(demand - 600, 0), 0)
    expected = asm1_to_adm1_influent(replace(state, S_S=ss, X_S=xs, X_BH=bh, X_BA=ba,
                                           S_O=0.0, S_NO=0.0,
                                           S_NH=20 + 0.08 * (340 - bh - ba),
                                           S_ALK=4 + state.S_NO / 14))
    assert influent == pytest.approx(expected)
    balance = verify_asm1_adm1_balance(state, influent)
    assert balance["cod_error_pct"] < 1e-12
    assert balance["n_error_pct"] < 1e-12


def test_unrepresentable_acceptors_rejected_when_biodegradable_cod_insufficient():
    with pytest.raises(ValueError, match="DQO"):
        asm1_to_adm1_influent(_asm(S_O=1000.0))


def test_no_acceptors_leave_asm_donors_and_nitrogen_unchanged():
    from simulator.full_model.asm_adm1_interface import _remove_electron_acceptors

    state = _asm(S_NO=0.0, S_NH=0.0, X_BH=0.1, X_BA=0.2)
    converted, oxidized = _remove_electron_acceptors(state)
    assert converted == state
    assert oxidized == 0.0


@pytest.mark.parametrize("name,value", [("S_O", -1.0), ("S_NO", -1.0), ("S_O", float("nan")),
                                       ("S_O", float("inf")), ("X_S", -1.0)])
def test_invalid_acceptors_and_donors_are_rejected(name, value):
    with pytest.raises(ValueError, match=name):
        asm1_to_adm1_influent(_asm(**{name: value}))


def test_charge_balanced_at_nominal_ph_after_denitrification():
    state = _asm()
    influent = asm1_to_adm1_influent(state)
    params = _make_params([])
    full = {name: 0.0 for name in ("S_va", "S_bu", "S_pro", "S_ac")}
    acid = solve_acid_base({**full, **influent}, params)
    assert acid.converged
    assert acid.p_h == pytest.approx(7.0, abs=1e-5)
    assert influent["S_IC"] == pytest.approx((state.S_ALK + state.S_NO / 14) / 1000)
    assert min(influent["S_cation"], influent["S_anion"]) == 0.0


def test_mcp_exposes_oxygen_and_exported_n2():
    import asyncio
    import json

    from pydantic import ValidationError
    from simulator.mcp_server import _ConvertASM1Params, convert_asm1_to_adm1_influent

    request = _ConvertASM1Params(S_O=10.0)
    payload = json.loads(asyncio.run(convert_asm1_to_adm1_influent(request)))
    assert payload["balance_check"]["cod_oxidized_kg_m3"] == pytest.approx((10 + 5 * 2.86) / 1000)
    assert payload["balance_check"]["n2_lost_kmol_n_m3"] == pytest.approx(5 / 14000)
    assert payload["balance_check"]["n_error_pct"] < 1e-12
    assert payload["balance_check"]["cod_error_pct"] < 1e-12
    with pytest.raises(ValidationError):
        request.S_O = -1.0
    with pytest.raises(ValidationError):
        _ConvertASM1Params(unknown=1)
