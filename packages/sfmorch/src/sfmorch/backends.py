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

from sfmkit import __version__ as SFMKIT_VERSION

from .errors import OrchestratorError
from .modulespec import ModuleSpec

STARTUP_TIMEOUT = 180.0  # generous: a GPU module may load several GB of weights

NO_GPU_WARNING = """\
[sfmorch] '{module}' declares resources.gpu but this Docker daemon cannot pass a
GPU into a container, so it will run on CPU. Expect it to be slow -- often 10-50x.

Having GPUs on the host is not enough; the NVIDIA container toolkit has to be
installed and wired into the daemon:

    # verify the host sees them at all
    nvidia-smi

    # install the toolkit (Debian/Ubuntu), then point docker at it
    sudo apt-get install -y nvidia-container-toolkit
    sudo nvidia-ctk runtime configure --runtime=docker
    sudo systemctl restart docker

    # confirm
    docker run --rm --gpus device=0 sfmstack/runtime:1.0 -c "print('ok')"

Pass cpu_fallback=False to DockerBackend to make this an error instead."""


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


def check_contract(health: dict, spec: ModuleSpec, *, source: str) -> None:
    """Refuse a server carrying a different sfmkit than the orchestrator.

    An image built before a contract change runs the right module name at the
    right version with the wrong runtime underneath, and the symptom is an
    AttributeError several frames inside the module. The image bakes sfmkit in,
    so only an explicit check catches it -- the module version cross-check does
    not, because the module itself did not change.
    """
    theirs = health.get("sfmkit_version")
    if theirs == SFMKIT_VERSION:
        return

    # A missing field is not "unknown, assume fine" -- it means the image predates
    # the check, which makes it stale by definition. Defaulting to permissive here
    # is what let a stale image through as an AttributeError inside a module.
    described = f"sfmkit {theirs}" if theirs else "an sfmkit too old to report its version"
    raise BackendError(
        f"module '{spec.name}' is running {described} but this orchestrator is "
        f"{SFMKIT_VERSION}. Images bake sfmkit in, so rebuild the base first and "
        f"then the module ({source}):\n"
        f"  docker build -t sfmstack/runtime:1.0 -f docker/runtime/Dockerfile .\n"
        f"  docker build -t {spec.image or '<image>'} -f modules/<name>/Dockerfile ."
    )


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
        check_contract(wait_healthy(url), spec, source="the local environment")

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
        cpu_fallback: bool = True,
        gpu_probe_image: str = "sfmstack/runtime:1.0",
    ):
        self.docker = docker
        self.mounts = list(mounts or [])
        self.network = network
        self.extra_run_args = list(extra_run_args or [])
        self.run_as_host_user = run_as_host_user
        # When the daemon cannot pass a GPU through, run GPU modules on CPU with a
        # loud warning rather than failing. The alternative -- refusing outright --
        # makes a host that is merely missing a driver package look like a host
        # that cannot run the pipeline at all. Set False to make it an error.
        self.cpu_fallback = cpu_fallback
        self.gpu_probe_image = gpu_probe_image
        self._gpu_supported: bool | None = None
        self._warned_no_gpu = False

    def available(self) -> bool:
        return shutil.which(self.docker) is not None

    def gpu_supported(self) -> bool:
        """Can this daemon actually hand a GPU to a container?

        Having GPUs on the host is not the same as being able to pass one in --
        that needs the NVIDIA container toolkit wired into the daemon, which is a
        separate install. Without it `--gpus` fails with "could not select device
        driver", several seconds into starting a container, for every GPU module.

        Probed once with a trivial container and cached, because the answer cannot
        change while the daemon is running.
        """
        if self._gpu_supported is None:
            probe = subprocess.run(
                [self.docker, "run", "--rm", "--gpus", "device=0",
                 "--entrypoint", "true", self.gpu_probe_image],
                capture_output=True, text=True,
            )
            self._gpu_supported = probe.returncode == 0
        return self._gpu_supported

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
            if self.gpu_supported():
                # No shell here, so the value must not carry quotes of its own --
                # docker would take them as part of the device spec.
                cmd += ["--gpus", f"device={device}"]
            elif self.cpu_fallback:
                device = None
                if not self._warned_no_gpu:
                    self._warned_no_gpu = True
                    print(NO_GPU_WARNING.format(module=spec.name), file=sys.stderr)
            else:
                raise BackendError(NO_GPU_WARNING.format(module=spec.name))
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
            health = wait_healthy(url)
        except BackendError:
            logs = subprocess.run(
                [self.docker, "logs", "--tail", "60", container_id],
                capture_output=True, text=True,
            ).stdout
            subprocess.run([self.docker, "rm", "-f", container_id], capture_output=True)
            raise BackendError(
                f"module '{spec.name}' container never became healthy. Logs:\n{logs}"
            ) from None

        # Deliberately outside the handler above: a contract mismatch is a
        # started, healthy container running the wrong runtime, and its message
        # says exactly what to rebuild. Folding it into "never became healthy"
        # would replace the actionable error with a misleading one.
        try:
            check_contract(health, spec, source="modules/*/Dockerfile")
        except BackendError:
            subprocess.run([self.docker, "rm", "-f", container_id], capture_output=True)
            raise

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
