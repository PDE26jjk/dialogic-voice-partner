"""Line rendering and export.

A line is mixed from its clips: every clip is read as mono at the output rate,
placed at its start position and summed. The result is peak-limited and written
as a 16-bit PCM WAV next to the Godot project, so the editor can point a voice
event at it.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
import wave
from array import array
from datetime import datetime, timezone
from pathlib import Path

from .schemas import BlockDocument, LineDocument, ProjectSettings, SourceRef
from .storage import load_block, save_line

OUTPUT_RATE = 44100
OUTPUT_CHANNELS = 1
INT16_MAX = 32767


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _read_mono(path: Path, rate: int) -> array:
    """Read a PCM WAV as mono 16-bit samples at `rate`, resampling if needed."""
    with wave.open(str(path), "rb") as handle:
        channels = handle.getnchannels()
        width = handle.getsampwidth()
        source_rate = handle.getframerate()
        frames = handle.readframes(handle.getnframes())

    if width != 2:
        raise ValueError(f"Only 16-bit WAV is supported, got {width * 8}-bit in {path.name}")

    samples = array("h")
    samples.frombytes(frames)
    if channels > 1:
        mixed = array("h")
        for index in range(0, len(samples) - channels + 1, channels):
            total = 0
            for channel in range(channels):
                total += samples[index + channel]
            mixed.append(total // channels)
        samples = mixed

    if source_rate != rate:
        samples = _resample(samples, source_rate, rate)
    return samples


def _resample(samples: array, source: int, target: int) -> array:
    if source == target or not samples:
        return samples
    ratio = source / target
    length = max(1, int(len(samples) / ratio))
    output = array("h", bytes(length * 2))
    last = len(samples) - 1
    for index in range(length):
        position = index * ratio
        low = int(position)
        high = min(low + 1, last)
        fraction = position - low
        value = samples[low] * (1 - fraction) + samples[high] * fraction
        output[index] = max(-INT16_MAX, min(INT16_MAX, int(value)))
    return output


def _resolve_source(root: Path, source: SourceRef) -> Path | None:
    """Map a clip source to the audio file it points at.

    A take reference resolves through the block's active take, so switching the
    active take re-targets every clip that uses the block.
    """
    if source.kind == "asset":
        return root / source.asset if source.asset else None
    if not source.block:
        return None
    try:
        block: BlockDocument = load_block(root, source.block)
    except (FileNotFoundError, ValueError):
        return None

    take = None
    if block.active_take:
        take = next((item for item in block.takes if item.id == block.active_take), None)
    if take is None and source.take:
        take = next((item for item in block.takes if item.id == source.take), None)
    if take is None and block.takes:
        take = block.takes[-1]
    return root / take.asset if take else None


def render_line(root: Path, line: LineDocument) -> tuple[bytes, int]:
    """Mix a line into WAV bytes; returns the payload and its duration in ms."""
    clips = line.track.clips
    duration_ms = max(
        0,
        *[
            clip.start_ms + max(0, clip.out_ms - clip.in_ms)
            for clip in clips
        ],
    )
    if duration_ms <= 0:
        return _to_wav(array("h", bytes(0)), 0), 0

    total = int(duration_ms * OUTPUT_RATE / 1000)
    mix = array("d", bytes(total * 8))

    for clip in clips:
        path = _resolve_source(root, clip.source)
        if path is None or not path.is_file():
            continue
        try:
            data = _read_mono(path, OUTPUT_RATE)
        except (wave.Error, ValueError, EOFError):
            continue

        start = int(clip.start_ms * OUTPUT_RATE / 1000)
        offset = int(clip.in_ms * OUTPUT_RATE / 1000)
        length = int((clip.out_ms - clip.in_ms) * OUTPUT_RATE / 1000)
        length = min(length, max(0, len(data) - offset), max(0, total - start))
        for index in range(length):
            mix[start + index] += data[offset + index]

    output = array("h", bytes(total * 2))
    for index in range(total):
        # Sum as-is; only clamp what would overflow int16 so nothing wraps.
        output[index] = max(-INT16_MAX, min(INT16_MAX, int(mix[index])))

    return _to_wav(output, OUTPUT_RATE), duration_ms


def _to_wav(samples: array, rate: int) -> bytes:
    from io import BytesIO

    buffer = BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(OUTPUT_CHANNELS)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(samples.tobytes())
    return buffer.getvalue()


def export_line(
    root: Path,
    settings: ProjectSettings,
    line: LineDocument,
) -> dict:
    """Render one line and write it under `<godot>/audio/voice/<section>/`."""
    root = root.expanduser().resolve()
    payload, duration_ms = render_line(root, line)

    godot = Path(settings.godot_project)
    if not godot.is_dir():
        raise FileNotFoundError(f"Godot project folder not found: {godot}")

    section = line.section or "inbox"
    target = godot / "audio" / "voice" / section / f"{line.uuid}.wav"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)

    # Godot paths use res://, so make the destination relative to the project.
    try:
        audio_res = "res://" + str(target.relative_to(godot)).replace("\\", "/")
    except ValueError:
        audio_res = target.as_posix()

    writeback_ok, writeback_error = notify_editor(settings, line, audio_res)

    line.export_path = str(target)
    line.exported_at = _now()
    line.export_status = "exported" if writeback_ok else "pending_writeback"
    save_line(root, line)

    return {
        "line_uuid": line.uuid,
        "path": str(target),
        "duration_ms": duration_ms,
        "short_source": _has_silence_padding(root, line),
        "writeback_ok": writeback_ok,
        "writeback_error": writeback_error,
    }


def notify_editor(
    settings: ProjectSettings,
    line: LineDocument,
    audio_res: str,
) -> tuple[bool, str | None]:
    """Ask the Godot editor to point the voice event at the exported file.

    A failure is not an export failure: the file is already on disk and the line
    is marked pending so it can be retried alone.
    """
    endpoint = settings.editor_endpoint.rstrip("/") + "/apply-export"
    body = json.dumps(
        {
            "line_uuid": line.uuid,
            "audio_res_path": audio_res,
            "dtl_path": line.dtl,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            if 200 <= response.status < 300:
                return True, None
            return False, f"HTTP {response.status}"
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return False, str(exc)


def _has_silence_padding(root: Path, line: LineDocument) -> bool:
    """True when a clip spans more than its source provides (padded with silence)."""
    for clip in line.track.clips:
        path = _resolve_source(root, clip.source)
        if path is None or not path.is_file():
            continue
        try:
            with wave.open(str(path), "rb") as handle:
                available_ms = handle.getnframes() / handle.getframerate() * 1000
        except (wave.Error, EOFError):
            continue
        if clip.out_ms - clip.in_ms > available_ms + 1:
            return True
    return False
