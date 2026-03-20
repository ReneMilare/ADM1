from __future__ import annotations

import json
import re
from copy import deepcopy
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from simulator.core.models import SimulationResult

PROJECT_ROOT = Path(__file__).resolve().parents[2]
USER_DATA_DIR = PROJECT_ROOT / "webapp" / "user_data"
STATE_PATH = USER_DATA_DIR / "workbench_state.json"
MAX_RECENT_QUERIES = 12
MAX_RECENT_SIMULATIONS = 12
MAX_PRESET_NAME_LENGTH = 80
PRESET_NAME_RE = re.compile(r"[^\w\s().-]+", flags=re.UNICODE)
WHITESPACE_RE = re.compile(r"\s+")
DEFAULT_WORKBENCH_STATE = {
    "preferences": {
        "default_reactor": "cstr",
        "default_backend": "pyadm1",
        "default_top_k": 5,
        "persist_scenarios_by_default": True,
        "show_home_onboarding": True,
        "auto_expand_top_result": True,
        "ammonia_inhibition_mode_default": "simple",
    },
    "simulation_presets": [],
    "favorite_queries": [],
    "recent_queries": [],
    "recent_simulations": [],
}


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _deepcopy_default_state() -> dict[str, Any]:
    return deepcopy(DEFAULT_WORKBENCH_STATE)


def _ensure_storage() -> None:
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)


def _state_fingerprint() -> tuple[bool, int, int]:
    if not STATE_PATH.exists():
        return (False, 0, 0)
    try:
        stat = STATE_PATH.stat()
    except OSError:
        return (True, 0, 0)
    return (True, stat.st_mtime_ns, stat.st_size)


@lru_cache(maxsize=4)
def _load_workbench_state_cached(_: tuple[bool, int, int]) -> dict[str, Any]:
    return _safe_read_state()


def _invalidate_state_cache() -> None:
    _load_workbench_state_cached.cache_clear()


def _safe_read_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return _deepcopy_default_state()
    try:
        payload = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return _deepcopy_default_state()
    return _normalize_state(payload)


def _normalize_state(payload: dict[str, Any] | None) -> dict[str, Any]:
    state = _deepcopy_default_state()
    if not isinstance(payload, dict):
        return state

    preferences = payload.get("preferences")
    if isinstance(preferences, dict):
        for key in state["preferences"]:
            if key in preferences:
                state["preferences"][key] = preferences[key]

    for key in ("simulation_presets", "favorite_queries", "recent_queries", "recent_simulations"):
        value = payload.get(key)
        if isinstance(value, list):
            state[key] = [item for item in value if isinstance(item, dict)]

    state["recent_queries"] = state["recent_queries"][:MAX_RECENT_QUERIES]
    state["recent_simulations"] = state["recent_simulations"][:MAX_RECENT_SIMULATIONS]
    return state


def _write_state(state: dict[str, Any]) -> None:
    _ensure_storage()
    tmp_path = STATE_PATH.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(STATE_PATH)
    _invalidate_state_cache()


def _sanitize_preset_name(name: str) -> str:
    cleaned_name = PRESET_NAME_RE.sub("", name)
    cleaned_name = WHITESPACE_RE.sub(" ", cleaned_name).strip(" .")
    cleaned_name = cleaned_name[:MAX_PRESET_NAME_LENGTH].strip()
    if not cleaned_name or cleaned_name in {".", ".."}:
        raise ValueError("Informe um nome valido para salvar o preset do usuario.")
    return cleaned_name


def load_workbench_state() -> dict[str, Any]:
    return deepcopy(_load_workbench_state_cached(_state_fingerprint()))


def get_preferences() -> dict[str, Any]:
    return dict(load_workbench_state()["preferences"])


def save_preferences(updates: dict[str, Any]) -> dict[str, Any]:
    state = load_workbench_state()
    for key in state["preferences"]:
        if key in updates:
            state["preferences"][key] = updates[key]
    _write_state(state)
    return dict(state["preferences"])


def export_workbench_state_bytes() -> bytes:
    state = load_workbench_state()
    return json.dumps(state, ensure_ascii=False, indent=2).encode("utf-8")


def list_simulation_presets() -> list[dict[str, Any]]:
    state = load_workbench_state()
    presets = state["simulation_presets"]
    return sorted(presets, key=lambda item: str(item.get("updated_at") or ""), reverse=True)


