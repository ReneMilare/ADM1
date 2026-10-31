from __future__ import annotations

import numpy as np
import pytest

import simulator.reactor_models.base as base_module

from simulator.core.kinetics import (
    BIOMASS_INDICES,
    STATE_INDEX,
    _ALK_TO_MOL,
    _COD_TO_MOL_ACETATE,
    _PCO2_ATM,
    _kh_co2,
    _pka_acetate,
    _pka_co2_first,
    estimate_ph,
    reaction_vector,
)
from simulator.core.models import FeedDefinition, InitialState, KineticParameters, OperatingConditions, ReactorConfig, STATE_NAMES
from simulator.reactor_models.base import ReactorBase
from simulator.reactor_models.uasb import UASBReactor


def test_ph_balance_is_independent_of_initial_guess() -> None:
    state = np.zeros(len(STATE_NAMES))
    state[STATE_INDEX["acetate"]] = 1.0
    state[STATE_INDEX["alkalinity"]] = 0.5
    results = [estimate_ph(state, influent_ph=guess, temperature_c=35.0) for guess in (5.0, 8.5)]
    assert results[0] == pytest.approx(4.928, abs=0.001)
    assert results[0] == pytest.approx(results[1], abs=1e-10)
    ph = results[0]
    bicarbonate = _kh_co2(35.0) * _PCO2_ATM * 10 ** (ph - _pka_co2_first(35.0))
    acetate = _COD_TO_MOL_ACETATE / (1 + 10 ** (_pka_acetate(35.0) - ph))
    assert bicarbonate + acetate == pytest.approx(0.5 * _ALK_TO_MOL, abs=1e-9)


def test_ph_balance_with_nearly_zero_alkalinity() -> None:
    state = np.zeros(len(STATE_NAMES))
    ph = estimate_ph(state, influent_ph=7.0, temperature_c=35.0)
    bicarbonate = _kh_co2(35.0) * _PCO2_ATM * 10 ** (ph - _pka_co2_first(35.0))
    assert bicarbonate == pytest.approx(1e-9 * _ALK_TO_MOL, rel=1e-9)


def test_explicit_zero_gas_capture_is_preserved() -> None:
    reactor = UASBReactor(ReactorConfig(reactor_type="uasb", gas_capture_efficiency=0.0))
    assert reactor.gas_capture_efficiency(0) == 0.0


def test_series_biomass_transport_conserves_mass(monkeypatch: pytest.MonkeyPatch) -> None:
    class VaryingRetentionReactor(ReactorBase):
        def biomass_washout_factor(self, segment_index: int) -> float:
            return (0.25, 0.6, 0.8)[segment_index]

    monkeypatch.setattr(base_module, "reaction_vector", lambda state, **kwargs: (np.zeros_like(state), {}))
    reactor = VaryingRetentionReactor(ReactorConfig(reactor_type="plug_flow", segments=3))
    operating = OperatingConditions(volume_m3=3.0, hrt_days=3.0)
    states = np.zeros((3, len(STATE_NAMES)))
    states[:, BIOMASS_INDICES[0]] = [2.0, 3.0, 5.0]
    derivatives = reactor.rhs(0.0, states.ravel(), feed=FeedDefinition(), operating_conditions=operating, parameters=KineticParameters()).reshape(states.shape)
    net_accumulation = sum(derivatives[i, BIOMASS_INDICES[0]] * reactor.segment_volume(i, operating) for i in range(3))
    effluent_flux = (operating.volume_m3 / operating.hrt_days) * 0.8 * 5.0
    assert net_accumulation == pytest.approx(-effluent_flux)


@pytest.mark.parametrize("acid_multiplier,prop_multiplier", [(1.0, 0.0), (0.0, 1.0)])
def test_configurable_yields_conserve_cod(acid_multiplier: float, prop_multiplier: float) -> None:
    state = np.asarray(InitialState().to_vector(), dtype=float)
    params = KineticParameters(acidogen_yield=0.20, propionate_yield=0.10)
    reaction, diag = reaction_vector(
        state, influent_ph=7.0, temperature_c=35.0, params=params,
        hydrolysis_multiplier=1.0, gas_capture_efficiency=1.0,
        acidogenesis_multiplier=acid_multiplier, propionate_multiplier=prop_multiplier,
    )
    cod_indices = [STATE_INDEX[name] for name in STATE_NAMES if name not in {"inorganic_nitrogen", "alkalinity"}]
    gas_cod = (
        diag["acetate_methanogenesis_rate"] * (1.0 - params.acetoclastic_yield)
        + diag["hydrogen_methanogenesis_rate"] * (1.0 - params.hydrogenotrophic_yield)
        + params.gas_stripping_h2 * state[STATE_INDEX["hydrogen"]]
    )
    assert np.sum(reaction[cod_indices]) + gas_cod == pytest.approx(0.0, abs=1e-9)
