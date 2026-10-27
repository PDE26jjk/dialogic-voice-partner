"""Persisted generation jobs.

A job is written before the provider call and updated after it, so a restart in
the middle of a generation reports the job as failed and retryable instead of
silently losing it.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

from ..schemas import Job
from .atomic import read_json, write_json_atomic
from .paths import project_paths

JOBS_DIR = "jobs"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _jobs_dir(root: Path) -> Path:
    directory = project_paths(root.expanduser().resolve())["root"] / JOBS_DIR
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def create_job(root: Path, block: str, provider: str, model: str) -> Job:
    job = Job(
        id=uuid.uuid4().hex[:12],
        block=block,
        provider=provider,
        model=model,
        state="running",
        created_at=_now(),
        updated_at=_now(),
    )
    save_job(root, job)
    return job


def save_job(root: Path, job: Job) -> None:
    job.updated_at = _now()
    write_json_atomic(_jobs_dir(root) / f"{job.id}.json", job.model_dump(mode="json"))


def list_jobs(root: Path) -> list[Job]:
    jobs: list[Job] = []
    directory = _jobs_dir(root)
    for path in sorted(directory.glob("*.json")):
        try:
            jobs.append(Job.model_validate(read_json(path)))
        except (OSError, ValueError):
            continue
    return jobs


def fail_interrupted(root: Path) -> int:
    """Mark jobs left running by a previous process as failed."""
    count = 0
    for job in list_jobs(root):
        if job.state != "running":
            continue
        job.state = "failed"
        job.error = "Interrupted by a restart"
        save_job(root, job)
        count += 1
    return count
