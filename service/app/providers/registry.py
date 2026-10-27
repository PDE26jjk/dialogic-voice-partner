"""Provider registry: the only place that knows which adapters exist."""

from __future__ import annotations

from ..schemas import ProviderInfo, ProviderModel, ProviderParam, ProviderVoice
from . import Provider
from .mock import MockProvider
from .sapi import SapiProvider

PROVIDERS: dict[str, Provider] = {
    provider.id: provider for provider in (SapiProvider(), MockProvider())
}


def get_provider(provider_id: str) -> Provider:
    for key, provider in PROVIDERS.items():
        if key == provider_id:
            return provider
    raise KeyError(f"Unknown provider: {provider_id}")


def provider_infos() -> list[ProviderInfo]:
    """Describe every registered provider for the model and voice pickers."""
    return [
        ProviderInfo(
            id=provider.id,
            label=provider.label,
            models=[
                ProviderModel(
                    id=model.id,
                    label=model.label,
                    params=[
                        ProviderParam(
                            id=param.id,
                            label=param.label,
                            type=param.type,
                            default=param.default,
                            minimum=param.minimum,
                            maximum=param.maximum,
                            step=param.step,
                        )
                        for param in model.params
                    ],
                )
                for model in provider.models
            ],
            voices=[
                ProviderVoice(id=voice.id, label=voice.label)
                for voice in provider.voices
            ],
        )
        for provider in PROVIDERS.values()
    ]
