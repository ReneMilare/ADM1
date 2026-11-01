from simulator.reactor_models.base import ReactorBase


class UASBReactor(ReactorBase):
    reactor_type = "uasb"
    default_biomass_washout_factor = 0.35
    default_gas_capture_efficiency = 1.0
    default_hydrolysis_multiplier = 1.08
