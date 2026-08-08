"""ContainerRunner -- executes a Job in a module server, keeping servers warm.

Slots into the same `Runner` seam as `InProcessRunner`; the orchestrator cannot
tell them apart. What it adds is a pool of long-lived servers, so a parameter
sweep against one module reuses a process with its weights already resident
instead of paying startup per attempt.

Lifecycle, and why:

  spawn on demand      most modules are never touched in a given run
  idle TTL             a warm server holding a GPU it is not using is waste
  LRU evict on demand  with one module per GPU, an 8-device box can hold 8 warm
                       servers; the ninth request evicts the least recently used
                       rather than failing
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sfmkit import Artifact, ArtifactStore

from .backends import Backend, BackendError, Endpoint, http_get, http_post
from .errors import ExecutionError
from .gpu import GpuBroker, Lease, NoGpuAvailable
from .modulespec import ModuleSpec
from .runner import Job

DEFAULT_IDLE_TTL = 600.0  # ten minutes
POLL_INTERVAL = 0.25
POLL_BACKOFF_MAX = 2.0


@dataclass
class _Slot:
    endpoint: Endpoint
    lease: Lease | None


class ContainerRunner:
    """Runs jobs against pooled module servers."""

    def __init__(
        self,
        backend: Backend,
        *,
        gpus: GpuBroker | None = None,
        idle_ttl: float = DEFAULT_IDLE_TTL,
        gpu_timeout: float | None = 600.0,
        job_timeout: float | None = None,
    ):
        self.backend = backend
        self.gpus = gpus or GpuBroker()
        self.idle_ttl = idle_ttl
        self.gpu_timeout = gpu_timeout
        self.job_timeout = job_timeout

        self._slots: dict[str, _Slot] = {}
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ pool

    @staticmethod
    def _key(spec: ModuleSpec) -> str:
        return f"{spec.name}@{spec.version}"

    def endpoints(self) -> dict[str, Endpoint]:
        with self._lock:
            return {k: s.endpoint for k, s in self._slots.items()}

    def _acquire_slot(self, spec: ModuleSpec, store: Path) -> _Slot:
        key = self._key(spec)

        with self._lock:
            slot = self._slots.get(key)
            if slot is not None:
                if self.backend.is_alive(slot.endpoint):
                    slot.endpoint.touch()
                    return slot
                # Died between jobs -- drop it and start clean rather than
                # surfacing a connection error as a module failure.
                self._discard(key)

            self.reap_idle()

            lease: Lease | None = None
            if spec.resources.gpu:
                try:
                    lease = self.gpus.acquire(key, timeout=0)
                except NoGpuAvailable:
                    if self._evict_lru_gpu_holder():
                        lease = self.gpus.acquire(key, timeout=self.gpu_timeout)
                    else:
                        lease = self.gpus.acquire(key, timeout=self.gpu_timeout)

            try:
                endpoint = self.backend.start(
                    spec, store=store, device=lease.device if lease else None
                )
            except Exception:
                if lease is not None:
                    self.gpus.release(lease)
                raise

            slot = _Slot(endpoint=endpoint, lease=lease)
            self._slots[key] = slot
            return slot

    def _discard(self, key: str) -> None:
        slot = self._slots.pop(key, None)
        if slot is None:
            return
        try:
            self.backend.stop(slot.endpoint)
        finally:
            if slot.lease is not None:
                self.gpus.release(slot.lease)

    def _evict_lru_gpu_holder(self) -> bool:
        """Free one device by stopping the least recently used GPU server."""
        with self._lock:
            holders = [(k, s) for k, s in self._slots.items() if s.lease is not None]
            if not holders:
                return False
            key, _ = min(holders, key=lambda kv: kv[1].endpoint.last_used)
            self._discard(key)
            return True

    def reap_idle(self) -> list[str]:
        """Stop servers idle beyond the TTL. Safe to call at any time."""
        with self._lock:
            stale = [
                k for k, s in self._slots.items() if s.endpoint.idle_s > self.idle_ttl
            ]
            for key in stale:
                self._discard(key)
            return stale

    def shutdown(self) -> None:
        with self._lock:
            for key in list(self._slots):
                self._discard(key)

    def __enter__(self) -> "ContainerRunner":
        return self

    def __exit__(self, *exc) -> None:
        self.shutdown()

    # ------------------------------------------------------------------- run

    def run(self, job: Job, store: ArtifactStore) -> dict[str, Artifact]:
        spec = job.spec
        slot = self._acquire_slot(spec, store.root)
        job_id = f"job_{uuid.uuid4().hex[:12]}"

        request = {
            "job_id": job_id,
            "module": spec.name,
            "module_version": spec.version,
            "image": spec.image,
            "run": job.run,
            "scene": job.scene,
            "inputs": {slot_name: art.id for slot_name, art in job.inputs.items()},
            "params": job.params,
            "output_types": spec.output_types,
            "device": str(slot.lease.device) if slot.lease else None,
        }

        try:
            http_post(f"{slot.endpoint.url}/run", request)
        except BackendError as e:
            raise ExecutionError(spec.name, e) from e

        record = self._await(slot.endpoint, job_id, spec)
        slot.endpoint.touch()

        if record["status"] != "ok":
            raise ExecutionError(
                spec.name,
                RuntimeError(
                    f"{record.get('error') or 'module reported failure'}\n"
                    + "\n".join(record.get("log_tail") or [])
                ),
            )

        return {
            slot_name: store.open(aid)
            for slot_name, aid in (record.get("outputs") or {}).items()
        }

    def _await(self, endpoint: Endpoint, job_id: str, spec: ModuleSpec) -> dict[str, Any]:
        deadline = (
            time.monotonic() + self.job_timeout if self.job_timeout else None
        )
        interval = POLL_INTERVAL

        while True:
            try:
                record = http_get(f"{endpoint.url}/jobs/{job_id}", timeout=30.0)
            except Exception as e:  # noqa: BLE001
                raise ExecutionError(
                    spec.name,
                    RuntimeError(f"lost contact with the module server: {e}"),
                ) from e

            if record.get("status") in ("ok", "failed", "cancelled"):
                return record

            if deadline is not None and time.monotonic() > deadline:
                try:
                    http_post(f"{endpoint.url}/jobs/{job_id}/cancel", {})
                except Exception:  # noqa: BLE001, S110 -- best effort
                    pass
                raise ExecutionError(
                    spec.name,
                    TimeoutError(f"exceeded job_timeout of {self.job_timeout}s"),
                )

            time.sleep(interval)
            # Back off so a long reconstruction is not polled thousands of times.
            interval = min(interval * 1.5, POLL_BACKOFF_MAX)
