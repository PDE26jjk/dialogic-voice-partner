from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from ..providers.registry import PROVIDERS
from ..schemas import BlockDocument, BlockLinks, BlockSlot, Take
from .atomic import read_json, write_json_atomic
from .lines import load_line, list_lines
from .paths import project_paths

TITLE_TEXT_LIMIT = 16
STAGE_DIRECTION = re.compile(r"[（(][^）)]*[）)]")
SENTENCE_END = "。.!?！？…"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _blocks_dir(root: Path) -> Path:
    return project_paths(root.expanduser().resolve())["blocks"]


def block_path(root: Path, block_id: str) -> Path:
    if not block_id or "/" in block_id or "\\" in block_id or ".." in block_id:
        raise ValueError(f"Invalid block id: {block_id!r}")
    return _blocks_dir(root) / f"{block_id}.json"


def default_title(character_name: str | None, character: str, text: str) -> str:
    """Build the title used when a block is created from a line."""
    speaker = character_name or character or "Line"
    excerpt = " ".join(text.split())
    if len(excerpt) > TITLE_TEXT_LIMIT:
        excerpt = excerpt[:TITLE_TEXT_LIMIT].rstrip() + "…"
    return f"{speaker} · {excerpt}" if excerpt else speaker


def slot_key(provider: str, model: str) -> str:
    return f"{provider}/{model}"


def convert_prompt(text: str) -> str:
    """Rewrite a line into a plain sentence a TTS model can read.

    Stage directions such as "（叹气）" are dropped and the result is closed with a
    sentence terminator. Provider adapters may replace this with a native form.
    """
    cleaned = STAGE_DIRECTION.sub("", text)
    cleaned = cleaned.strip().strip("\"“”'‘’")
    cleaned = " ".join(cleaned.split())
    if cleaned and cleaned[-1] not in SENTENCE_END:
        cleaned += "。"
    return cleaned


def load_block(root: Path, block_id: str) -> BlockDocument:
    path = block_path(root, block_id)
    if not path.is_file():
        raise FileNotFoundError(f"No block document: {path}")
    return BlockDocument.model_validate(read_json(path))


def save_block(root: Path, block: BlockDocument) -> BlockDocument:
    block.updated_at = _now()
    write_json_atomic(block_path(root, block.id), block.model_dump(mode="json"))
    return block


def list_blocks(
    root: Path,
    section: str | None = None,
    line: str | None = None,
) -> list[BlockDocument]:
    """Return project blocks, optionally filtered by linked section or line."""
    blocks_dir = _blocks_dir(root)
    if not blocks_dir.is_dir():
        return []

    documents: list[BlockDocument] = []
    for path in sorted(blocks_dir.glob("*.json")):
        try:
            block = BlockDocument.model_validate(read_json(path))
        except (OSError, ValueError):
            continue
        if section is not None and section not in block.links.sections:
            continue
        if line is not None and line not in block.links.lines:
            continue
        documents.append(block)
    return documents


def create_block(
    root: Path,
    line_uuid: str | None = None,
    title: str | None = None,
    section: str | None = None,
    line_uuids: list[str] | None = None,
) -> BlockDocument:
    """Create a block, copying character and text from one or several lines."""
    block = BlockDocument(
        id=uuid.uuid4().hex[:12],
        title=title or "",
        created_at=_now(),
    )

    selected = [uuid_value for uuid_value in (line_uuids or []) if uuid_value]
    if not selected and line_uuid:
        selected = [line_uuid]

    if selected:
        documents = [load_line(root, value) for value in selected]
        first = documents[0]
        block.character = first.character
        block.character_name = first.character_name
        block.text = "\n".join(document.text for document in documents)
        block.title = title or default_title(
            first.character_name, first.character, block.text
        )
        block.links.lines = selected
    else:
        block.title = title or "Untitled block"

    if section:
        block.links.sections = [section]

    # A fresh block always has one usable slot, so its inspector is never empty.
    default_provider = next(iter(PROVIDERS.values()), None)
    if default_provider and default_provider.models:
        model = default_provider.models[0]
        key = slot_key(default_provider.id, model.id)
        block.slots[key] = BlockSlot(
            provider=default_provider.id,
            model=model.id,
            voice=default_provider.voices[0].id if default_provider.voices else None,
            prompt=block.text,
            # Empty on purpose: unset parameters follow the model, then the character.
            params={},
        )
        block.active_slot = key

    return save_block(root, block)


def update_block(
    root: Path,
    block_id: str,
    title: str | None = None,
    links: BlockLinks | None = None,
    active_slot: str | None = None,
    active_take: str | None = None,
    character: str | None = None,
    character_name: str | None = None,
) -> BlockDocument:
    block = load_block(root, block_id)
    if title is not None:
        block.title = title
    if character is not None:
        block.character = character
    if character_name is not None:
        block.character_name = character_name
    if links is not None:
        block.links = links
    if active_slot is not None:
        if active_slot not in block.slots:
            raise ValueError(f"Unknown slot: {active_slot}")
        block.active_slot = active_slot
    if active_take is not None:
        if not any(take.id == active_take for take in block.takes):
            raise ValueError(f"Unknown take: {active_take}")
        block.active_take = active_take
    return save_block(root, block)


