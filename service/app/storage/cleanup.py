"""Explicit cleanup for orphaned blocks and unreferenced take files."""

from __future__ import annotations

from pathlib import Path

from ..schemas import CleanupResult
from .blocks import delete_block, load_block
from .index import load_index, reload_index


def cleanup_orphans(root: Path, remove_files: bool = True) -> CleanupResult:
    """Drop blocks with no surviving line and their unreferenced takes.

    A take referenced by any clip is protected, even when its block is orphaned:
    removing it would leave a dangling clip reference.
    """
    root = root.expanduser().resolve()
    index = load_index(root, rebuild=True)

    removed_blocks: list[str] = []
    removed_takes: list[str] = []
    removed_files: list[str] = []

    for block_id in index.orphans:
        try:
            block = load_block(root, block_id)
        except (FileNotFoundError, ValueError):
            continue

        for take in block.takes:
            if take.id in index.take_refs:
                continue
            removed_takes.append(take.id)
            if not remove_files:
                continue
            path = root / take.asset
            if path.is_file():
                path.unlink()
                removed_files.append(take.asset)

        delete_block(root, block_id)
        removed_blocks.append(block_id)

    reload_index(root)
    return CleanupResult(
        blocks_removed=removed_blocks,
        takes_removed=removed_takes,
        files_removed=removed_files,
    )
