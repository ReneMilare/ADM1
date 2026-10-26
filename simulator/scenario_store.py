from __future__ import annotations

import re
from pathlib import Path

from simulator.core.models import SimulationResult

# Ids become file names. Rejecting both "/" and backslash keeps traversal
# protection identical on Windows and POSIX, where backslash is a valid name char.
_SIMULATION_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class ScenarioStore:
    def __init__(self, root: Path | None = None) -> None:
        # Default to a path relative to this file so the store location is
        # stable regardless of the process working directory.
        self.root = root if root is not None else Path(__file__).resolve().parent / "runs"
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, simulation_id: str) -> Path:
        if not _SIMULATION_ID_PATTERN.fullmatch(simulation_id):
            raise ValueError(f"Invalid simulation_id: {simulation_id}")
        resolved_root = self.root.resolve()
        candidate = (resolved_root / f"{simulation_id}.json").resolve()
        if not candidate.is_relative_to(resolved_root):
            raise ValueError(f"Invalid simulation_id: {simulation_id}")
        return candidate

    def save(self, result: SimulationResult) -> Path:
        path = self.path_for(result.simulation_id)
        path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        return path

    def load(self, simulation_id: str) -> SimulationResult:
        path = self.path_for(simulation_id)
        if not path.exists():
            raise FileNotFoundError(f"Simulation '{simulation_id}' was not found in {self.root}")
        return SimulationResult.model_validate_json(path.read_text(encoding="utf-8"))

    def list_simulation_ids(self) -> list[str]:
        return sorted(path.stem for path in self.root.glob("*.json"))
