from __future__ import annotations

import sys
from pathlib import Path


def ensure_project_root() -> None:
    """Add the project root (parent of the ``webapp/`` package directory) to sys.path."""
    project_root = str(Path(__file__).resolve().parent.parent)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
