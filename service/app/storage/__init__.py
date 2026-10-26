"""Project storage: JSON documents on disk, no database (see design D3)."""

from .atomic import write_json_atomic
from .lines import upsert_lines
from .paths import project_paths, workspace_path
from .project import (
    create_project,
    ensure_section,
    load_project,
    load_workspace,
    save_workspace,
)

__all__ = [
    "create_project",
    "ensure_section",
    "load_project",
    "load_workspace",
    "save_workspace",
    "upsert_lines",
    "project_paths",
    "workspace_path",
    "write_json_atomic",
]
