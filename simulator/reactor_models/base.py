from __future__ import annotations

from abc import ABC

import numpy as np

from simulator.core.kinetics import BIOMASS_INDICES, STATE_INDEX, clip_state_vector, reaction_vector
from simulator.core.models import FeedDefinition, InitialState, KineticParameters, OperatingConditions, ReactorConfig, STATE_NAMES


class ReactorBase(ABC):
    reactor_type = "base"
    default_biomass_washout_factor = 1.0
    default_gas_capture_efficiency = 1.0
    default_hydrolysis_multiplier = 1.0

    def __init__(self, config: ReactorConfig) -> None:
        self.config = config

    @property
    def segment_count(self) -> int:
        return self.config.segments

    @property
    def profile_segment_labels(self) -> tuple[str, ...]:
        return ()

    def biomass_washout_factor(self, segment_index: int) -> float:
        del segment_index
        return self.config.biomass_washout_factor or self.default_biomass_washout_factor

    def gas_capture_efficiency(self, segment_index: int) -> float:
        del segment_index
        return self.config.gas_capture_efficiency or self.default_gas_capture_efficiency

    def hydrolysis_multiplier(self, segment_index: int) -> float:
        del segment_index
        return self.config.hydrolysis_multiplier or self.default_hydrolysis_multiplier

    def segment_temperature_c(self, segment_index: int, operating_conditions: OperatingConditions) -> float:
        del segment_index
        return operating_conditions.temperature_c

    def segment_influent_ph(self, segment_index: int, feed: FeedDefinition) -> float:
        del segment_index
        return feed.ph

    def segment_parameters(self, segment_index: int, parameters: KineticParameters) -> KineticParameters:
        del segment_index
        return parameters

    def reaction_kwargs(self, segment_index: int) -> dict[str, float]:
        del segment_index
        return {}

    def segment_dilution_rate(self, segment_index: int, operating_conditions: OperatingConditions) -> float:
        del segment_index
        return self.segment_count / operating_conditions.hrt_days

    def segment_volume(self, segment_index: int, operating_conditions: OperatingConditions) -> float:
        del segment_index
        return operating_conditions.volume_m3 / self.segment_count

    def influent_vector(self, feed: FeedDefinition) -> np.ndarray:
        return np.asarray(feed.to_state_vector(), dtype=float)

    def initial_vector(self, initial_state: InitialState) -> np.ndarray:
        base_vector = np.asarray(initial_state.to_vector(), dtype=float)
        return np.tile(base_vector, self.segment_count)

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
        influent = self.influent_vector(feed)
        base_state_count = len(STATE_NAMES)
        biomass_indices = np.asarray(BIOMASS_INDICES, dtype=int)
        derivatives = np.zeros_like(states)

        for segment_index in range(self.segment_count):
            start = segment_index * base_state_count
            end = start + base_state_count
            segment_state = states[start:end]
            upstream_state = influent if segment_index == 0 else states[start - base_state_count : start]
            reaction, _ = reaction_vector(
                segment_state,
                influent_ph=self.segment_influent_ph(segment_index, feed),
                temperature_c=self.segment_temperature_c(segment_index, operating_conditions),
                params=self.segment_parameters(segment_index, parameters),
                hydrolysis_multiplier=self.hydrolysis_multiplier(segment_index),
                gas_capture_efficiency=self.gas_capture_efficiency(segment_index),
                **self.reaction_kwargs(segment_index),
            )
            dilution_rate = self.segment_dilution_rate(segment_index, operating_conditions)
            transport = dilution_rate * (upstream_state - segment_state)
            washout_factor = self.biomass_washout_factor(segment_index)
            transport[biomass_indices] = dilution_rate * (
                upstream_state[biomass_indices] - washout_factor * segment_state[biomass_indices]
            )
            derivatives[start:end] = transport + reaction
        return derivatives

    def summarize_profiles(
        self,
        state_matrix: np.ndarray,
        *,
        feed: FeedDefinition,
        operating_conditions: OperatingConditions,
        parameters: KineticParameters,
    ) -> dict[str, list[float]]:
        clipped = clip_state_vector(state_matrix)
        base_state_count = len(STATE_NAMES)
        profiles: dict[str, list[float]] = {name: [] for name in STATE_NAMES}
        profiles.update(
            {
                "ph": [],
                "vfa_total": [],
                "methane_m3_day": [],
                "co2_m3_day": [],
                "h2_m3_day": [],
                "biogas_m3_day": [],
                "ch4_fraction": [],
                "effluent_cod": [],
                "volatile_solids_proxy": [],
                "free_ammonia_kgN_m3": [],
                "inh_nh3_acidogens": [],
                "inh_nh3_propionate": [],
                "inh_nh3_acetoclastic": [],
                "inh_nh3_hydrogenotrophic": [],
            }
        )
        for label in self.profile_segment_labels:
            profiles[f"{label}_ph"] = []
            profiles[f"{label}_hydrolysis_rate"] = []
            profiles[f"{label}_methane_rate_m3_day"] = []

        for row in clipped:
            methane_total = 0.0
            co2_total = 0.0
            h2_total = 0.0
            biogas_total = 0.0
            ph_weighted = 0.0
            vfa_weighted = 0.0
            fan_weighted = 0.0
            inh_acid_weighted = 0.0
            inh_pro_weighted = 0.0
            inh_ac_weighted = 0.0
            inh_hg_weighted = 0.0
            stage_snapshots: list[tuple[str, dict[str, float], float]] = []

            for segment_index in range(self.segment_count):
                start = segment_index * base_state_count
                end = start + base_state_count
                segment_state = row[start:end]
                segment_volume = self.segment_volume(segment_index, operating_conditions)
                _, diagnostics = reaction_vector(
                    segment_state,
                    influent_ph=self.segment_influent_ph(segment_index, feed),
                    temperature_c=self.segment_temperature_c(segment_index, operating_conditions),
                    params=self.segment_parameters(segment_index, parameters),
                    hydrolysis_multiplier=self.hydrolysis_multiplier(segment_index),
                    gas_capture_efficiency=self.gas_capture_efficiency(segment_index),
                    **self.reaction_kwargs(segment_index),
                )
                methane_total += diagnostics["methane_rate_m3_m3_day"] * segment_volume
                co2_total += diagnostics["co2_rate_m3_m3_day"] * segment_volume
                h2_total += diagnostics["h2_rate_m3_m3_day"] * segment_volume
                biogas_total += diagnostics["biogas_rate_m3_m3_day"] * segment_volume
                ph_weighted += diagnostics["ph"] * segment_volume / operating_conditions.volume_m3
                vfa_weighted += diagnostics["vfa_total"] * segment_volume / operating_conditions.volume_m3
                fan_weighted += diagnostics["free_ammonia_kgN_m3"] * segment_volume / operating_conditions.volume_m3
                inh_acid_weighted += diagnostics["inh_nh3_acidogens"] * segment_volume / operating_conditions.volume_m3
                inh_pro_weighted += diagnostics["inh_nh3_propionate"] * segment_volume / operating_conditions.volume_m3
                inh_ac_weighted += diagnostics["inh_nh3_acetoclastic"] * segment_volume / operating_conditions.volume_m3
                inh_hg_weighted += diagnostics["inh_nh3_hydrogenotrophic"] * segment_volume / operating_conditions.volume_m3
                if segment_index < len(self.profile_segment_labels):
                    stage_snapshots.append((self.profile_segment_labels[segment_index], diagnostics, segment_volume))

            effluent_state = row[-base_state_count:]
            effluent_cod = float(
                effluent_state[STATE_INDEX["particulate_cod"]]
                + effluent_state[STATE_INDEX["soluble_cod"]]
                + effluent_state[STATE_INDEX["acetate"]]
                + effluent_state[STATE_INDEX["propionate"]]
            )
            volatile_solids_proxy = float(
                effluent_state[STATE_INDEX["particulate_cod"]]
                + effluent_state[STATE_INDEX["acidogens"]]
                + effluent_state[STATE_INDEX["propionate_biomass"]]
                + effluent_state[STATE_INDEX["acetoclastic_biomass"]]
                + effluent_state[STATE_INDEX["hydrogenotrophic_biomass"]]
            )
            ch4_fraction = methane_total / max(biogas_total, 1e-9)

            for state_index, state_name in enumerate(STATE_NAMES):
                profiles[state_name].append(float(effluent_state[state_index]))
            profiles["ph"].append(float(ph_weighted))
            profiles["vfa_total"].append(float(vfa_weighted))
            profiles["methane_m3_day"].append(float(methane_total))
            profiles["co2_m3_day"].append(float(co2_total))
            profiles["h2_m3_day"].append(float(h2_total))
            profiles["biogas_m3_day"].append(float(biogas_total))
            profiles["ch4_fraction"].append(float(np.clip(ch4_fraction, 0.0, 1.0)))
            profiles["effluent_cod"].append(effluent_cod)
            profiles["volatile_solids_proxy"].append(volatile_solids_proxy)
            profiles["free_ammonia_kgN_m3"].append(float(fan_weighted))
            profiles["inh_nh3_acidogens"].append(float(inh_acid_weighted))
            profiles["inh_nh3_propionate"].append(float(inh_pro_weighted))
            profiles["inh_nh3_acetoclastic"].append(float(inh_ac_weighted))
            profiles["inh_nh3_hydrogenotrophic"].append(float(inh_hg_weighted))
            for label, diagnostics, segment_volume in stage_snapshots:
                del segment_volume
                profiles[f"{label}_ph"].append(float(diagnostics["ph"]))
                profiles[f"{label}_hydrolysis_rate"].append(float(diagnostics["hydrolysis_rate"]))
                profiles[f"{label}_methane_rate_m3_day"].append(
                    float(diagnostics["methane_rate_m3_m3_day"] * self.segment_volume(self.profile_segment_labels.index(label), operating_conditions))
                )
        return profiles
