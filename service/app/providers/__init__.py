"""Provider adapters: one module per remote TTS service (see design D7)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Intent:
    """Provider-neutral description of one line to synthesize."""

    text: str
    character: str | None = None
    character_name: str | None = None
    language: str | None = None
    style: str | None = None


@dataclass(frozen=True)
class ModelParam:
    """One native parameter a model exposes, described for the inspector."""

    id: str
    label: str
    type: str = "number"  # number | text | boolean
    default: Any = None
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = None


@dataclass(frozen=True)
class ModelInfo:
    """A model a provider offers, with the parameters it exposes."""

    id: str
    label: str
    params: list[ModelParam] = field(default_factory=list)

    def defaults(self) -> dict:
        return {param.id: param.default for param in self.params if param.default is not None}


@dataclass(frozen=True)
class VoiceInfo:
    """A named voice a provider can speak with."""

    id: str
    label: str


@dataclass
class SynthesisResult:
    """Audio produced by one provider call."""

    audio: bytes
    extension: str
    duration_ms: int


class Provider(ABC):
    """One remote service. Implement `compile` and `synthesize`."""

    id: str
    label: str
    models: list[ModelInfo]
    voices: list[VoiceInfo] = []
    # "select" shows the declared voices; "text" accepts any id typed by hand.
    voice_mode: str = "select"
    supports_stream: bool = False
    pcm_rate: int = 24000

    def compile(
        self,
        intent: Intent,
        model: str,
        params: dict,
        voice: str | None = None,
        raw: bool = False,
    ) -> dict:
        """Translate the neutral intent into this provider's request body."""
        return {"text": intent.text, "voice": voice, **params}

    @abstractmethod
    def synthesize(
        self,
        model: str,
        prompt: str,
        params: dict,
        voice: str | None = None,
        credentials: dict[str, str] | None = None,
    ) -> SynthesisResult:
        """Return audio for one prompt; raise on provider errors.

        `credentials` carries the project's stored secrets for this provider;
        they are never logged or attached to job records.
        """

    def find_model(self, model_id: str) -> ModelInfo:
        for model in self.models:
            if model.id == model_id:
                return model
        raise ValueError(f"Unknown model {model_id!r} for provider {self.id!r}")
