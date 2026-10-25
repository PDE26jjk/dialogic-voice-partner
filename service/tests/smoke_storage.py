"""Storage smoke test: no pytest dependency, run it directly.

    uv run --project service python service/tests/smoke_storage.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

SERVICE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_DIR))

from app.schemas import Selection, SourceRef, WorkspaceState  # noqa: E402
from app.storage import (  # noqa: E402
    create_project,
    load_project,
    load_workspace,
    save_workspace,
)


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

        print("storage smoke OK")


if __name__ == "__main__":
    main()
