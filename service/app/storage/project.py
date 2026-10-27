from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from ..schemas import (
    CharacterProviderSettings,
    CharacterSettings,
    ExportSettings,
    ProjectSettings,
    Section,
    WorkspaceState,
)
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


def update_settings(
    root: Path,
    recording_countdown_ms: int | None = None,
    export: ExportSettings | None = None,
) -> ProjectSettings:
    root = root.expanduser().resolve()
    settings = load_project(root)
    if recording_countdown_ms is not None:
        settings.recording_countdown_ms = recording_countdown_ms
    if export is not None:
        settings.export = export
    settings.updated_at = _now()
    write_json_atomic(project_paths(root)["project"], settings.model_dump(mode="json"))
    return settings


def delete_section(root: Path, section_id: str) -> list[Section]:
    """Remove a section and its workspace; its lines keep their documents."""
    root = root.expanduser().resolve()
    validate_section_id(section_id)
    settings = load_project(root)
    if len(settings.sections) <= 1:
        raise ValueError("A project needs at least one section")

    remaining = [section for section in settings.sections if section.id != section_id]
    if len(remaining) == len(settings.sections):
        raise ValueError(f"Unknown section: {section_id}")

    settings.sections = remaining
    for index, section in enumerate(settings.sections):
        section.order = index
    if settings.current_section == section_id:
        settings.current_section = settings.sections[0].id
    settings.updated_at = _now()
    write_json_atomic(project_paths(root)["project"], settings.model_dump(mode="json"))

    workspace = workspace_path(root, section_id)
    if workspace.is_file():
        workspace.unlink()
    return settings.sections


def reorder_sections(root: Path, ids: list[str]) -> list[Section]:
    """Persist the section order the user arranged in the sidebar."""
    root = root.expanduser().resolve()
    settings = load_project(root)
    order = {section_id: index for index, section_id in enumerate(ids)}
    for section in settings.sections:
        if section.id in order:
            section.order = order[section.id]
    settings.sections.sort(key=lambda section: section.order)
    write_json_atomic(project_paths(root)["project"], settings.model_dump(mode="json"))
    return settings.sections


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


DEFAULT_CHARACTER_ID = "none"
DEFAULT_CHARACTER_NAME = "无角色"


def ensure_default_character(settings: ProjectSettings) -> bool:
    """Make sure the fallback character exists; returns True when it changed."""
    entry = settings.characters.get(DEFAULT_CHARACTER_ID)
    if entry is not None:
        if entry.name in ("", "(no character)"):
            entry.name = DEFAULT_CHARACTER_NAME
            return True
        return False
    settings.characters[DEFAULT_CHARACTER_ID] = CharacterSettings(
        name=DEFAULT_CHARACTER_NAME
    )
    return True


def character_config(settings: ProjectSettings, character: str | None) -> CharacterSettings:
    """Return the character's defaults, falling back to the built-in one."""
    if character and character in settings.characters:
        return settings.characters[character]
    return settings.characters.get(DEFAULT_CHARACTER_ID) or CharacterSettings(
        name=DEFAULT_CHARACTER_NAME
    )


def update_character_provider(
    root: Path,
    character: str,
    provider: str,
    voice: str | None,
    params: dict | None,
) -> ProjectSettings:
    """Set one provider's defaults for a character."""
    root = root.expanduser().resolve()
    settings = load_project(root)
    ensure_default_character(settings)

    entry = settings.characters.get(character)
    if entry is None:
        raise KeyError(f"Unknown character: {character}")

    config = entry.providers.get(provider) or CharacterProviderSettings()
    if voice is not None:
        config.voice = voice or None
    if params is not None:
        config.params = dict(params)
    entry.providers[provider] = config

    settings.updated_at = _now()
    write_json_atomic(project_paths(root)["project"], settings.model_dump(mode="json"))
    return settings


def clear_character_provider(root: Path, character: str, provider: str) -> ProjectSettings:
    """Remove one provider's defaults so the provider defaults apply again."""
    root = root.expanduser().resolve()
    settings = load_project(root)
    entry = settings.characters.get(character)
    if entry is None:
        raise KeyError(f"Unknown character: {character}")
    entry.providers.pop(provider, None)
    settings.updated_at = _now()
    write_json_atomic(project_paths(root)["project"], settings.model_dump(mode="json"))
    return settings


def get_character_voice(settings: ProjectSettings, character: str, provider: str) -> str | None:
    """Return the mapped voice, or None when the character is unmapped."""
    config = character_config(settings, character)
    entry = config.providers.get(provider)
    return entry.voice if entry and entry.voice else None


def get_character_params(
    settings: ProjectSettings, character: str, provider: str
) -> dict:
    """Provider parameters configured for a character (may be empty)."""
    config = character_config(settings, character)
    entry = config.providers.get(provider)
    return dict(entry.params) if entry else {}


def set_character_name(root: Path, character: str, name: str) -> ProjectSettings:
    root = root.expanduser().resolve()
    settings = load_project(root)
    entry = settings.characters.get(character)
    if entry is None:
        raise KeyError(f"Unknown character: {character}")
    entry.name = name
    settings.updated_at = _now()
    write_json_atomic(project_paths(root)["project"], settings.model_dump(mode="json"))
    return settings


def add_character(root: Path, character: str, name: str) -> ProjectSettings:
    """Create a character seeded with the fallback character's providers."""
    root = root.expanduser().resolve()
    settings = load_project(root)
    ensure_default_character(settings)
    if character in settings.characters:
        raise ValueError(f"Character already exists: {character}")

    fallback = settings.characters[DEFAULT_CHARACTER_ID]
    settings.characters[character] = CharacterSettings(
        name=name or character,
        providers={
            provider: CharacterProviderSettings(
                voice=config.voice, params=dict(config.params)
            )
            for provider, config in fallback.providers.items()
        },
    )
    settings.updated_at = _now()
    write_json_atomic(project_paths(root)["project"], settings.model_dump(mode="json"))
    return settings


def remove_character(root: Path, character: str) -> ProjectSettings:
    """Drop a character; the fallback character cannot be removed."""
    if character == DEFAULT_CHARACTER_ID:
        raise ValueError("The default character cannot be removed")
    root = root.expanduser().resolve()
    settings = load_project(root)
    if character not in settings.characters:
        raise KeyError(f"Unknown character: {character}")
    del settings.characters[character]
    settings.updated_at = _now()
    write_json_atomic(project_paths(root)["project"], settings.model_dump(mode="json"))
    return settings


def rename_character(root: Path, old: str, new: str) -> ProjectSettings:
    """Rename a character id in settings and in the line documents."""
    root = root.expanduser().resolve()
    settings = load_project(root)
    if old not in settings.characters:
        raise KeyError(f"Unknown character: {old}")
    if new in settings.characters and new != old:
        raise ValueError(f"Character already exists: {new}")

    entry = settings.characters.pop(old)
    settings.characters[new] = entry
    settings.updated_at = _now()
    write_json_atomic(project_paths(root)["project"], settings.model_dump(mode="json"))

    from .lines import list_lines, save_line

    for line in list_lines(root):
        if line.character == old:
            line.character = new
            save_line(root, line)
    return settings


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
