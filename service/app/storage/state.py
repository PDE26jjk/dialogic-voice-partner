from __future__ import annotations

import json
from pathlib import Path

from .atomic import read_json, write_json_atomic

STATE_DIR = Path.home() / ".dialogic-voice-partner"
STATE_FILE = STATE_DIR / "state.json"
RECENT_LIMIT = 12


def _read_state() -> dict:
    if not STATE_FILE.is_file():
        return {}
    try:
        data = read_json(STATE_FILE)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_state(state: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    write_json_atomic(STATE_FILE, state)


def get_active_project() -> str | None:
    """Return the project the app is currently working in, if any."""
    value = _read_state().get("active_project")
    return value if isinstance(value, str) and value else None


def set_active_project(root: Path) -> str:
    resolved = str(root.expanduser().resolve())
    state = _read_state()
    state["active_project"] = resolved
    recent = [item for item in state.get("recent", []) if item != resolved]
    recent.insert(0, resolved)
    state["recent"] = recent[:RECENT_LIMIT]
    _write_state(state)
    return resolved


def clear_active_project() -> None:
    state = _read_state()
    state.pop("active_project", None)
    _write_state(state)


def recent_projects() -> list[str]:
    recent = _read_state().get("recent", [])
    return [item for item in recent if isinstance(item, str)]


def forget_project(root: Path) -> None:
    resolved = str(root.expanduser().resolve())
    state = _read_state()
    state["recent"] = [item for item in state.get("recent", []) if item != resolved]
    if state.get("active_project") == resolved:
        state.pop("active_project", None)
    _write_state(state)
