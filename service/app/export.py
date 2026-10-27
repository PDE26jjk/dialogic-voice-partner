"""Line rendering and export.

A line is mixed from its clips: every clip is read as mono at the output rate,
placed at its start position and summed. The sum is clamped (never limited) and
written as a PCM WAV next to the Godot project, so the editor can point a voice
event at it.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
import urllib.error
import urllib.request
import wave
from array import array
from datetime import datetime, timezone
from pathlib import Path

from imageio_ffmpeg import get_ffmpeg_exe

from .schemas import BlockDocument, ExportSettings, LineDocument, ProjectSettings, SourceRef
from .storage import load_block, save_line

OUTPUT_RATE = 44100
INT16_MAX = 32767


def _now() -> datetime:
    return datetime.now(timezone.utc)


_FFMPEG: str | None = None


def _ffmpeg_exe() -> str | None:
    """Locate the bundled ffmpeg binary once, if the package provides one."""
    global _FFMPEG
    if _FFMPEG is None:
        try:
            _FFMPEG = get_ffmpeg_exe()
        except Exception:  # noqa: BLE001 - treat a missing binary as "no ffmpeg"
            _FFMPEG = ""
    return _FFMPEG or None


def _transcode(path: Path, rate: int) -> array:
    """Decode any audio file through ffmpeg into mono 16-bit samples."""
    exe = _ffmpeg_exe()
    if exe is None:
        raise ValueError(
            f"{path.name} is not a WAV file and ffmpeg is unavailable"
        )

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
        temporary = Path(handle.name)
    try:
        subprocess.run(
            [
                exe,
                "-y",
                "-v",
                "error",
                "-i",
                str(path),
                "-ac",
                "1",
                "-ar",
                str(rate),
                "-sample_fmt",
                "s16",
                str(temporary),
            ],
            check=True,
            capture_output=True,
            timeout=180,
        )
        with wave.open(str(temporary), "rb") as decoded:
            frames = decoded.readframes(decoded.getnframes())
        return _decode_pcm(frames, 2, path.name)
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or b"").decode("utf-8", "replace").strip()
        raise ValueError(f"ffmpeg could not decode {path.name}: {detail}") from exc
    finally:
        temporary.unlink(missing_ok=True)


def _decode_pcm(frames: bytes, width: int, name: str) -> array:
    """Decode 8/16/24/32-bit PCM frames into signed 16-bit samples."""
    if width == 2:
        samples = array("h")
        samples.frombytes(frames)
        return samples

    samples = array("h")
    if width == 1:
        # 8-bit WAV is unsigned.
        samples.extend((byte - 128) << 8 for byte in frames)
        return samples

    if width == 3:
        for index in range(0, len(frames) - 2, 3):
            value = int.from_bytes(frames[index : index + 3], "little", signed=True)
            samples.append(value >> 8)
        return samples

    if width == 4:
        for index in range(0, len(frames) - 3, 4):
            value = int.from_bytes(frames[index : index + 4], "little", signed=True)
            samples.append(value >> 16)
        return samples

    raise ValueError(f"Unsupported WAV depth: {width * 8}-bit in {name}")


def _read_mono(path: Path, rate: int) -> array:
    """Read a PCM WAV as mono 16-bit samples at `rate`, resampling if needed."""
    try:
        with wave.open(str(path), "rb") as handle:
            channels = handle.getnchannels()
            width = handle.getsampwidth()
            source_rate = handle.getframerate()
            frames = handle.readframes(handle.getnframes())
    except (wave.Error, EOFError):
        # Anything ffmpeg can read (mp3, flac, ogg, ...) becomes 16-bit mono.
        return _transcode(path, rate)

    samples = _decode_pcm(frames, width, path.name)
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


def _render_samples(root: Path, line: LineDocument, rate: int) -> tuple[array, int]:
    """Mix a line's clips into 16-bit mono samples at `rate`."""
    clips = line.track.clips
    duration_ms = max(
        0,
        *[clip.start_ms + max(0, clip.out_ms - clip.in_ms) for clip in clips],
    )
    if duration_ms <= 0:
        return array("h"), 0

    total = int(duration_ms * rate / 1000)
    mix = array("d", bytes(total * 8))

    for clip in clips:
        path = _resolve_source(root, clip.source)
        if path is None or not path.is_file():
            continue
        try:
            data = _read_mono(path, rate)
        except (wave.Error, ValueError, EOFError):
            continue

        start = int(clip.start_ms * rate / 1000)
        offset = int(clip.in_ms * rate / 1000)
        length = int((clip.out_ms - clip.in_ms) * rate / 1000)
        length = min(length, max(0, len(data) - offset), max(0, total - start))
        gain = max(0.0, min(4.0, clip.gain))
        for index in range(length):
            mix[start + index] += data[offset + index] * gain

    output = array("h", bytes(total * 2))
    for index in range(total):
        # Sum as-is; only clamp what would overflow int16 so nothing wraps.
        output[index] = max(-INT16_MAX, min(INT16_MAX, int(mix[index])))
    return output, duration_ms


