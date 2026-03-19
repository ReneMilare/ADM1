from simulator.reactor_models.base import ReactorBase


class CSTRReactor(ReactorBase):
    reactor_type = "cstr"
    default_biomass_washout_factor = 1.0
    default_gas_capture_efficiency = 1.0
    default_hydrolysis_multiplier = 1.0
