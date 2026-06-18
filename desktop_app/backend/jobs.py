"""In-memory background job manager for the desktop backend.

Video generation takes minutes, so the HTTP API can't block on it. Each
generate request creates a Job, runs the pipeline on a worker thread, and
streams progress into the job's event list. The Electron UI polls
`/api/jobs/{id}` to show progress and pick up the result.

This is intentionally simple (single process, in-memory). For a packaged app
that's fine — one user, one machine. Swap for a real queue if you ever serve
multiple users.
"""

from __future__ import annotations

import threading
import traceback
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Job:
    id: str
    status: str = "queued"  # queued | running | done | error
    events: list[dict] = field(default_factory=list)
    result: dict | None = None
    error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def create(self) -> Job:
        job = Job(id=uuid.uuid4().hex)
        with self._lock:
            self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def _append_event(self, job_id: str, stage: str, payload: Any) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.events.append({"stage": stage, "payload": payload})

    def run(self, job_id: str, target, *args, **kwargs) -> None:
        """Run `target(on_event=..., *args, **kwargs)` on a worker thread.

        `target` must accept an `on_event(stage, payload)` callback and return a
        JSON-serializable dict (the result).
        """

        def on_event(stage: str, payload: Any) -> None:
            self._append_event(job_id, stage, payload)

        def worker() -> None:
            with self._lock:
                self._jobs[job_id].status = "running"
            try:
                result = target(*args, on_event=on_event, **kwargs)
                with self._lock:
                    job = self._jobs[job_id]
                    job.result = result
                    job.status = "done"
            except Exception as e:  # surface the failure to the UI
                with self._lock:
                    job = self._jobs[job_id]
                    job.error = f"{e}"
                    job.status = "error"
                    job.events.append(
                        {"stage": "error", "payload": {"trace": traceback.format_exc()[-1500:]}}
                    )

        threading.Thread(target=worker, daemon=True).start()
