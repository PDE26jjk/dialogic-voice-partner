"""Provider registry: the only place that knows which adapters exist."""

from __future__ import annotations

from ..schemas import ProviderInfo, ProviderModel
from . import Provider
from .mock import MockProvider

PROVIDERS: dict[str, Provider] = {
    provider.id: provider for provider in (MockProvider(),)
}


def get_provider(provider_id: str) -> Provider:
    for key, provider in PROVIDERS.items():
        if key == provider_id:
            return provider
    raise KeyError(f"Unknown provider: {provider_id}")


def provider_infos() -> list[ProviderInfo]:
    """Describe every registered provider for the model picker."""
    return [
        ProviderInfo(
            id=provider.id,
            label=provider.label,
            models=[ProviderModel(id=model.id, label=model.label) for model in provider.models],
        )
        for provider in PROVIDERS.values()
    ]
