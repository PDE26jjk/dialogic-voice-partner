"""Project storage: JSON documents on disk, no database (see design D3)."""

from .atomic import write_json_atomic
from .project import create_project, load_project, load_workspace, save_workspace
from .paths import project_paths, workspace_path

__all__ = [
    "create_project",
    "load_project",
    "load_workspace",
    "save_workspace",
    "project_paths",
    "workspace_path",
    "write_json_atomic",
]