def render_line(
    root: Path,
    line: LineDocument,
    export: ExportSettings | None = None,
) -> tuple[bytes, int]:
    """Mix a line into WAV bytes; returns the payload and its duration in ms."""
    settings = export or ExportSettings()
    samples, duration_ms = _render_samples(root, line, settings.sample_rate)
    return (
        _to_wav(samples, settings.sample_rate, settings.channels, settings.bit_depth),
        duration_ms,
    )


def render_range(
    root: Path,
    line: LineDocument,
    start_ms: int,
    end_ms: int,
    export: ExportSettings | None = None,
) -> tuple[bytes, int]:
    """Render a slice of a line; used to save a selection as a reusable asset."""
    settings = export or ExportSettings()
    samples, _ = _render_samples(root, line, settings.sample_rate)
    start = max(0, int(start_ms * settings.sample_rate / 1000))
    end = min(len(samples), int(end_ms * settings.sample_rate / 1000))
    if end <= start:
        raise ValueError("The selection is empty")
    return (
        _to_wav(samples[start:end], settings.sample_rate, settings.channels, settings.bit_depth),
        int((end - start) * 1000 / settings.sample_rate),
    )


def _to_wav(
    samples: array,
    rate: int,
    channels: int = 1,
    bit_depth: int = 16,
) -> bytes:
    from io import BytesIO

    if channels > 1:
        interleaved = array("h")
        for value in samples:
            for _ in range(channels):
                interleaved.append(value)
        samples = interleaved

    if bit_depth == 16:
        payload = samples.tobytes()
    elif bit_depth == 8:
        payload = bytes(max(0, min(255, (value >> 8) + 128)) for value in samples)
    elif bit_depth == 24:
        buffer_bytes = bytearray()
        for value in samples:
            buffer_bytes += ((value << 8) & 0xFFFFFF).to_bytes(3, "little")
        payload = bytes(buffer_bytes)
    else:
        raise ValueError(f"Unsupported bit depth: {bit_depth}")

    buffer = BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(bit_depth // 8)
        handle.setframerate(rate)
        handle.writeframes(payload)
    return buffer.getvalue()


def export_line(
    root: Path,
    settings: ProjectSettings,
    line: LineDocument,
) -> dict:
    """Render one line and write it under `<godot>/audio/voice/<section>/`."""
    root = root.expanduser().resolve()
    export = settings.export
    if export.container != "wav":
        raise ValueError(f"Unsupported export container: {export.container}")

    payload, duration_ms = render_line(root, line, export)

    godot = Path(settings.godot_project)
    if not godot.is_dir():
        raise FileNotFoundError(f"Godot project folder not found: {godot}")

    section = line.section or "inbox"
    target = godot / "audio" / "voice" / section / f"{line.uuid}.wav"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)

    # Godot paths use res://, so make the destination relative to the project.
    audio_res = _res_path(godot, target)
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


def retry_writeback(
    root: Path,
    settings: ProjectSettings,
    line: LineDocument,
) -> tuple[bool, str | None]:
    """Re-send a pending write-back without rendering the audio again."""
    if not line.export_path:
        raise ValueError("Line has no exported file yet; export it first")

    godot = Path(settings.godot_project)
    audio_res = _res_path(godot, Path(line.export_path))
    ok, error = notify_editor(settings, line, audio_res)

    line.export_status = "exported" if ok else "pending_writeback"
    if ok:
        line.exported_at = _now()
    save_line(root, line)
    return ok, error


def _res_path(godot: Path, target: Path) -> str:
    try:
        return "res://" + str(target.relative_to(godot)).replace("\\", "/")
    except ValueError:
        return target.as_posix()


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
