"""Project storage: JSON documents on disk, no database (see design D3)."""

from .atomic import write_json_atomic
from .assets import list_assets, save_asset
from .blocks import (
    add_take,
    convert_slot,
    create_block,
    default_title,
    delete_block,
    delete_take,
    duplicate_block,
    ensure_slot,
    list_blocks,
    load_block,
    referencing_lines,
    revert_prompt,
    save_block,
    slot_key,
    update_block,
    update_slot,
)
from .cleanup import cleanup_orphans
from .index import build_index, index_to_json, load_index, reload_index, save_index
from .jobs import create_job, fail_interrupted, list_jobs, save_job
from .secrets import configured_providers, get_secret, load_secrets, save_secret
from .lines import list_lines, load_line, save_line, update_line, upsert_lines
from .paths import project_paths, workspace_path
from .project import (
    activate_section,
    active_project,
    create_project,
    create_section,
    ensure_section,
    find_character_voice,
    get_character_voice,
    load_project,
    load_workspace,
    reorder_lines,
    reorder_sections,
    save_project,
    save_workspace,
    set_character_voice,
    update_section,
    update_settings,
)
from .state import get_active_project, set_active_project

__all__ = [
    "activate_section",
    "active_project",
    "add_take",
    "convert_slot",
    "create_block",
    "create_project",
    "create_section",
    "default_title",
    "delete_block",
    "delete_take",
    "ensure_section",
    "ensure_slot",
    "find_character_voice",
    "get_character_voice",
    "list_assets",
    "list_blocks",
    "list_lines",
    "load_block",
    "load_line",
    "load_project",
    "load_workspace",
    "referencing_lines",
    "reorder_lines",
    "revert_prompt",
    "save_asset",
    "save_block",
    "save_line",
    "save_project",
    "set_character_voice",
    "save_workspace",
    "update_line",
    "update_settings",
    "slot_key",
    "update_block",
    "update_section",
    "update_slot",
    "upsert_lines",
    "project_paths",
    "workspace_path",
    "write_json_atomic",
    "get_active_project",
    "set_active_project",
]
