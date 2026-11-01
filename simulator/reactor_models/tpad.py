from __future__ import annotations

from simulator.core.models import FeedDefinition, KineticParameters, OperatingConditions, TPADConfig
from simulator.reactor_models.base import ReactorBase


class TPADReactor(ReactorBase):
    reactor_type = "tpad"
    default_hydrolysis_multiplier = 1.0

    @property
    def segment_count(self) -> int:
        return 2

    @property
    def profile_segment_labels(self) -> tuple[str, ...]:
        return ("thermo", "meso")

    def _cfg(self) -> TPADConfig:
        return self.config.tpad  # type: ignore[return-value]

    def biomass_washout_factor(self, segment_index: int) -> float:
        if self.config.biomass_washout_factor is not None:
            return self.config.biomass_washout_factor
        return 0.95 if segment_index == 0 else 0.85

    def gas_capture_efficiency(self, segment_index: int) -> float:
        if self.config.gas_capture_efficiency is not None:
            return self.config.gas_capture_efficiency
        return 0.94 if segment_index == 0 else 1.0

    def hydrolysis_multiplier(self, segment_index: int) -> float:
        base = super().hydrolysis_multiplier(segment_index)
        return base * (1.35 if segment_index == 0 else 1.0)

    def segment_temperature_c(self, segment_index: int, operating_conditions: OperatingConditions) -> float:
        del operating_conditions
        cfg = self._cfg()
        return cfg.thermo_temperature_c if segment_index == 0 else cfg.meso_temperature_c

    def segment_dilution_rate(self, segment_index: int, operating_conditions: OperatingConditions) -> float:
        cfg = self._cfg()
        local_hrt = cfg.thermo_hrt_days if segment_index == 0 else cfg.meso_hrt_days
        return 1.0 / local_hrt

    def segment_volume(self, segment_index: int, operating_conditions: OperatingConditions) -> float:
        flow = operating_conditions.volume_m3 / operating_conditions.hrt_days
        return flow / self.segment_dilution_rate(segment_index, operating_conditions)

    def segment_volumes(self, feed: FeedDefinition, operating_conditions: OperatingConditions) -> list[float]:
        flow = feed.flow_rate_m3_day or operating_conditions.volume_m3 / operating_conditions.hrt_days
        return [flow / self.segment_dilution_rate(i, operating_conditions) for i in range(2)]

    def segment_parameters(self, segment_index: int, parameters: KineticParameters) -> KineticParameters:
        if segment_index == 0:
            return parameters.model_copy(update={"k_m_ac": parameters.k_m_ac * 0.9, "k_m_h2": parameters.k_m_h2 * 0.9})
        return parameters.model_copy(update={"k_m_ac": parameters.k_m_ac * 1.08, "k_m_h2": parameters.k_m_h2 * 1.08})

    def reaction_kwargs(self, segment_index: int) -> dict[str, float]:
        if segment_index == 0:
            return {
                "acidogenesis_multiplier": 1.08,
                "acetoclastic_multiplier": 0.9,
                "hydrogenotrophic_multiplier": 0.9,
            }
        return {
            "acidogenesis_multiplier": 0.95,
            "acetoclastic_multiplier": 1.08,
            "hydrogenotrophic_multiplier": 1.08,
        }
