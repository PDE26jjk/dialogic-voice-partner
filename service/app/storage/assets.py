from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from pathlib import Path

from ..schemas import AssetInfo
from .atomic import read_json, write_json_atomic
from .paths import project_paths


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _assets_dir(root: Path) -> Path:
    return project_paths(root.expanduser().resolve())["assets"]


def list_assets(root: Path) -> list[AssetInfo]:
    """Return every recorded or uploaded asset, newest metadata first read order."""
    directory = _assets_dir(root)
    if not directory.is_dir():
        return []

    assets: list[AssetInfo] = []
    for path in sorted(directory.glob("*.json")):
        try:
            assets.append(AssetInfo.model_validate(read_json(path)))
        except (OSError, ValueError):
            continue
    return assets


def save_asset(
    root: Path,
    name: str,
    data: bytes,
    extension: str,
    duration_ms: int | None,
) -> AssetInfo:
    """Write one audio file plus its metadata document into the shared pool."""
    directory = _assets_dir(root)
    directory.mkdir(parents=True, exist_ok=True)

    digest = hashlib.sha256(data).hexdigest()
    asset_id = uuid.uuid4().hex[:12]
    filename = f"{asset_id}.{extension}"
    (directory / filename).write_bytes(data)

    info = AssetInfo(
        id=asset_id,
        name=name,
        path=f"media/assets/{filename}",
        duration_ms=duration_ms,
        hash=digest,
        created_at=_now(),
    )
    write_json_atomic(directory / f"{asset_id}.json", info.model_dump(mode="json"))
    return info


def import_asset(
    root: Path,
    name: str,
    data: bytes,
    extension: str,
    duration_ms: int | None = None,
) -> AssetInfo:
    """Copy a dropped file into the pool, reusing an identical existing asset."""
    digest = hashlib.sha256(data).hexdigest()
    for info in list_assets(root):
        if info.hash == digest:
            return info
    return save_asset(root, name, data, extension, duration_ms)
