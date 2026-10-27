"""Generation: neutral intent -> provider compile -> audio -> take."""

from __future__ import annotations

import uuid
from pathlib import Path

from .providers import Intent
from .providers.registry import get_provider
from .schemas import BatchGenerateResult, BlockDocument, Job
from .storage import (
    add_take,
    create_job,
    get_character_voice,
    load_block,
    ensure_slot,
    load_project,
    save_job,
    slot_key,
)


def _resolve_voice(root: Path, block: BlockDocument, slot, provider) -> str | None:
    """A slot-level voice wins; otherwise the character mapping applies."""
    voice = slot.voice
    if provider.voices and not voice:
        settings = load_project(root)
        voice = get_character_voice(settings, block.character, provider.id)
    if provider.voices and not voice:
        raise ValueError(
            f"Character '{block.character or 'unknown'}' has no voice on "
            f"provider '{provider.id}'. Pick a voice in the model slot or in the "
            f"characters panel."
        )
    return voice


def generate_take(
    root: Path,
    block_id: str,
    provider_id: str,
    model: str,
    raw: bool = False,
) -> BlockDocument:
    """Synthesize the block's current prompt and append the result as a take."""
    root = root.expanduser().resolve()
    block = load_block(root, block_id)
    key = slot_key(provider_id, model)
    slot = block.slots.get(key)
    if slot is None:
        raise KeyError(f"Unknown slot: {key}")

    provider = get_provider(provider_id)
    job = create_job(root, block_id, provider_id, model)
    try:
        voice = _resolve_voice(root, block, slot, provider)
        params = {**provider.find_model(model).defaults(), **slot.params}
        if raw:
            # Raw mode forwards the prompt verbatim, tags included.
            body = {"text": slot.prompt, "voice": voice, **params}
            text = slot.prompt
        else:
            intent = Intent(
                text=block.text or slot.prompt,
                character=block.character,
                character_name=block.character_name,
            )
            body = provider.compile(intent, model, params, voice)
            text = str(body.get("text", slot.prompt))

        result = provider.synthesize(model, text, params, voice)

        take_id = uuid.uuid4().hex[:12]
        relative = f"media/takes/{block.id}_{take_id}.{result.extension}"
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(result.audio)

        job.state = "done"
        job.take = take_id
        save_job(root, job)
        return add_take(root, block.id, key, relative, result.duration_ms)
    except Exception as exc:
        job.state = "failed"
        job.error = str(exc)
        save_job(root, job)
        raise


def generate_batch(
    root: Path,
    block_id: str,
    providers: list[str],
    raw: bool = False,
) -> list[BatchGenerateResult]:
    """Generate one take per provider; one failure never blocks the others."""
    results: list[BatchGenerateResult] = []
    for provider_id in providers:
        try:
            provider = get_provider(provider_id)
            if not provider.models:
                raise ValueError(f"Provider '{provider_id}' declares no model")
            model = provider.models[0].id
            # Ensure the slot exists so a first-time provider still works.
            block = load_block(root, block_id)
            if slot_key(provider_id, model) not in block.slots:
                ensure_slot(root, block_id, provider_id, model)

            updated = generate_take(root, block_id, provider_id, model, raw=raw)
            latest = updated.takes[-1] if updated.takes else None
            results.append(
                BatchGenerateResult(
                    provider=provider_id,
                    ok=True,
                    take=latest.id if latest else None,
                )
            )
        except Exception as exc:  # noqa: BLE001 - reported per provider
            results.append(
                BatchGenerateResult(provider=provider_id, ok=False, error=str(exc))
            )
    return results
