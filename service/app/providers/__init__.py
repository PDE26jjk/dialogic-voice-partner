"""Provider adapters: one module per remote TTS service (see design D7)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


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
        return {
            param.id: param.default
            for param in self.params
            if param.default is not None
        }


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
    """One remote service. Implement `synthesize` and declare its models."""

    id: str
    label: str
    models: list[ModelInfo]
    voices: list[VoiceInfo] = []

    @abstractmethod
    def synthesize(
        self,
        model: str,
        prompt: str,
        params: dict,
        voice: str | None = None,
    ) -> SynthesisResult:
        """Return audio for one prompt; raise on provider errors."""

    def find_model(self, model_id: str) -> ModelInfo:
        for model in self.models:
            if model.id == model_id:
                return model
        raise ValueError(f"Unknown model {model_id!r} for provider {self.id!r}")
