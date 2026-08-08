"""Asynchronous job tracking.

`Orchestrator.run` blocks, which is right for a script and wrong for a tool call:
a dense reconstruction runs for tens of minutes and no MCP client should hold a
request open that long.

So the service layer submits work here and returns a job id. Short jobs still
complete inline -- `submit_and_wait` gives the caller a bounded grace period, so
a SIFT run that takes two seconds comes back in one round trip and only genuinely
slow work turns into polling.

Concurrency is deliberately generous here. The real limit is the GPU broker's
exclusive leases; throttling in two places would just make the second one lie.
"""

from __future__ import annotations

import threading
import time
import traceback
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable

DEFAULT_WORKERS = 16


@dataclass
class JobHandle:
    id: str
    kind: str  # run | replay | build | smoke_test
    label: str = ""
    run_id: str = ""
    status: str = "queued"  # queued | running | ok | failed
    result: dict[str, Any] | None = None
    error: str = ""
    traceback: str = ""
    submitted_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None

    @property
    def duration_s(self) -> float | None:
        if self.started_at is None:
            return None
        end = self.finished_at if self.finished_at is not None else time.time()
        return round(end - self.started_at, 3)

    @property
    def done(self) -> bool:
        return self.status in ("ok", "failed")

    def to_doc(self) -> dict[str, Any]:
        doc: dict[str, Any] = {
            "job_id": self.id,
            "kind": self.kind,
            "status": self.status,
            "duration_s": self.duration_s,
        }
        if self.label:
            doc["label"] = self.label
        if self.run_id:
            doc["run_id"] = self.run_id
        if self.status == "ok" and self.result is not None:
            doc.update(self.result)
        if self.status == "failed":
            doc["error"] = self.error
            doc["traceback"] = self.traceback
        return doc


class JobManager:
    def __init__(self, max_workers: int = DEFAULT_WORKERS):
        self._pool = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="sfm-job"
        )
        self._jobs: dict[str, JobHandle] = {}
        self._futures: dict[str, Future] = {}
        self._lock = threading.Lock()

    # ---------------------------------------------------------------- submit

    def submit(
        self,
        fn: Callable[[], dict[str, Any]],
        *,
        kind: str,
        label: str = "",
        run_id: str = "",
    ) -> JobHandle:
        handle = JobHandle(
            id=f"job_{uuid.uuid4().hex[:12]}", kind=kind, label=label, run_id=run_id
        )
        with self._lock:
            self._jobs[handle.id] = handle

        def wrapped() -> None:
            handle.started_at = time.time()
            handle.status = "running"
            try:
                result = fn()
                handle.result = result
                terminal = "ok"
            except Exception as e:  # noqa: BLE001 -- reported, not swallowed
                handle.error = f"{type(e).__name__}: {e}"
                handle.traceback = traceback.format_exc()
                terminal = "failed"
            finally:
                handle.finished_at = time.time()
                # Status last: a poller must never see a terminal state before
                # the payload that explains it. Same discipline as the module
                # server, and the same bug if it is not observed.
                handle.status = terminal

        with self._lock:
            self._futures[handle.id] = self._pool.submit(wrapped)
        return handle

    def submit_and_wait(
        self,
        fn: Callable[[], dict[str, Any]],
        *,
        kind: str,
        label: str = "",
        run_id: str = "",
        wait_s: float = 0.0,
    ) -> JobHandle:
        """Submit, then give it `wait_s` to finish before returning.

        Lets fast work complete in a single tool call while slow work degrades
        gracefully into polling, without the caller having to know in advance
        which it is.
        """
        handle = self.submit(fn, kind=kind, label=label, run_id=run_id)
        if wait_s > 0:
            self.wait(handle.id, timeout=wait_s)
        return handle

    # ----------------------------------------------------------------- query

    def get(self, job_id: str) -> JobHandle | None:
        with self._lock:
            return self._jobs.get(job_id)

    def wait(self, job_id: str, timeout: float | None = None) -> JobHandle | None:
        handle = self.get(job_id)
        if handle is None:
            return None
        with self._lock:
            future = self._futures.get(job_id)
        if future is not None:
            try:
                future.result(timeout=timeout)
            except Exception:  # noqa: BLE001, S110 -- recorded on the handle
                pass
            except TimeoutError:
                pass
        return handle

    def list(
        self, *, run_id: str | None = None, status: str | None = None, limit: int = 50
    ) -> list[JobHandle]:
        with self._lock:
            jobs = list(self._jobs.values())
        if run_id is not None:
            jobs = [j for j in jobs if j.run_id == run_id]
        if status is not None:
            jobs = [j for j in jobs if j.status == status]
        jobs.sort(key=lambda j: j.submitted_at, reverse=True)
        return jobs[:limit]

    def shutdown(self, wait: bool = False) -> None:
        self._pool.shutdown(wait=wait, cancel_futures=not wait)
