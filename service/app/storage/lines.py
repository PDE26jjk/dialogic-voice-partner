from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from ..schemas import LineDocument, PushLine
from .atomic import read_json, write_json_atomic
from .paths import project_paths

UUID_PATTERN = re.compile(r"^[A-Za-z0-9-]{8,64}$")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def validate_uuid(value: str) -> str:
    if not UUID_PATTERN.match(value):
        raise ValueError(f"Invalid line uuid: {value!r}")
    return value


def upsert_lines(
    root: Path,
    dtl: str,
    lines: list[PushLine],
    section: str,
) -> tuple[int, int]:
    """Create or update one line document per pushed voice line.

    Existing timelines and clips are preserved: only the fields owned by the
    Godot editor are overwritten.
    """
    lines_dir = project_paths(root.expanduser().resolve())["lines"]
    created = 0
    updated = 0

    for line in lines:
        validate_uuid(line.uuid)
        path = lines_dir / f"{line.uuid}.json"

        if path.is_file():
            document = LineDocument.model_validate(read_json(path))
            updated += 1
        else:
            document = LineDocument(
                uuid=line.uuid,
                section=section,
                dtl=dtl,
                character=line.character,
                text=line.text,
            )
            created += 1

        document.section = section
        document.dtl = dtl
        document.character = line.character
        document.character_name = line.character_name
        document.text = line.text
        document.updated_at = _now()
        write_json_atomic(path, document.model_dump(mode="json"))

    return created, updated


def load_line(root: Path, uuid_value: str) -> LineDocument:
    """Read one line document by its Godot UUID."""
    validate_uuid(uuid_value)
    path = project_paths(root.expanduser().resolve())["lines"] / f"{uuid_value}.json"
    if not path.is_file():
        raise FileNotFoundError(f"No line document: {path}")
    return LineDocument.model_validate(read_json(path))


def list_lines(
    root: Path,
    section: str | None = None,
    order: list[str] | None = None,
) -> list[LineDocument]:
    """Return the project's line documents, optionally limited to one section.

    `order` is the user's arrangement; UUIDs missing from it keep their natural
    order after the arranged ones.
    """
    lines_dir = project_paths(root.expanduser().resolve())["lines"]
    if not lines_dir.is_dir():
        return []

    documents: list[LineDocument] = []
    for path in sorted(lines_dir.glob("*.json")):
        try:
            document = LineDocument.model_validate(read_json(path))
        except (OSError, ValueError):
            continue
        if section is not None and document.section != section:
            continue
        documents.append(document)

    if order:
        rank = {uuid: index for index, uuid in enumerate(order)}
        documents.sort(key=lambda document: (rank.get(document.uuid, len(rank)), document.uuid))
    return documents