def save_simulation_preset(name: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    cleaned_name = _sanitize_preset_name(name)

    state = load_workbench_state()
    presets = [item for item in state["simulation_presets"] if str(item.get("name", "")).casefold() != cleaned_name.casefold()]
    presets.append(
        {
            "name": cleaned_name,
            "updated_at": _now_iso(),
            "payload": payload,
            "summary": {
                "reactor_type": payload.get("reactor_type"),
                "substrate_mode": payload.get("substrate_mode"),
                "preset_id": payload.get("preset_id"),
                "backend_choice": payload.get("backend_choice"),
                "duration_days": payload.get("simulation", {}).get("duration_days"),
            },
        }
    )
    state["simulation_presets"] = sorted(presets, key=lambda item: str(item.get("updated_at") or ""), reverse=True)
    _write_state(state)
    return list_simulation_presets()


def delete_simulation_preset(name: str) -> list[dict[str, Any]]:
    state = load_workbench_state()
    state["simulation_presets"] = [
        item for item in state["simulation_presets"] if str(item.get("name", "")).casefold() != name.casefold()
    ]
    _write_state(state)
    return list_simulation_presets()


def find_simulation_preset(name: str) -> dict[str, Any] | None:
    for item in list_simulation_presets():
        if str(item.get("name", "")).casefold() == name.casefold():
            return item
    return None


def list_favorite_queries() -> list[dict[str, Any]]:
    state = load_workbench_state()
    return sorted(state["favorite_queries"], key=lambda item: str(item.get("saved_at") or ""), reverse=True)


def is_query_favorite(query: str) -> bool:
    normalized = query.strip().casefold()
    return any(str(item.get("query", "")).casefold() == normalized for item in list_favorite_queries())


def toggle_favorite_query(query: str) -> bool:
    cleaned_query = query.strip()
    if not cleaned_query:
        raise ValueError("Nao ha consulta para favoritar.")

    state = load_workbench_state()
    favorites = [item for item in state["favorite_queries"] if str(item.get("query", "")).casefold() != cleaned_query.casefold()]
    removed = len(favorites) != len(state["favorite_queries"])
    if not removed:
        favorites.insert(0, {"query": cleaned_query, "saved_at": _now_iso()})
    state["favorite_queries"] = favorites[:MAX_RECENT_QUERIES]
    _write_state(state)
    return not removed


def list_recent_queries(limit: int = 8) -> list[dict[str, Any]]:
    state = load_workbench_state()
    return state["recent_queries"][:limit]


def record_recent_query(query: str, *, result_count: int, source_count: int) -> list[dict[str, Any]]:
    cleaned_query = query.strip()
    if not cleaned_query:
        return list_recent_queries()

    state = load_workbench_state()
    items = [item for item in state["recent_queries"] if str(item.get("query", "")).casefold() != cleaned_query.casefold()]
    items.insert(
        0,
        {
            "query": cleaned_query,
            "used_at": _now_iso(),
            "result_count": int(result_count),
            "source_count": int(source_count),
        },
    )
    state["recent_queries"] = items[:MAX_RECENT_QUERIES]
    _write_state(state)
    return list_recent_queries()


def list_recent_simulations(limit: int = 8) -> list[dict[str, Any]]:
    state = load_workbench_state()
    return state["recent_simulations"][:limit]


def record_recent_simulation(result: SimulationResult) -> list[dict[str, Any]]:
    state = load_workbench_state()
    items = [item for item in state["recent_simulations"] if str(item.get("simulation_id", "")) != result.simulation_id]
    items.insert(
        0,
        {
            "simulation_id": result.simulation_id,
            "created_at": result.created_at,
            "reactor_type": result.reactor.reactor_type,
            "backend_used": str(result.metadata.get("backend_used", result.simulation.backend)),
            "backend_requested": str(result.metadata.get("backend_requested", result.simulation.backend)),
            "feed_name": result.feed.name,
            "methane_final_m3_day": round(float(result.summary.methane_final_m3_day), 3),
        },
    )
    state["recent_simulations"] = items[:MAX_RECENT_SIMULATIONS]
    _write_state(state)
    return list_recent_simulations()


def clear_saved_items(section: str) -> None:
    state = load_workbench_state()
    if section not in {"simulation_presets", "favorite_queries", "recent_queries", "recent_simulations"}:
        raise ValueError(f"Unsupported section: {section}")
    state[section] = []
    _write_state(state)
