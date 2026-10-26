"""Provider adapters: one module per remote TTS service (see design D7)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ModelInfo:
    """A model a provider offers, with the parameters it exposes."""

    id: str
    label: str
    params: dict = field(default_factory=dict)


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

    @abstractmethod
    def synthesize(self, model: str, prompt: str, params: dict) -> SynthesisResult:
        """Return audio for one prompt; raise on provider errors."""

    def find_model(self, model_id: str) -> ModelInfo:
        for model in self.models:
            if model.id == model_id:
                return model
        raise ValueError(f"Unknown model {model_id!r} for provider {self.id!r}")
