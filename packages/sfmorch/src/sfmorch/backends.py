"""Where a module server actually runs.

Two implementations behind one interface:

  DockerBackend      one container per module, the production path
  SubprocessBackend  the server as a local process, same HTTP contract

SubprocessBackend exists so the container path can be tested without Docker and
developed without a rebuild on every edit. It offers no dependency isolation --
that is the entire point of the Docker path -- but it exercises the same server,
the same protocol, and the same lifecycle code, so what it proves transfers.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from .errors import OrchestratorError
from .modulespec import ModuleSpec

STARTUP_TIMEOUT = 180.0  # generous: a GPU module may load several GB of weights


class BackendError(OrchestratorError):
    """A server could not be started, reached, or stopped."""


@dataclass
class Endpoint:
    """A running module server."""

    url: str
    handle: str  # container id, or pid as a string
    module: str
    version: str
    device: int | None = None
    started_at: float = field(default_factory=time.monotonic)
    last_used: float = field(default_factory=time.monotonic)

    def touch(self) -> None:
        self.last_used = time.monotonic()

    @property
    def idle_s(self) -> float:
        return time.monotonic() - self.last_used


# --------------------------------------------------------------------------- #
# HTTP helpers -- urllib, so sfmorch stays dependency-light
# --------------------------------------------------------------------------- #


def http_get(url: str, timeout: float = 30.0) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as r:  # noqa: S310
        return json.loads(r.read() or b"{}")


def http_post(url: str, payload: dict[str, Any], timeout: float = 30.0) -> dict[str, Any]:
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        detail = json.loads(e.read() or b"{}").get("error", "")
        raise BackendError(f"{url} returned {e.code}: {detail}") from e


def wait_healthy(url: str, timeout: float = STARTUP_TIMEOUT, probe: float = 0.25) -> dict:
    deadline = time.monotonic() + timeout
    last = ""
    while time.monotonic() < deadline:
        try:
            return http_get(f"{url}/healthz", timeout=5.0)
        except Exception as e:  # noqa: BLE001 -- startup races are expected
            last = str(e)
            time.sleep(probe)
    raise BackendError(f"{url} did not become healthy within {timeout}s ({last})")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Backend(Protocol):
    def start(self, spec: ModuleSpec, *, store: Path, device: int | None) -> Endpoint: ...
    def stop(self, endpoint: Endpoint) -> None: ...
    def is_alive(self, endpoint: Endpoint) -> bool: ...


# --------------------------------------------------------------------------- #
# Subprocess
# --------------------------------------------------------------------------- #


class SubprocessBackend:
    """Run the module server as a local process under this interpreter.

    No isolation: the module's dependencies must already be importable here. A
    module whose dependencies conflict with the current environment will fail to
    import, which is correct and is exactly the condition Docker resolves.
    """

    def __init__(self, python: str | None = None):
        self.python = python or sys.executable
        self._procs: dict[str, subprocess.Popen] = {}

    def start(self, spec: ModuleSpec, *, store: Path, device: int | None) -> Endpoint:
        if spec.root is None:
            raise BackendError(f"module '{spec.name}' has no directory to serve")

        env = dict(os.environ)
        if device is not None:
            env["CUDA_VISIBLE_DEVICES"] = str(device)

        proc = subprocess.Popen(
            [
                self.python, "-m", "sfmkit.server",
                "--module-dir", str(spec.root),
                "--store", str(store),
                "--host", "127.0.0.1",
                "--port", "0",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )

        # The server announces its bound port, so we never race a pre-bound socket.
        line = proc.stdout.readline() if proc.stdout else ""
        if not line:
            err = proc.stderr.read() if proc.stderr else ""
            proc.kill()
            raise BackendError(f"module '{spec.name}' server failed to start:\n{err}")

        try:
            announced = json.loads(line)
        except json.JSONDecodeError as e:
            proc.kill()
            raise BackendError(
                f"module '{spec.name}' server printed unparseable startup line: {line!r}"
            ) from e

        url = f"http://127.0.0.1:{announced['port']}"
        handle = str(proc.pid)
        self._procs[handle] = proc
        wait_healthy(url)

        return Endpoint(
            url=url, handle=handle, module=spec.name, version=spec.version, device=device
        )

    def stop(self, endpoint: Endpoint) -> None:
        proc = self._procs.pop(endpoint.handle, None)
        if proc is None:
            return
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)

    def is_alive(self, endpoint: Endpoint) -> bool:
        proc = self._procs.get(endpoint.handle)
        return proc is not None and proc.poll() is None


# --------------------------------------------------------------------------- #
# Docker
# --------------------------------------------------------------------------- #


class DockerBackend:
    """One container per module. The production path.

    The artifact store is mounted at the SAME absolute path inside the container
    as outside, so an artifact's recorded paths resolve identically on both
    sides and no translation layer is needed.

    `mounts` carries dataset directories, read-only. SceneLoader reads a host
    path given as a parameter, and a scene built with `resize: none` records
    absolute dataset paths that downstream modules must also be able to reach.
    """

    def __init__(
        self,
        *,
        mounts: list[str] | None = None,
        docker: str = "docker",
        network: str | None = None,
        extra_run_args: list[str] | None = None,
        run_as_host_user: bool = True,
    ):
        self.docker = docker
        self.mounts = list(mounts or [])
        self.network = network
        self.extra_run_args = list(extra_run_args or [])
        self.run_as_host_user = run_as_host_user

    def available(self) -> bool:
        return shutil.which(self.docker) is not None

    def start(self, spec: ModuleSpec, *, store: Path, device: int | None) -> Endpoint:
        if not spec.image:
            raise BackendError(
                f"module '{spec.name}' declares no image; it cannot be containerised"
            )
        if not self.available():
            raise BackendError(f"{self.docker} is not on PATH")

        store = Path(store).resolve()
        port = free_port()

        cmd = [
            self.docker, "run", "--rm", "--detach",
            "--name", f"sfm-{spec.name.lower()}-{port}",
            "--publish", f"127.0.0.1:{port}:8080",
            "--volume", f"{store}:{store}",
        ]

        if self.run_as_host_user:
            # Without this, everything a module writes into the shared store is
            # owned by root on the host: the user cannot delete their own
            # artifacts, and a later in-process run cannot write beside them.
            # HOME is set because a bare uid has no passwd entry, and several
            # libraries (torch hub, matplotlib, huggingface) fall over resolving it.
            cmd += ["--user", f"{os.getuid()}:{os.getgid()}", "--env", "HOME=/tmp"]

        for m in self.mounts:
            cmd += ["--volume", m if ":" in m else f"{m}:{m}:ro"]
        if device is not None:
            # No shell here, so the value must not carry quotes of its own --
            # docker would take them as part of the device spec.
            cmd += ["--gpus", f"device={device}"]
        if self.network:
            cmd += ["--network", self.network]
        cmd += self.extra_run_args
        cmd += [
            spec.image,
            "--module-dir", "/module",
            "--store", str(store),
            "--host", "0.0.0.0",
            "--port", "8080",
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise BackendError(
                f"docker run failed for '{spec.name}' ({spec.image}):\n{result.stderr.strip()}"
            )

        container_id = result.stdout.strip()
        url = f"http://127.0.0.1:{port}"

        try:
            wait_healthy(url)
        except BackendError:
            logs = subprocess.run(
                [self.docker, "logs", "--tail", "60", container_id],
                capture_output=True, text=True,
            ).stdout
            subprocess.run([self.docker, "rm", "-f", container_id], capture_output=True)
            raise BackendError(
                f"module '{spec.name}' container never became healthy. Logs:\n{logs}"
            ) from None

        return Endpoint(
            url=url,
            handle=container_id,
            module=spec.name,
            version=spec.version,
            device=device,
        )

    def stop(self, endpoint: Endpoint) -> None:
        subprocess.run(
            [self.docker, "rm", "-f", endpoint.handle], capture_output=True, text=True
        )

    def is_alive(self, endpoint: Endpoint) -> bool:
        result = subprocess.run(
            [self.docker, "inspect", "-f", "{{.State.Running}}", endpoint.handle],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0 and result.stdout.strip() == "true"
