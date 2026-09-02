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

import atexit
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
# A busy solve can hold the server off its own status endpoint. Generous
# enough that an ordinary stall is absorbed, bounded so a genuinely dead
# server is still noticed within a couple of minutes.
POLL_HTTP_TIMEOUT = 30.0
POLL_MISS_LIMIT = 5


@dataclass
class _Slot:
    endpoint: Endpoint
    lease: Lease | None
    busy: int = 0  # in-flight jobs; a slot with any is never reaped or evicted


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
        # `is not None`, not `or`: GpuBroker.__len__ is the device count, so a
        # deliberately empty broker -- "this runner gets no GPUs" -- is falsy and
        # `or` silently replaced it with one that discovers every device on the
        # host. Harmless while the daemon could not pass GPUs through at all;
        # once it can, it means a caller who asked for no GPUs gets all of them.
        self.gpus = gpus if gpus is not None else GpuBroker()
        self.idle_ttl = idle_ttl
        self.gpu_timeout = gpu_timeout
        self.job_timeout = job_timeout

        self._slots: dict[str, _Slot] = {}
        self._lock = threading.RLock()

    def image_digest(self, spec):
        """Delegate to the backend: it is the thing that knows what would run."""
        return self.backend.image_digest(spec)


        # Pooling is per-process: a new process starts with no slots and spawns
        # its own servers on its own ports, so nothing is ever reused ACROSS
        # processes and there is nothing to preserve by outliving one. Without
        # this, every script that runs a module and exits leaves its servers up
        # holding a GPU, and the only thing that would ever reap them is another
        # process happening to start a job -- which for a one-shot script never
        # comes. `shutdown` is idempotent, so this composes with `with`.
        atexit.register(self.shutdown)

    # ------------------------------------------------------------------ pool

    @staticmethod
    def _key(spec: ModuleSpec) -> str:
        return f"{spec.name}@{spec.version}"

    def endpoints(self) -> dict[str, Endpoint]:
        with self._lock:
            return {k: s.endpoint for k, s in self._slots.items()}

    def _acquire_slot(self, spec: ModuleSpec, store: Path) -> _Slot:
        """Return a slot with `busy` ALREADY incremented. The caller must
        decrement it.

        Marking it here rather than in `run()` is not tidiness. `_acquire_slot`
        holds the lock while it spawns, so a concurrent `reap_idle()` queues on
        that lock and acquires it the instant this returns -- before the caller
        can take the lock again to mark the slot busy. It would then find a slot
        with `busy == 0` and an `idle_s` measured from a `last_used` that no job
        has advanced yet, and stop the server out from under a job that is about
        to start. That window is microseconds wide and lost 2 runs in 3, because
        lock handoff makes the waiting reaper the likely winner rather than an
        unlikely one.
        """
        key = self._key(spec)

        with self._lock:
            slot = self._slots.get(key)
            if slot is not None:
                if self.backend.is_alive(slot.endpoint):
                    slot.endpoint.touch()
                    slot.busy += 1
                    return slot
                # Died between jobs -- drop it and start clean rather than
                # surfacing a connection error as a module failure.
                self._discard(key)

            self.reap_idle()

            lease: Lease | None = None
            if spec.resources.gpu and self.gpus.devices:
                try:
                    lease = self.gpus.acquire(key, timeout=0)
                except NoGpuAvailable:
                    if self._evict_lru_gpu_holder():
                        lease = self.gpus.acquire(key, timeout=self.gpu_timeout)
                    else:
                        lease = self.gpus.acquire(key, timeout=self.gpu_timeout)
            elif spec.resources.gpu:
                # O': a broker with NO devices means "this runner gets none", and
                # the honest response is to run on CPU -- which is what the
                # backend already does when the daemon cannot pass a GPU through,
                # and what every GPU module's limitations file promises. Before
                # this it raised instead, so the one documented way to say "run
                # this without a GPU" was the one way that could not work. Someone
                # whose devices were all full read that promise, passed an empty
                # broker, and got an error rather than a slow answer.
                #
                # Only for a deliberately empty broker. Devices that exist but are
                # busy still wait: a caller who assigned devices wants those
                # devices, and silently dropping to a 50x slower path because a
                # neighbour is mid-job would be a worse surprise than the wait.
                pass

            try:
                endpoint = self.backend.start(
                    spec, store=store, device=lease.device if lease else None
                )
            except Exception:
                if lease is not None:
                    self.gpus.release(lease)
                raise

            slot = _Slot(endpoint=endpoint, lease=lease, busy=1)
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
        """Free one device by stopping the least recently used *idle* GPU server.

        Busy slots are excluded. `last_used` only advances while a job is polled,
        so without this guard the longest-running job -- exactly the one worth
        protecting -- would look like the stalest and be evicted first.
        """
        with self._lock:
            holders = [
                (k, s)
                for k, s in self._slots.items()
                if s.lease is not None and s.busy == 0
            ]
            if not holders:
                return False
            key, _ = min(holders, key=lambda kv: kv[1].endpoint.last_used)
            self._discard(key)
            return True

    def reap_idle(self) -> list[str]:
        """Stop servers idle beyond the TTL. Safe to call at any time.

        Never reaps a slot with a job in flight, however long that job has been
        running.
        """
        with self._lock:
            stale = [
                k
                for k, s in self._slots.items()
                if s.busy == 0 and s.endpoint.idle_s > self.idle_ttl
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
        slot = self._acquire_slot(spec, store.root)  # returns it already busy
        try:
            job_id = f"job_{uuid.uuid4().hex[:12]}"
            request = {
                "job_id": job_id,
                "module": spec.name,
                "module_version": spec.version,
                "image": spec.image,
                # From the endpoint, not the spec: the spec says which tag was
                # asked for, the endpoint says which image answered.
                "image_digest": slot.endpoint.image_digest,
                "run": job.run,
                "scene": job.scene,
                "inputs": {name: art.id for name, art in job.inputs.items()},
                "params": job.params,
                "output_types": spec.output_types,
                "device": str(slot.lease.device) if slot.lease else None,
            }

            try:
                http_post(f"{slot.endpoint.url}/run", request)
            except BackendError as e:
                raise ExecutionError(spec.name, e) from e

            record = self._await(slot.endpoint, job_id, job)
        finally:
            with self._lock:
                slot.busy -= 1
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

    def _await(self, endpoint: Endpoint, job_id: str, job: Job) -> dict[str, Any]:
        spec = job.spec
        timeout = self.job_timeout
        if spec.resources.timeout_s:
            timeout = spec.resources.timeout_s
        deadline = time.monotonic() + timeout if timeout else None
        interval = POLL_INTERVAL

        # A poll that times out is NOT evidence the server is gone. A module
        # server answers its own status endpoint from the process running the
        # solve, so a long CPU-bound stretch -- a global bundle adjustment on a
        # large model, which is exactly when the caller most wants the result --
        # can leave it unable to reply inside the HTTP timeout while the job is
        # progressing perfectly well.
        #
        # Failing on the first timeout killed healthy runs at DEFAULT parameters
        # on five captures in one corpus sweep, and reported it as "lost contact",
        # which reads as a crash. Three readers concluded a documented action
        # (raising the iteration cap) was impossible; one spent five runs on it.
        #
        # So a timeout is retried, and only a run of consecutive failures -- or an
        # error that is not a timeout, which IS evidence -- ends the wait. The job
        # record on the server is the authority; one slow answer is not a death.
        misses = 0
        while True:
            try:
                record = http_get(f"{endpoint.url}/jobs/{job_id}", timeout=POLL_HTTP_TIMEOUT)
                misses = 0
            except TimeoutError as e:
                misses += 1
                if misses >= POLL_MISS_LIMIT:
                    raise ExecutionError(
                        spec.name,
                        RuntimeError(
                            f"the module server stopped answering its status "
                            f"endpoint: {POLL_MISS_LIMIT} consecutive polls timed "
                            f"out over ~{int(POLL_MISS_LIMIT * POLL_HTTP_TIMEOUT)}s. "
                            f"The job may still be running inside the container."
                        ),
                    ) from e
                if not self.backend.is_alive(endpoint):
                    raise ExecutionError(
                        spec.name,
                        RuntimeError("the module server exited while the job ran."),
                    ) from e
                time.sleep(interval)
                continue
            except Exception as e:  # noqa: BLE001
                raise ExecutionError(
                    spec.name,
                    RuntimeError(f"lost contact with the module server: {e}"),
                ) from e

            # Keeps the slot's LRU position honest while a long job runs, so a
            # 20-minute reconstruction does not look like the stalest server.
            endpoint.touch()

            if job.on_progress is not None:
                progress = record.get("progress")
                if progress is not None or record.get("stage"):
                    job.on_progress(progress, str(record.get("stage") or ""))

            if record.get("status") in ("ok", "failed", "cancelled"):
                return record

            if deadline is not None and time.monotonic() > deadline:
                try:
                    http_post(f"{endpoint.url}/jobs/{job_id}/cancel", {})
                except Exception:  # noqa: BLE001, S110 -- best effort
                    pass
                raise ExecutionError(
                    spec.name,
                    TimeoutError(
                        f"exceeded the {timeout}s timeout. Raise it with "
                        f"resources.timeout_s in {spec.name}'s module.yaml if this "
                        f"module is legitimately this slow."
                    ),
                )

            time.sleep(interval)
            # Back off so a long reconstruction is not polled thousands of times.
            interval = min(interval * 1.5, POLL_BACKOFF_MAX)
