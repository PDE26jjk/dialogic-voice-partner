"""Generation: provider call -> audio file -> take in the block history."""

from __future__ import annotations

import uuid
from pathlib import Path

from .providers.registry import get_provider
from .schemas import BlockDocument
from .storage import add_take, get_character_voice, load_block, load_project, slot_key


def generate_take(root: Path, block_id: str, provider_id: str, model: str) -> BlockDocument:
    """Synthesize the block's current prompt and append the result as a take."""
    root = root.expanduser().resolve()
    block = load_block(root, block_id)
    key = slot_key(provider_id, model)
    slot = block.slots.get(key)
    if slot is None:
        raise KeyError(f"Unknown slot: {key}")

    provider = get_provider(provider_id)
    # A slot-level voice wins; otherwise the character mapping applies.
    voice = slot.voice
    if provider.voices and not voice:
        settings = load_project(root)
        voice = get_character_voice(settings, block.character, provider_id)
    if provider.voices and not voice:
        raise ValueError(
            f"Character '{block.character or 'unknown'}' has no voice on "
            f"provider '{provider_id}'. Pick a voice in the model slot or in the "
            f"characters panel."
        )

    result = provider.synthesize(model, slot.prompt, slot.params, voice)

    take_id = uuid.uuid4().hex[:12]
    relative = f"media/takes/{block.id}_{take_id}.{result.extension}"
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(result.audio)

    return add_take(root, block.id, key, relative, result.duration_ms)
