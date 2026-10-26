"""Generation: provider call -> audio file -> take in the block history."""

from __future__ import annotations

import uuid
from pathlib import Path

from .providers.registry import get_provider
from .schemas import BlockDocument
from .storage import add_take, load_block, slot_key


def generate_take(root: Path, block_id: str, provider_id: str, model: str) -> BlockDocument:
    """Synthesize the block's current prompt and append the result as a take."""
    root = root.expanduser().resolve()
    block = load_block(root, block_id)
    key = slot_key(provider_id, model)
    slot = block.slots.get(key)
    if slot is None:
        raise KeyError(f"Unknown slot: {key}")

    provider = get_provider(provider_id)
    result = provider.synthesize(model, slot.prompt, slot.params)

    take_id = uuid.uuid4().hex[:12]
    relative = f"media/takes/{block.id}_{take_id}.{result.extension}"
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(result.audio)

    return add_take(root, block.id, key, relative, result.duration_ms)
