"""Per-project credentials.

Secrets live in ``secrets.json`` next to the project documents. They are never
echoed back through the API, never written into job records and never logged.
"""

from __future__ import annotations

from pathlib import Path

from .atomic import read_json, write_json_atomic

SECRETS_FILE = "secrets.json"


def _path(root: Path) -> Path:
    return root.expanduser().resolve() / SECRETS_FILE


def load_secrets(root: Path) -> dict[str, dict[str, str]]:
    path = _path(root)
    if not path.is_file():
        return {}
    try:
        data = read_json(path)
    except (OSError, ValueError):
        return {}
    return {str(provider): dict(values) for provider, values in data.items()}


def save_secret(root: Path, provider: str, values: dict[str, str]) -> list[str]:
    """Merge one provider's credentials; returns the providers that have any."""
    secrets = load_secrets(root)
    secrets[provider] = {key: value for key, value in values.items() if value}
    path = _path(root)
    write_json_atomic(path, secrets)
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return sorted(name for name, values in secrets.items() if values)


def get_secret(root: Path, provider: str, key: str) -> str | None:
    return load_secrets(root).get(provider, {}).get(key)


def configured_providers(root: Path) -> list[str]:
    return sorted(name for name, values in load_secrets(root).items() if values)
