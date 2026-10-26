from __future__ import annotations

from pathlib import Path

from .atomic import read_json, write_json_atomic

STATE_DIR = Path.home() / ".dialogic-voice-partner"
STATE_FILE = STATE_DIR / "state.json"


def get_active_project() -> str | None:
    """Return the project the app is currently working in, if any."""
    if not STATE_FILE.is_file():
        return None
    try:
        data = read_json(STATE_FILE)
    except (OSError, ValueError):
        return None
    value = data.get("active_project")
    return value if isinstance(value, str) and value else None


def set_active_project(root: Path) -> str:
    resolved = str(root.expanduser().resolve())
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    write_json_atomic(STATE_FILE, {"active_project": resolved})
    return resolved
