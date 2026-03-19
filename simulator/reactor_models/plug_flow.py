from simulator.reactor_models.base import ReactorBase


class PlugFlowReactor(ReactorBase):
    reactor_type = "plug_flow"
    default_biomass_washout_factor = 0.75
    default_gas_capture_efficiency = 1.04
    default_hydrolysis_multiplier = 1.12

    def hydrolysis_multiplier(self, segment_index: int) -> float:
        base = super().hydrolysis_multiplier(segment_index)
        if self.segment_count == 1:
            return base
        position = segment_index / (self.segment_count - 1)
        return base * (1.15 - 0.25 * position)

    def gas_capture_efficiency(self, segment_index: int) -> float:
        base = super().gas_capture_efficiency(segment_index)
        if self.segment_count == 1:
            return base
        position = segment_index / (self.segment_count - 1)
        return base * (0.96 + 0.08 * position)
