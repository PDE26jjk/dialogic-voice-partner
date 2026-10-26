"""A local provider that synthesizes a tone, so the pipeline runs without keys.

It exists to exercise generate -> take -> play -> export end to end. Replace it
with a real adapter; nothing else in the service knows which provider answered.
"""

from __future__ import annotations

import io
import wave

from . import ModelInfo, Provider, SynthesisResult
SAMPLE_RATE = 24000
TONE_HZ = 220
MS_PER_CHARACTER = 110
MIN_DURATION_MS = 700


class MockProvider(Provider):
    id = "mock"
    label = "Mock (local tone)"
    models = [
        ModelInfo(id="tone", label="Tone", params={"pitch": 1.0}),
        ModelInfo(id="tone-low", label="Low tone", params={"pitch": 0.7}),
    ]

    def synthesize(self, model: str, prompt: str, params: dict) -> SynthesisResult:
        info = self.find_model(model)
        pitch = float(params.get("pitch", info.params.get("pitch", 1.0)))
        duration_ms = max(MIN_DURATION_MS, len(prompt.strip()) * MS_PER_CHARACTER)
        frequency = TONE_HZ * pitch

        frames = int(SAMPLE_RATE * duration_ms / 1000)
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(SAMPLE_RATE)
            handle.writeframes(_tone_frames(frames, frequency))

        return SynthesisResult(
            audio=buffer.getvalue(),
            extension="wav",
            duration_ms=duration_ms,
        )


def _tone_frames(frames: int, frequency: float) -> bytes:
    """Build a 16-bit mono sine wave with a short fade in and out."""
    import math

    amplitude = 0.18 * 32767
    fade = min(SAMPLE_RATE // 50, frames // 2)
    samples = bytearray()
    for index in range(frames):
        envelope = 1.0
        if index < fade:
            envelope = index / fade
        elif index > frames - fade:
            envelope = (frames - index) / fade
        value = int(amplitude * envelope * math.sin(2 * math.pi * frequency * index / SAMPLE_RATE))
        samples += value.to_bytes(2, "little", signed=True)
    return bytes(samples)