def duplicate_block(root: Path, block_id: str) -> BlockDocument:
    """Copy a block: new document, shared take files, copied slots."""
    source = load_block(root, block_id)
    copy = source.model_copy(deep=True)
    copy.id = uuid.uuid4().hex[:12]
    copy.title = f"{source.title} (copy)"
    copy.created_at = _now()
    copy.updated_at = _now()
    return save_block(root, copy)


def delete_block(root: Path, block_id: str) -> None:
    path = block_path(root, block_id)
    if not path.is_file():
        raise FileNotFoundError(f"No block document: {path}")
    path.unlink()


def ensure_slot(root: Path, block_id: str, provider: str, model: str) -> BlockDocument:
    """Create the provider/model slot on first use; return the block either way."""
    block = load_block(root, block_id)
    key = slot_key(provider, model)
    if key not in block.slots:
        block.slots[key] = BlockSlot(provider=provider, model=model, prompt=block.text)
    if block.active_slot is None:
        block.active_slot = key
    return save_block(root, block)


def add_take_file(
    root: Path,
    block_id: str,
    key: str,
    data: bytes,
    extension: str,
    duration_ms: int | None = None,
) -> BlockDocument:
    """Store a dropped file as a take, reusing identical audio."""
    import hashlib

    digest = hashlib.sha256(data).hexdigest()[:12]
    relative = f"media/takes/{block_id}_{digest}.{extension}"
    path = root.expanduser().resolve() / relative
    if not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return add_take(root.expanduser().resolve(), block_id, key, relative, duration_ms)


def update_slot(
    root: Path,
    block_id: str,
    key: str,
    prompt: str | None = None,
    params: dict | None = None,
    voice: str | None = None,
) -> BlockDocument:
    block = load_block(root, block_id)
    slot = block.slots.get(key)
    if slot is None:
        raise KeyError(f"Unknown slot: {key}")
    if prompt is not None and prompt != slot.prompt:
        # Keep the replaced prompt so the conversion action stays reversible.
        slot.history.append(slot.prompt)
        slot.prompt = prompt
    if params is not None:
        slot.params = params
    if voice is not None:
        # An empty string clears the override and falls back to the character mapping.
        slot.voice = voice or None
    slot.updated_at = _now()
    block.active_slot = key
    return save_block(root, block)


def copy_prompt(root: Path, block_id: str, key: str) -> BlockDocument:
    """Reset a slot prompt to the block text, keeping the old prompt in history."""
    block = load_block(root, block_id)
    slot = block.slots.get(key)
    if slot is None:
        raise KeyError(f"Unknown slot: {key}")
    slot.history.append(slot.prompt)
    slot.prompt = block.text
    slot.updated_at = _now()
    return save_block(root, block)


def convert_slot(root: Path, block_id: str, key: str) -> BlockDocument:
    """Replace a slot prompt with the converted line text, keeping the old one."""
    block = load_block(root, block_id)
    slot = block.slots.get(key)
    if slot is None:
        raise KeyError(f"Unknown slot: {key}")
    converted = convert_prompt(block.text)
    if not converted or converted == slot.prompt:
        raise ValueError(f"Nothing to convert for slot: {key}")
    slot.history.append(slot.prompt)
    slot.prompt = converted
    slot.updated_at = _now()
    return save_block(root, block)


def revert_prompt(root: Path, block_id: str, key: str) -> BlockDocument:
    """Restore the most recent prompt from the slot history."""
    block = load_block(root, block_id)
    slot = block.slots.get(key)
    if slot is None:
        raise KeyError(f"Unknown slot: {key}")
    if not slot.history:
        raise ValueError(f"Slot has no prompt history: {key}")
    slot.prompt = slot.history.pop()
    slot.updated_at = _now()
    return save_block(root, block)


def referencing_lines(root: Path, take_id: str) -> list[str]:
    """Return the line UUIDs whose clips point at the given take."""
    referrers: list[str] = []
    for line in list_lines(root):
        if any(
            clip.source.kind == "take" and clip.source.take == take_id
            for clip in line.track.clips
        ):
            referrers.append(line.uuid)
    return referrers


def delete_take(root: Path, block_id: str, take_id: str) -> BlockDocument:
    """Remove a take unless a clip still references it."""
    block = load_block(root, block_id)
    take = next((item for item in block.takes if item.id == take_id), None)
    if take is None:
        raise KeyError(f"Unknown take: {take_id}")
    referrers = referencing_lines(root, take_id)
    if referrers:
        raise ValueError(
            f"Take {take_id} is referenced by lines: {', '.join(referrers)}"
        )
    block.takes = [item for item in block.takes if item.id != take_id]
    return save_block(root, block)


def add_take(
    root: Path,
    block_id: str,
    key: str,
    asset: str,
    duration_ms: int | None = None,
) -> BlockDocument:
    """Append a take to the block history; the slot records who produced it."""
    block = load_block(root, block_id)
    slot = block.slots.get(key)
    if slot is None:
        raise KeyError(f"Unknown slot: {key}")
    block.takes.append(
        Take(
            id=uuid.uuid4().hex[:12],
            slot=key,
            provider=slot.provider,
            model=slot.model,
            asset=asset,
            duration_ms=duration_ms,
            created_at=_now(),
        )
    )
    return save_block(root, block)
