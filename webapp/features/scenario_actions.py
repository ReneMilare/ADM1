"""Actions de cenário — sem Streamlit, recebe/retorna contratos."""

from __future__ import annotations

from typing import TYPE_CHECKING

from webapp.contracts import ScenarioArtifact

if TYPE_CHECKING:
    from simulator.core.models import SimulationResult


def load_scenario(simulation_id: str) -> SimulationResult | None:
    """Carrega cenário pelo ID a partir do ScenarioStore."""
    from simulator.scenario_store import ScenarioStore
    store = ScenarioStore()
    try:
        return store.load(simulation_id)
    except Exception:
        return None


def duplicate_scenario_action(simulation_id: str) -> tuple[str | None, str | None]:
    """Duplica cenário. Retorna (novo_id, None) ou (None, error_msg)."""
    from webapp.services.scenario_service import duplicate_scenario
    new_id = duplicate_scenario(simulation_id)
    if new_id is not None:
        return new_id, None
    return None, f"Falha ao duplicar o cenário '{simulation_id}'."


def get_scenario_diff(id_a: str, id_b: str) -> dict | None:
    """Wrapper sobre compute_scenario_diff."""
    from webapp.services.scenario_service import compute_scenario_diff
    return compute_scenario_diff(id_a, id_b)


def build_artifact(
    simulation_id: str,
    *,
    notes: str = "",
    tags: list[str] | None = None,
    baseline_id: str | None = None,
) -> ScenarioArtifact | None:
    """Wrapper sobre build_scenario_artifact."""
    from webapp.services.scenario_service import build_scenario_artifact
    return build_scenario_artifact(
        simulation_id,
        notes=notes,
        tags=tags,
        baseline_id=baseline_id,
    )
