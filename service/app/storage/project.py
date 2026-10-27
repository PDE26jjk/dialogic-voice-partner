from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from ..schemas import ProjectSettings, Section, WorkspaceState
from .atomic import read_json, write_json_atomic
from .paths import (
    DEFAULT_SECTION_ID,
    DEFAULT_SECTION_NAME,
    project_paths,
    validate_section_id,
    workspace_path,
)


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


def ensure_section(root: Path) -> tuple[ProjectSettings, str]:
    """Return the current section, creating an Inbox section when the project has none."""
    root = root.expanduser().resolve()
    settings = load_project(root)
    if settings.current_section:
        return settings, settings.current_section

    if not settings.sections:
        settings.sections.append(
            Section(id=DEFAULT_SECTION_ID, name=DEFAULT_SECTION_NAME, order=0)
        )
    settings.current_section = settings.sections[0].id
    settings.updated_at = _now()
    write_json_atomic(project_paths(root)["project"], settings.model_dump(mode="json"))
    return settings, settings.current_section


def create_section(root: Path, section_id: str, name: str) -> Section:
    validate_section_id(section_id)
    root = root.expanduser().resolve()
    settings = load_project(root)
    if any(section.id == section_id for section in settings.sections):
        raise ValueError(f"Section already exists: {section_id}")

    order = max((section.order for section in settings.sections), default=-1) + 1
    section = Section(id=section_id, name=name, order=order)
    settings.sections.append(section)
    settings.updated_at = _now()
    write_json_atomic(project_paths(root)["project"], settings.model_dump(mode="json"))
    return section


def update_section(
    root: Path,
    section_id: str,
    name: str | None = None,
    order: int | None = None,
) -> Section:
    validate_section_id(section_id)
    root = root.expanduser().resolve()
    settings = load_project(root)
    for section in settings.sections:
        if section.id != section_id:
            continue
        if name is not None:
            section.name = name
        if order is not None:
            section.order = order
        settings.updated_at = _now()
        write_json_atomic(project_paths(root)["project"], settings.model_dump(mode="json"))
        return section
    raise KeyError(f"Unknown section: {section_id}")


def activate_section(root: Path, section_id: str) -> str:
    validate_section_id(section_id)
    root = root.expanduser().resolve()
    settings = load_project(root)
    if not any(section.id == section_id for section in settings.sections):
        raise KeyError(f"Unknown section: {section_id}")
    settings.current_section = section_id
    settings.updated_at = _now()
    write_json_atomic(project_paths(root)["project"], settings.model_dump(mode="json"))
    return section_id


def update_settings(root: Path, recording_countdown_ms: int | None = None) -> ProjectSettings:
    root = root.expanduser().resolve()
    settings = load_project(root)
    if recording_countdown_ms is not None:
        settings.recording_countdown_ms = recording_countdown_ms
    settings.updated_at = _now()
    write_json_atomic(project_paths(root)["project"], settings.model_dump(mode="json"))
    return settings


def reorder_lines(root: Path, uuids: list[str]) -> ProjectSettings:
    """Store the user's line order; unknown UUIDs are ignored, not remembered."""
    root = root.expanduser().resolve()
    settings = load_project(root)
    lines_dir = project_paths(root)["lines"]
    existing = {path.stem for path in lines_dir.glob("*.json")}
    settings.line_order = [uuid for uuid in uuids if uuid in existing]
    settings.updated_at = _now()
    write_json_atomic(project_paths(root)["project"], settings.model_dump(mode="json"))
    return settings


def save_project(root: Path, settings: ProjectSettings) -> ProjectSettings:
    """Persist project settings and stamp the modification time."""
    root = root.expanduser().resolve()
    settings.updated_at = _now()
    write_json_atomic(project_paths(root)["project"], settings.model_dump(mode="json"))
    return settings


def set_character_voice(
    root: Path,
    character: str,
    provider: str,
    voice: str,
) -> ProjectSettings:
    """Remember which voice a character speaks with on one provider."""
    root = root.expanduser().resolve()
    settings = load_project(root)

    # Drop stale mappings so a character always resolves to exactly one voice.
    for existing in settings.providers.values():
        if isinstance(existing, dict) and isinstance(existing.get("voices"), dict):
            existing["voices"].pop(character, None)

    entry = settings.providers.setdefault(provider, {})
    if not isinstance(entry, dict):
        entry = {}
        settings.providers[provider] = entry
    voices = entry.setdefault("voices", {})
    if not isinstance(voices, dict):
        voices = {}
        entry["voices"] = voices
    voices[character] = voice
    settings.updated_at = _now()
    write_json_atomic(project_paths(root)["project"], settings.model_dump(mode="json"))
    return settings


def get_character_voice(settings: ProjectSettings, character: str, provider: str) -> str | None:
    """Return the mapped voice, or None when the character is unmapped."""
    entry = settings.providers.get(provider)
    if not isinstance(entry, dict):
        return None
    voices = entry.get("voices")
    if not isinstance(voices, dict):
        return None
    value = voices.get(character)
    return value if isinstance(value, str) else None


def find_character_voice(
    settings: ProjectSettings, character: str
) -> tuple[str | None, str | None]:
    """Return the first (provider, voice) pair configured for a character."""
    for provider, entry in settings.providers.items():
        if not isinstance(entry, dict):
            continue
        voices = entry.get("voices")
        if isinstance(voices, dict) and isinstance(voices.get(character), str):
            return provider, voices[character]
    return None, None


def active_project() -> tuple[Path, ProjectSettings] | None:
    """Return the active project and its settings, or None when nothing is active."""
    from .state import get_active_project

    value = get_active_project()
    if not value:
        return None
    root = Path(value)
    try:
        return root, load_project(root)
    except FileNotFoundError:
        return None
