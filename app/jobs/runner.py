"""In-process async job runner backed by the jobs table.

Long work (ingestion = vision calls, evaluation = 12+ calls) never blocks a request. Swap for arq/Celery
when running multiple API replicas; the Job table and API contract stay the same.
"""
from __future__ import annotations

import asyncio
import logging
import traceback
from typing import Any, Awaitable, Callable

from app.storage import db

log = logging.getLogger(__name__)
_tasks: set[asyncio.Task] = set()

Work = Callable[[Callable[[str], None]], Awaitable[tuple[str | None, str | None, dict | None]]]


def _update(job_id: str, **fields: Any) -> None:
    with db.session() as s:
        job = s.get(db.Job, job_id)
        for k, v in fields.items():
            setattr(job, k, v)
        s.commit()


def submit(kind: str, work: Work) -> str:
    """work(stage_cb) -> (result_type, result_id, inline_result)."""
    with db.session() as s:
        job = db.Job(kind=kind)
        s.add(job)
        s.commit()
        job_id = job.id

    async def run() -> None:
        _update(job_id, status="running", stage="started")
        try:
            rtype, rid, inline = await work(lambda stage: _update(job_id, stage=stage))
            _update(job_id, status="succeeded", stage="done", result_type=rtype, result_id=rid, result=inline)
        except Exception as e:  # report every failure on the job; never crash the server
            log.error("job %s failed: %s", job_id, traceback.format_exc())
            _update(job_id, status="failed", error=f"{type(e).__name__}: {e}")

    t = asyncio.get_running_loop().create_task(run())
    _tasks.add(t)
    t.add_done_callback(_tasks.discard)
    return job_id


def recover_interrupted() -> None:
    """Jobs that were running when the process died are marked failed so clients can retry."""
    with db.session() as s:
        for job in s.query(db.Job).filter(db.Job.status.in_(["queued", "running"])):
            job.status, job.error = "failed", "interrupted by server restart; resubmit"
        s.commit()


async def drain() -> None:
    """Await all running jobs (tests)."""
    while _tasks:
        await asyncio.gather(*list(_tasks), return_exceptions=True)
