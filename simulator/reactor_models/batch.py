from __future__ import annotations

import numpy as np

from simulator.core.kinetics import clip_state_vector, reaction_vector
from simulator.core.models import FeedDefinition, InitialState, KineticParameters, OperatingConditions
from simulator.reactor_models.base import ReactorBase


class BatchReactor(ReactorBase):
    reactor_type = "batch"
    default_biomass_washout_factor = 0.0
    default_gas_capture_efficiency = 1.0
    default_hydrolysis_multiplier = 1.0

    def initial_vector(self, initial_state: InitialState) -> np.ndarray:
        feed = FeedDefinition()
        inoculum_fraction = self.config.batch.inoculum_fraction if self.config.batch is not None else 0.3
        inoculum_state = np.asarray(initial_state.to_vector(), dtype=float)
        substrate_state = np.asarray(feed.to_state_vector(), dtype=float)
        mixed_state = inoculum_fraction * inoculum_state + (1.0 - inoculum_fraction) * substrate_state
        return mixed_state

    def build_batch_initial_vector(self, feed: FeedDefinition, initial_state: InitialState) -> np.ndarray:
        inoculum_fraction = self.config.batch.inoculum_fraction if self.config.batch is not None else 0.3
        inoculum_state = np.asarray(initial_state.to_vector(), dtype=float)
        substrate_state = np.asarray(feed.to_state_vector(), dtype=float)
        mixed_state = inoculum_fraction * inoculum_state + (1.0 - inoculum_fraction) * substrate_state
        return clip_state_vector(mixed_state)

    def rhs(
        self,
        t: float,
        y: np.ndarray,
        *,
        feed: FeedDefinition,
        operating_conditions: OperatingConditions,
        parameters: KineticParameters,
    ) -> np.ndarray:
        del t
        states = clip_state_vector(y)
        reaction, _ = reaction_vector(
            states,
            influent_ph=feed.ph,
            temperature_c=operating_conditions.temperature_c,
            params=parameters,
            hydrolysis_multiplier=self.hydrolysis_multiplier(0),
            gas_capture_efficiency=self.gas_capture_efficiency(0),
        )
        return reaction
