from simulator.core.models import ReactorConfig
from simulator.reactor_models.base import ReactorBase
from simulator.reactor_models.batch import BatchReactor
from simulator.reactor_models.cstr import CSTRReactor
from simulator.reactor_models.plug_flow import PlugFlowReactor
from simulator.reactor_models.tpad import TPADReactor
from simulator.reactor_models.two_phase import TwoPhaseReactor
from simulator.reactor_models.uasb import UASBReactor

REACTOR_REGISTRY = {
    "cstr": CSTRReactor,
    "uasb": UASBReactor,
    "plug_flow": PlugFlowReactor,
    "two_phase": TwoPhaseReactor,
    "tpad": TPADReactor,
    "batch": BatchReactor,
}


def build_reactor(config: ReactorConfig) -> ReactorBase:
    cls = REACTOR_REGISTRY.get(config.reactor_type)
    if cls is None:
        raise ValueError(f"Unsupported reactor type: {config.reactor_type}")
    return cls(config)


__all__ = [
    "BatchReactor",
    "CSTRReactor",
    "PlugFlowReactor",
    "ReactorBase",
    "TPADReactor",
    "TwoPhaseReactor",
    "UASBReactor",
    "build_reactor",
]
