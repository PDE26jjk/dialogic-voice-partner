from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from ..schemas import ProjectSettings, WorkspaceState
from .atomic import read_json, write_json_atomic
from .paths import project_paths, validate_section_id, workspace_path


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_project(root: Path, godot_project: str, name: str) -> ProjectSettings:
    """Create the project folder tree and its `project.json`.

    An existing non-empty folder is refused so a typo cannot overwrite a project.
    """
    root = root.expanduser().resolve()
    if root.exists() and any(root.iterdir()):
        raise FileExistsError(f"Folder is not empty: {root}")

    paths = project_paths(root)
    for key in ("blocks", "lines", "workspaces", "takes", "assets"):
        paths[key].mkdir(parents=True, exist_ok=True)

    now = _now()
    settings = ProjectSettings(
        name=name,
        godot_project=godot_project,
        created_at=now,
        updated_at=now,
    )
    write_json_atomic(paths["project"], settings.model_dump(mode="json"))
    return settings


def load_project(root: Path) -> ProjectSettings:
    root = root.expanduser().resolve()
    path = project_paths(root)["project"]
    if not path.is_file():
        raise FileNotFoundError(f"No {path.name} in {root}")
    return ProjectSettings.model_validate(read_json(path))


def load_workspace(root: Path, section_id: str) -> WorkspaceState | None:
    root = root.expanduser().resolve()
    validate_section_id(section_id)
    path = workspace_path(root, section_id)
    if not path.is_file():
        return None
    return WorkspaceState.model_validate(read_json(path))


def save_workspace(root: Path, state: WorkspaceState) -> WorkspaceState:
    root = root.expanduser().resolve()
    validate_section_id(state.section)
    state.updated_at = _now()
    write_json_atomic(workspace_path(root, state.section), state.model_dump(mode="json"))
    return state
