from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from simulator.digital_twin.estimator import UKFConfig

from simulator.core.models import (
    FeedDefinition,
    InitialState,
    KineticParameters,
    OperatingConditions,
    ReactorConfig,
    SimulationConfig,
)


def make_default_feed() -> FeedDefinition:
    return FeedDefinition()


def make_default_initial_state(feed: FeedDefinition | None = None) -> InitialState:
    base = feed or make_default_feed()
    # Heuristic initial conditions calibrated for BSM2-like reactors (Batstone et al., 2002).
    # Multipliers reflect typical steady-state ratios between reactor and feed concentrations,
    # chosen so the ODE converges within 30–60 simulation days.
    return InitialState(
        particulate_cod=max(base.particulate_cod * 0.82, 0.1),   # ~82% of feed (partial hydrolysis)
        soluble_cod=max(base.soluble_cod * 0.72, 0.1),            # ~72% of feed (partial acidogenesis)
        acetate=max(base.acetate * 1.8, 0.05),                    # ×1.8 vs feed (VFA accumulation)
        propionate=max(base.propionate * 2.4, 0.05),              # ×2.4 vs feed (slower oxidation)
        hydrogen=max(base.hydrogen * 4.0, 0.001),                 # ×4 vs feed (dissolved H2 pool at new k_m_h2 SS)
        inorganic_nitrogen=max(base.inorganic_nitrogen * 1.08, 0.1),  # slight N accumulation
        alkalinity=max(base.alkalinity * 1.06, 0.5),              # slight alkalinity build-up
        sic_kmol_m3=max(base.sic_kmol_m3 * 1.06, 1e-6) if base.sic_kmol_m3 is not None else None,
    )


def make_default_operating_conditions() -> OperatingConditions:
    return OperatingConditions()


def make_default_kinetics() -> KineticParameters:
    return KineticParameters()


def make_default_reactor_config(reactor_type: str = "cstr") -> ReactorConfig:
    if reactor_type == "plug_flow":
        return ReactorConfig(reactor_type="plug_flow", segments=6)
    return ReactorConfig(reactor_type=reactor_type)


def make_default_simulation_config() -> SimulationConfig:
    return SimulationConfig()


def make_default_ukf_config() -> UKFConfig:
    """Digital-twin filter defaults, independent of reactor sizing defaults."""
    from simulator.digital_twin.estimator import UKFConfig

    return UKFConfig()
