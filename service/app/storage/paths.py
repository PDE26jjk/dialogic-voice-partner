from __future__ import annotations

import re
from pathlib import Path

SECTION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

PROJECT_FILE = "project.json"
BLOCKS_DIR = "blocks"
LINES_DIR = "lines"
WORKSPACES_DIR = "workspaces"
MEDIA_DIR = "media"
TAKES_DIR = "media/takes"
ASSETS_DIR = "media/assets"


def validate_section_id(section_id: str) -> str:
    if not SECTION_ID_PATTERN.match(section_id):
        raise ValueError(f"Invalid section id: {section_id!r}")
    return section_id


def project_paths(root: Path) -> dict[str, Path]:
    return {
        "root": root,
        "project": root / PROJECT_FILE,
        "blocks": root / BLOCKS_DIR,
        "lines": root / LINES_DIR,
        "workspaces": root / WORKSPACES_DIR,
        "media": root / MEDIA_DIR,
        "takes": root / TAKES_DIR,
        "assets": root / ASSETS_DIR,
    }


def workspace_path(root: Path, section_id: str) -> Path:
    validate_section_id(section_id)
    return root / WORKSPACES_DIR / f"{section_id}.json"
