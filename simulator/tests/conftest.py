from __future__ import annotations

import numpy as np
import pytest

from simulator.core.models import FeedDefinition, InitialState, KineticParameters


@pytest.fixture
def default_params() -> KineticParameters:
    return KineticParameters()


@pytest.fixture
def default_state() -> np.ndarray:
    return np.asarray(InitialState().to_vector(), dtype=float)


@pytest.fixture
def default_feed() -> FeedDefinition:
    return FeedDefinition()
