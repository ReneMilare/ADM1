from __future__ import annotations

from simulator.core.models import FeedDefinition, KineticParameters, OperatingConditions, TwoPhaseConfig
from simulator.reactor_models.base import ReactorBase


class TwoPhaseReactor(ReactorBase):
    reactor_type = "two_phase"
    default_hydrolysis_multiplier = 1.0

    @property
    def segment_count(self) -> int:
        return 2

    @property
    def profile_segment_labels(self) -> tuple[str, ...]:
        return ("phase1", "phase2")

    def _cfg(self) -> TwoPhaseConfig:
        return self.config.two_phase  # type: ignore[return-value]

    def biomass_washout_factor(self, segment_index: int) -> float:
        if self.config.biomass_washout_factor is not None:
            return self.config.biomass_washout_factor
        return 1.0 if segment_index == 0 else 0.65

    def gas_capture_efficiency(self, segment_index: int) -> float:
        if self.config.gas_capture_efficiency is not None:
            return self.config.gas_capture_efficiency
        return 0.9 if segment_index == 0 else 1.0

    def hydrolysis_multiplier(self, segment_index: int) -> float:
        base = super().hydrolysis_multiplier(segment_index)
        return base * (1.35 if segment_index == 0 else 1.05)

    def segment_dilution_rate(self, segment_index: int, operating_conditions: OperatingConditions) -> float:
        cfg = self._cfg()
        f_vol = cfg.phase1_volume_fraction if segment_index == 0 else 1.0 - cfg.phase1_volume_fraction
        local_hrt = operating_conditions.hrt_days * f_vol
        return 1.0 / max(local_hrt, 1e-9)

    def segment_volume(self, segment_index: int, operating_conditions: OperatingConditions) -> float:
        cfg = self._cfg()
        volume_fraction = cfg.phase1_volume_fraction if segment_index == 0 else 1.0 - cfg.phase1_volume_fraction
        return operating_conditions.volume_m3 * volume_fraction

    def segment_influent_ph(self, segment_index: int, feed: FeedDefinition) -> float:
        cfg = self._cfg()
        return cfg.phase1_ph_setpoint if segment_index == 0 else cfg.phase2_ph_setpoint

    def segment_parameters(self, segment_index: int, parameters: KineticParameters) -> KineticParameters:
        cfg = self._cfg()
        if segment_index == 0:
            return parameters.model_copy(
                update={
                    "ph_optimum": min(max(cfg.phase1_ph_setpoint + 0.2, 5.2), 6.1),
                    "k_m_ac": parameters.k_m_ac * 0.18,
                    "k_m_h2": parameters.k_m_h2 * 0.22,
                }
            )
        return parameters.model_copy(update={"ph_optimum": cfg.phase2_ph_setpoint, "k_m_ac": parameters.k_m_ac * 1.18, "k_m_h2": parameters.k_m_h2 * 1.12})

    def reaction_kwargs(self, segment_index: int) -> dict[str, float]:
        if segment_index == 0:
            return {
                "acidogenesis_multiplier": 1.2,
                "propionate_multiplier": 0.9,
                "acetoclastic_multiplier": 0.35,
                "hydrogenotrophic_multiplier": 0.4,
            }
        return {
            "acidogenesis_multiplier": 0.95,
            "acetoclastic_multiplier": 1.1,
            "hydrogenotrophic_multiplier": 1.05,
        }

