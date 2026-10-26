from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

REPLACE_ATTEMPTS = 5
REPLACE_DELAY = 0.02


def write_json_atomic(path: Path, data: Any) -> None:
    """Write JSON so an interrupted write never leaves a partial document.

    The temporary name is unique per call: two overlapping writers of the same
    document must not fight over one scratch file. On Windows a reader can hold
    the destination for a few milliseconds, so the rename is retried briefly
    instead of surfacing a spurious 500.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{uuid.uuid4().hex[:8]}.tmp")
    temporary.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    for attempt in range(REPLACE_ATTEMPTS):
        try:
            os.replace(temporary, path)
            return
        except PermissionError:
            if attempt == REPLACE_ATTEMPTS - 1:
                temporary.unlink(missing_ok=True)
                raise
            time.sleep(REPLACE_DELAY)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))
