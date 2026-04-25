from __future__ import annotations

import sys
from pathlib import Path


def ensure_project_root_on_path(start: str | Path | None = None) -> Path:
    current = Path(start or __file__).resolve()
    search_root = current if current.is_dir() else current.parent
    for candidate in (search_root, *search_root.parents):
        if (candidate / "simulator").is_dir() and (candidate / "webapp").is_dir():
            candidate_str = str(candidate)
            if candidate_str not in sys.path:
                sys.path.insert(0, candidate_str)
            return candidate
    raise RuntimeError("Could not locate the ADM1 project root from the current webapp entrypoint.")
