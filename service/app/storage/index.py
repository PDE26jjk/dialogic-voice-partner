"""Project index: derived lookups rebuilt from the JSON documents on disk.

The index is a cache: deleting ``index.json`` only costs a rebuild. It is
written after every rebuild so external tools can inspect the same view.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from ..schemas import BlockDocument, LineDocument
from .atomic import read_json, write_json_atomic
from .paths import project_paths

INDEX_FILE = "index.json"


@dataclass
class ProjectIndex:
    built_at: str = ""
    sections: list[str] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)
    blocks: list[str] = field(default_factory=list)
    block_lines: dict[str, list[str]] = field(default_factory=dict)
    line_blocks: dict[str, list[str]] = field(default_factory=dict)
    take_refs: dict[str, list[str]] = field(default_factory=dict)
    orphans: list[str] = field(default_factory=list)


def build_index(root: Path) -> ProjectIndex:
    """Walk the documents and derive every lookup the UI needs."""
    paths = project_paths(root.expanduser().resolve())
    index = ProjectIndex(built_at=datetime.now(timezone.utc).isoformat())

    project_file = paths["project"]
    if project_file.is_file():
        project = read_json(project_file)
        index.sections = [section["id"] for section in project.get("sections", [])]

    lines: dict[str, LineDocument] = {}
    for path in sorted(paths["lines"].glob("*.json")):
        try:
            document = LineDocument.model_validate(read_json(path))
        except (ValueError, OSError):
            continue
        lines[document.uuid] = document
        index.lines.append(document.uuid)

    blocks: dict[str, BlockDocument] = {}
    for path in sorted(paths["blocks"].glob("*.json")):
        try:
            block = BlockDocument.model_validate(read_json(path))
        except (ValueError, OSError):
            continue
        blocks[block.id] = block
        index.blocks.append(block.id)

    for block in blocks.values():
        linked = [uuid for uuid in block.links.lines if uuid in lines]
        index.block_lines[block.id] = linked
        if not linked:
            index.orphans.append(block.id)
        for uuid in linked:
            index.line_blocks.setdefault(uuid, []).append(block.id)

    for line in lines.values():
        # A clip referencing a take makes that take protected from cleanup.
        for position, clip in enumerate(line.track.clips):
            if clip.source.kind == "take" and clip.source.take:
                index.take_refs.setdefault(clip.source.take, []).append(
                    f"{line.uuid}#{position}"
                )

    return index


def save_index(root: Path, index: ProjectIndex) -> None:
    paths = project_paths(root.expanduser().resolve())
    write_json_atomic(paths["root"] / INDEX_FILE, asdict(index))


def load_index(root: Path, rebuild: bool = False) -> ProjectIndex:
    paths = project_paths(root.expanduser().resolve())
    path = paths["root"] / INDEX_FILE
    if not rebuild and path.is_file():
        try:
            return ProjectIndex(**read_json(path))
        except (TypeError, ValueError, OSError):
            pass
    index = build_index(paths["root"])
    save_index(paths["root"], index)
    return index


def reload_index(root: Path) -> ProjectIndex:
    index = build_index(root)
    save_index(root, index)
    return index


def index_to_json(index: ProjectIndex) -> dict:
    return asdict(index)
