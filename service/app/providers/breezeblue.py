"""breeze.blue cloud TTS provider.

Mirrors the tray client in Genie-TTS/relay/tts_breezeblue.py: the streaming
endpoint returns headerless signed 16-bit mono PCM at 24 kHz, so the adapter
wraps it in a WAV container before handing it back.

Credentials come from the project's secrets file (``api_key``) and are never
logged.
"""

from __future__ import annotations

import io
import json
import urllib.error
import urllib.request
import wave

from typing import Iterator

from . import ModelInfo, ModelParam, Provider, SynthesisResult, VoiceInfo

API_BASE = "https://api.breeze.blue"
DEFAULT_VOICE = "voc_kwje43kewnst"
PCM_RATE = 24000

SPEED = ModelParam(
    id="speed",
    label="Speed",
    type="number",
    default=1.0,
    minimum=0.5,
    maximum=2.0,
    step=0.05,
)

LANGUAGE = ModelParam(
    id="language_code",
    label="Language",
    type="text",
    default="zh",
)


class BreezeBlueProvider(Provider):
    id = "breezeblue"
    label = "BreezeBlue (cloud)"
    models = [
        ModelInfo(
            id="breeze-tts-2",
            label="Breeze TTS 2",
            params=[SPEED, LANGUAGE],
        )
    ]
    # Voice ids are account specific, so the panel accepts a typed id.
    voices: list[VoiceInfo] = []
    voice_mode = "text"
    supports_stream = True

    def stream_pcm(
        self,
        model: str,
        prompt: str,
        params: dict,
        voice: str | None = None,
        credentials: dict[str, str] | None = None,
    ) -> Iterator[bytes]:
        """Yield the provider's headerless PCM as it arrives."""
        api_key = (credentials or {}).get("api_key", "").strip()
        if not api_key:
            raise ValueError(
                "BreezeBlue needs an API key. Store one under credentials "
                "for provider 'breezeblue' first."
            )

        voice_id = voice or DEFAULT_VOICE
        url = f"{API_BASE}/v1/text-to-speech/{voice_id}/stream"
        payload = {
            "text": prompt,
            "model_id": model,
            "voice_settings": {"speed": float(params.get("speed", 1.0))},
        }
        language = params.get("language_code")
        if language:
            payload["language_code"] = language

        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "xi-api-key": api_key,
                "Content-Type": "application/json",
                "Accept": "audio/*",
                "User-Agent": "Mozilla/5.0",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                while True:
                    chunk = response.read(4096)
                    if not chunk:
                        break
                    yield chunk
        except urllib.error.HTTPError as exc:
            raise ValueError(f"BreezeBlue failed with HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ValueError(f"BreezeBlue unreachable: {exc}") from exc

    def synthesize(
        self,
        model: str,
        prompt: str,
        params: dict,
        voice: str | None = None,
        credentials: dict[str, str] | None = None,
    ) -> SynthesisResult:
        api_key = (credentials or {}).get("api_key", "").strip()
        if not api_key:
            raise ValueError(
                "BreezeBlue needs an API key. Store one under credentials "
                "for provider 'breezeblue' first."
            )

        voice_id = voice or DEFAULT_VOICE
        url = f"{API_BASE}/v1/text-to-speech/{voice_id}/stream"
        payload = {
            "text": prompt,
            "model_id": model,
            "voice_settings": {"speed": float(params.get("speed", 1.0))},
        }
        language = params.get("language_code")
        if language:
            payload["language_code"] = language

        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "xi-api-key": api_key,
                "Content-Type": "application/json",
                "Accept": "audio/*",
                # Cloudflare in front of the API rejects the default urllib agent.
                "User-Agent": "Mozilla/5.0",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                pcm = response.read()
        except urllib.error.HTTPError as exc:
            raise ValueError(f"BreezeBlue failed with HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ValueError(f"BreezeBlue unreachable: {exc}") from exc

        if not pcm:
            raise ValueError("BreezeBlue returned no audio")

        samples = len(pcm) // 2
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(PCM_RATE)
            handle.writeframes(pcm[: samples * 2])

        return SynthesisResult(
            audio=buffer.getvalue(),
            extension="wav",
            duration_ms=int(samples * 1000 / PCM_RATE),
        )
