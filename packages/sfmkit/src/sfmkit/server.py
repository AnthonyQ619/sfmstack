"""The module server.

One container, one module, one long-lived process. Weights loaded once at
startup stay resident, which is what makes a parameter sweep cheap -- the case
the driving agent hits constantly.

Deliberately built on `http.server`. This module ships inside every container, so
a web framework here would become a dependency of modules pinning conflicting
torch and numpy majors. The control plane carries ids and parameters only; every
byte of payload moves through the mounted artifact store, so throughput is not a
consideration.

    python -m sfmkit.server --module-dir /module --store /store [--port 8080]

Endpoints
    GET  /healthz              liveness, warmth, device
    GET  /manifest             this container's module.yaml, verbatim
    POST /run                  enqueue a job -> 202 {job_id}
    GET  /jobs/<id>            status, metrics, diagnostics, log tail
    POST /jobs/<id>/cancel     drop if queued; running jobs cannot be interrupted
"""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import json
import os
import queue
import sys
import threading
import time
import traceback
import uuid
from collections import deque
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import yaml

from .artifact import Artifact
from .module import Ctx, Params, run_module
from .store import ArtifactStore

LOG_TAIL_LINES = 200


# --------------------------------------------------------------------------- #
# Jobs
# --------------------------------------------------------------------------- #


@dataclass
class JobRecord:
    id: str
    request: dict[str, Any]
    status: str = "queued"  # queued | running | ok | failed | cancelled
    outputs: dict[str, str] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    diagnostics: list[dict[str, Any]] = field(default_factory=list)
    error: str = ""
    traceback: str = ""
    log: deque[str] = field(default_factory=lambda: deque(maxlen=LOG_TAIL_LINES))
    started_at: float | None = None
    duration_s: float | None = None
    cancel_requested: bool = False

    def to_doc(self) -> dict[str, Any]:
        return {
            "job_id": self.id,
            "status": self.status,
            "outputs": self.outputs,
            "metrics": self.metrics,
            "diagnostics": self.diagnostics,
            "error": self.error,
            "traceback": self.traceback,
            "log_tail": list(self.log),
            "duration_s": self.duration_s,
        }


class _Tee(io.TextIOBase):
    """Capture a job's stdout into its log while still letting it reach the
    container's own stdout, so `docker logs` remains useful."""

    def __init__(self, sink: deque[str], passthrough):
        self._sink = sink
        self._pass = passthrough
        self._partial = ""

    def write(self, text: str) -> int:
        self._pass.write(text)
        self._partial += text
        while "\n" in self._partial:
            line, _, self._partial = self._partial.partition("\n")
            self._sink.append(line)
        return len(text)

    def flush(self) -> None:
        self._pass.flush()


# --------------------------------------------------------------------------- #
# The module under service
# --------------------------------------------------------------------------- #


