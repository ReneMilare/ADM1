from __future__ import annotations

import numpy as np
import pytest

from simulator.core.models import FeedDefinition, KineticParameters, OperatingConditions, ReactorConfig
from simulator.full_model.asm_adm1_interface import ASM1State, asm1_to_adm1_influent, verify_asm1_adm1_balance
from simulator.reactor_models.base import ReactorBase


@pytest.mark.parametrize('snd,xnd,snh', [(10.0, 30.0, 20.0), (0.0, 0.0, 0.0), (100.0, 300.0, 40.0)])
def test_interface_conserves_cod_and_total_kjeldahl_nitrogen(snd: float, xnd: float, snh: float) -> None:
    feed = ASM1State(100, 30, 200, 20, 50, 10, 15, snd, xnd, snh, 0, 5)
    out = asm1_to_adm1_influent(feed)
    cod_in = (100 + 30 + 200 + 20 + 50 + 10 + 15) / 1000
    cod_out = sum(out.get(k, 0) for k in ('S_su', 'S_aa', 'S_I', 'X_ch', 'X_pr', 'X_li', 'X_xc', 'X_I'))
    n_in = (snd + xnd + snh + 0.08 * (50 + 10) + 0.06 * (15 + 20)) / 14000
    n_out = out['S_IN'] + 0.007 * (out['S_aa'] + out['X_pr']) + 0.06 / 14 * (out['S_I'] + out['X_I']) + 0.0376 / 14 * out['X_xc']
    assert abs(cod_in - cod_out) < 1e-9
    assert abs(n_in - n_out) < 1e-9
    assert out['S_IN'] >= 0
    assert verify_asm1_adm1_balance(feed, out)['n_error_pct'] < 1e-9
    if snd == xnd == snh == 0:
        assert out['S_aa'] == 0
        assert out['S_I'] == 0


def test_feed_soluble_cod_does_not_double_count_vfa() -> None:
    feed = FeedDefinition(soluble_cod=5, acetate=1, propionate=2)
    state = feed.to_state_vector()
    assert sum(state[1:4]) == pytest.approx(feed.soluble_cod)


@pytest.mark.parametrize('washout', [1.0, 0.25])
def test_effluent_cod_counts_hydrogen_and_washed_out_biomass(washout: float) -> None:
    reactor = ReactorBase(ReactorConfig(biomass_washout_factor=washout))
    state = np.array([[1., 2., 3., 4., 5., 6., 7., 8., 9., 1., 4.]])
    result = reactor.summarize_profiles(state, feed=FeedDefinition(), operating_conditions=OperatingConditions(), parameters=KineticParameters())
    assert result['effluent_cod'][0] == pytest.approx(15 + washout * 30)
