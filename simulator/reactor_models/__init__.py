from simulator.reactor_models.base import ReactorBase
from simulator.reactor_models.cstr import CSTRReactor
from simulator.reactor_models.plug_flow import PlugFlowReactor
from simulator.reactor_models.uasb import UASBReactor
from simulator.core.models import ReactorConfig


def build_reactor(config: ReactorConfig) -> ReactorBase:
    if config.reactor_type == "cstr":
        return CSTRReactor(config)
    if config.reactor_type == "uasb":
        return UASBReactor(config)
    if config.reactor_type == "plug_flow":
        return PlugFlowReactor(config)
    raise ValueError(f"Unsupported reactor type: {config.reactor_type}")


__all__ = ["ReactorBase", "CSTRReactor", "UASBReactor", "PlugFlowReactor", "build_reactor"]
