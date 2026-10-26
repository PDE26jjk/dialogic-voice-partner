"""Storage smoke test: no pytest dependency, run it directly.

    uv run --project service python service/tests/smoke_storage.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

SERVICE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_DIR))

from app.schemas import PushLine, Selection, SourceRef, WorkspaceState  # noqa: E402
from app.storage import (  # noqa: E402
    add_take,
    convert_slot,
    create_block,
    create_project,
    delete_block,
    delete_take,
    ensure_slot,
    list_blocks,
    load_block,
    load_project,
    load_workspace,
    revert_prompt,
    save_workspace,
    update_slot,
    upsert_lines,
)
from app.storage.paths import project_paths  # noqa: E402


def main() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary) / "project"

        created = create_project(root, "R:/godot/sample-project", "Demo")
        assert created.name == "Demo"
        assert (root / "project.json").is_file()
        for directory in ("blocks", "lines", "workspaces", "media", "media/takes", "media/assets"):
            assert (root / directory).is_dir(), f"missing {directory}"

        loaded = load_project(root)
        assert loaded.godot_project == "R:/godot/sample-project"
        assert loaded.sections == []

        assert load_workspace(root, "act_2") is None

        saved = save_workspace(
            root,
            WorkspaceState(
                section="act_2",
                source=SourceRef(kind="take", block="blk_1", take="tk_1"),
                in_ms=1000,
                out_ms=3200,
                selection=Selection(in_ms=1200, out_ms=2400),
            ),
        )
        assert saved.updated_at is not None
        assert (root / "workspaces" / "act_2.json").is_file()

        again = load_workspace(root, "act_2")
        assert again is not None
        assert again.out_ms == 3200
        assert again.selection is not None and again.selection.in_ms == 1200

        # A second section keeps its own document.
        assert load_workspace(root, "act_3") is None

        # --- blocks -------------------------------------------------------
        upsert_lines(
            root,
            "scenes/act_1.dtl",
            [
                PushLine(
                    uuid="11111111-aaaa",
                    character="chen_mo",
                    character_name="老陈",
                    text="架子塌下来那一下，我以为要死了。",
                )
            ],
            "inbox",
        )

        block = create_block(root, line_uuid="11111111-aaaa")
        assert block.links.lines == ["11111111-aaaa"]
        assert "老陈" in block.title
        assert block.text.startswith("架子塌下来")
        assert block.character == "chen_mo"
        assert (project_paths(root)["blocks"] / f"{block.id}.json").is_file()

        # The pool is project level, and links filter it without owning it.
        assert len(list_blocks(root)) == 1
        assert len(list_blocks(root, line="11111111-aaaa")) == 1
        assert len(list_blocks(root, line="22222222-bbbb")) == 0

        # Slots are created lazily and start from the line text.
        block = ensure_slot(root, block.id, "volcengine", "seed-tts")
        key = "volcengine/seed-tts"
        assert key in block.slots
        assert block.slots[key].prompt == block.text
        assert block.active_slot == key

        # Editing a prompt keeps the replaced one in history.
        block = update_slot(root, block.id, key, prompt="平静地说出这句话。")
        assert block.slots[key].history == [block.text]

        converted = convert_slot(root, block.id, key)
        assert converted.slots[key].prompt == "架子塌下来那一下，我以为要死了。"
        assert "平静地说出" in converted.slots[key].history[-1]

        reverted = revert_prompt(root, block.id, key)
        assert reverted.slots[key].prompt == "平静地说出这句话。"

        # Takes are shared by the block, not by the slot.
        block = add_take(root, block.id, key, "media/takes/tk_1.wav", 2100)
        assert len(block.takes) == 1
        assert block.takes[0].provider == "volcengine"

        block = delete_take(root, block.id, block.takes[0].id)
        assert block.takes == []

        assert load_block(root, block.id).id == block.id

        delete_block(root, block.id)
        assert list_blocks(root) == []

        print("storage smoke OK")


if __name__ == "__main__":
    main()