class ModuleService:
    """Owns the adapter, the store, and the single worker thread."""

    def __init__(self, module_dir: str | Path, store_root: str | Path):
        self.module_dir = Path(module_dir)
        self.store = ArtifactStore(store_root)

        manifest_path = self.module_dir / "module.yaml"
        if not manifest_path.exists():
            raise SystemExit(f"no module.yaml in {self.module_dir}")
        self.manifest: dict[str, Any] = yaml.safe_load(
            manifest_path.read_text(encoding="utf-8")
        )

        self.name = str(self.manifest["name"])
        self.version = str(self.manifest["version"])
        self.produces = {
            slot: doc["type"] for slot, doc in (self.manifest.get("produces") or {}).items()
        }

        self._jobs: dict[str, JobRecord] = {}
        self._lock = threading.Lock()
        self._queue: queue.Queue[str] = queue.Queue()
        self.warm = False

        self._fn = self._load_adapter()
        self._warmup()

        threading.Thread(target=self._worker, daemon=True, name="job-worker").start()

    # ------------------------------------------------------------------ setup

    def _load_adapter(self):
        entry = str(self.manifest.get("entrypoint", "adapter:run"))
        mod_name, _, func_name = entry.partition(":")
        source = self.module_dir / f"{mod_name}.py"
        if not source.exists():
            raise SystemExit(f"entrypoint {entry!r} but {source} does not exist")

        spec = importlib.util.spec_from_file_location(f"_sfm_{self.name}", source)
        if spec is None or spec.loader is None:
            raise SystemExit(f"cannot import {source}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        self._adapter = module

        fn = getattr(module, func_name or "run", None)
        if fn is None or not getattr(fn, "_is_sfm_module", False):
            raise SystemExit(f"{source}:{func_name} is missing or not @module")
        return fn

    def _warmup(self) -> None:
        """Call the adapter's optional `warmup()`.

        This is where a module loads model weights onto the GPU once, so they are
        resident for every subsequent job. Without it a warm server buys nothing
        over a cold process.
        """
        hook = getattr(self._adapter, "warmup", None)
        if hook is None:
            self.warm = True
            return
        try:
            hook()
            self.warm = True
        except Exception:
            traceback.print_exc()
            self.warm = False

    # ------------------------------------------------------------------- jobs

    def submit(self, request: dict[str, Any]) -> JobRecord:
        job = JobRecord(id=str(request.get("job_id") or uuid.uuid4()), request=request)
        with self._lock:
            self._jobs[job.id] = job
        self._queue.put(job.id)
        return job

    def get(self, job_id: str) -> JobRecord | None:
        with self._lock:
            return self._jobs.get(job_id)

    def cancel(self, job_id: str) -> JobRecord | None:
        job = self.get(job_id)
        if job is None:
            return None
        job.cancel_requested = True
        if job.status == "queued":
            job.status = "cancelled"
        return job

    def _worker(self) -> None:
        while True:
            job = self.get(self._queue.get())
            if job is None or job.status == "cancelled":
                continue
            self._execute(job)

    def _execute(self, job: JobRecord) -> None:
        """Run one job.

        `status` is the publication signal and is therefore written LAST. A
        client polling between "failed" and the assignment of `error` would
        otherwise see a failure with no explanation, which is both useless and
        very hard to reproduce.
        """
        job.status = "running"
        job.started_at = time.monotonic()
        req = job.request

        terminal = "failed"
        try:
            inputs: dict[str, Artifact] = {
                slot: self.store.open(aid) for slot, aid in (req.get("inputs") or {}).items()
            }

            ctx = Ctx(
                store=self.store,
                module=self.name,
                module_version=self.version,
                image=str(req.get("image", "")),
                run=str(req.get("run", "")),
                scene=str(req.get("scene", "")),
                device=req.get("device"),
                inputs=inputs,
                params=Params(req.get("params") or {}),
                output_types=dict(req.get("output_types") or self.produces),
            )

            tee = _Tee(job.log, sys.__stdout__)
            with contextlib.redirect_stdout(tee), contextlib.redirect_stderr(tee):
                sealed = run_module(self._fn, ctx)

            job.outputs = {slot: art.id for slot, art in sealed.items()}
            for art in sealed.values():
                job.metrics.update(
                    {n: m.value for n, m in art.manifest.metrics.items()}
                )
                job.diagnostics.extend(d.to_doc() for d in art.manifest.diagnostics)
            terminal = "ok"

        except Exception as e:  # noqa: BLE001 -- reported, not swallowed
            job.error = f"{type(e).__name__}: {e}"
            job.traceback = traceback.format_exc()
            for line in job.traceback.splitlines():
                job.log.append(line)
            terminal = "failed"

        finally:
            job.duration_s = round(time.monotonic() - (job.started_at or 0), 3)
            job.status = terminal  # last write: everything else is already visible

    # ----------------------------------------------------------------- health

    def health(self) -> dict[str, Any]:
        return {
            "ok": True,
            "module": self.name,
            "version": self.version,
            "warm": self.warm,
            "store": str(self.store.root),
            "device": os.environ.get("CUDA_VISIBLE_DEVICES"),
            "queued": self._queue.qsize(),
        }


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #


class _Handler(BaseHTTPRequestHandler):
    service: ModuleService  # injected on the class before serving
    protocol_version = "HTTP/1.1"

    def log_message(self, *args) -> None:
        pass  # the job log is the useful record; access logs are noise

    # ---------------------------------------------------------------- helpers

    def _send(self, code: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        return json.loads(self.rfile.read(length) or b"{}")

    # ----------------------------------------------------------------- routes

    def do_GET(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler API
        if self.path == "/healthz":
            return self._send(200, self.service.health())

        if self.path == "/manifest":
            return self._send(200, self.service.manifest)

        if self.path.startswith("/jobs/"):
            job = self.service.get(self.path[len("/jobs/") :])
            if job is None:
                return self._send(404, {"error": "no such job"})
            return self._send(200, job.to_doc())

        self._send(404, {"error": f"no route {self.path}"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/run":
            try:
                request = self._body()
            except json.JSONDecodeError as e:
                return self._send(400, {"error": f"malformed JSON: {e}"})

            # Guard against image/manifest skew: a rebuilt image that lags the
            # checked-out module.yaml would otherwise run the wrong code under
            # the right name, and the artifact would carry a version it does not
            # correspond to.
            want_name = request.get("module")
            want_version = request.get("module_version")
            if want_name and want_name != self.service.name:
                return self._send(409, {
                    "error": f"this container serves {self.service.name}, "
                             f"not {want_name}"
                })
            if want_version and want_version != self.service.version:
                return self._send(409, {
                    "error": f"this container serves {self.service.name} "
                             f"{self.service.version}, not {want_version}. "
                             f"Rebuild the image."
                })

            job = self.service.submit(request)
            return self._send(202, {"job_id": job.id})

        if self.path.startswith("/jobs/") and self.path.endswith("/cancel"):
            job_id = self.path[len("/jobs/") : -len("/cancel")]
            job = self.service.cancel(job_id)
            if job is None:
                return self._send(404, {"error": "no such job"})
            return self._send(200, job.to_doc())

        self._send(404, {"error": f"no route {self.path}"})


def serve(module_dir: str, store: str, host: str = "0.0.0.0", port: int = 8080):
    service = ModuleService(module_dir, store)
    handler = type("_BoundHandler", (_Handler,), {"service": service})
    httpd = ThreadingHTTPServer((host, port), handler)
    return service, httpd


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="sfmkit.server")
    ap.add_argument("--module-dir", required=True)
    ap.add_argument("--store", required=True)
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8080,
                    help="0 selects a free port; the chosen port is announced on stdout")
    args = ap.parse_args(argv)

    service, httpd = serve(args.module_dir, args.store, args.host, args.port)

    # Announced so a parent that asked for port 0 can find us without racing on
    # a pre-bound socket.
    print(
        json.dumps({
            "ready": True,
            "port": httpd.server_address[1],
            "module": service.name,
            "version": service.version,
            "warm": service.warm,
        }),
        flush=True,
    )

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
