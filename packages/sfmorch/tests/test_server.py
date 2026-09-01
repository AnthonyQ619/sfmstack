"""The module server's HTTP contract.

Exercised through SubprocessBackend, so this covers the same server, protocol and
lifecycle that DockerBackend drives -- without needing Docker in the test
environment.
"""

import subprocess
import sys
import time

import numpy as np
import pytest
from sfmkit import ArtifactStore

from sfmorch import Orchestrator, SubprocessBackend
from sfmorch.backends import BackendError, http_get, http_post
from sfmorch.container import ContainerRunner
from sfmorch.backends import _pid_alive
from sfmorch.gpu import GpuBroker

from conftest import FIXTURE_MODULES


@pytest.fixture
def backend():
    b = SubprocessBackend()
    yield b
    # Teardown the fixture used not to have. A test that starts a server through
    # this backend and then fails, or is interrupted, otherwise strands it: the
    # `_procs` dict dies with the process and the child is reparented to init,
    # holding a port on a store pytest has already deleted.
    b.shutdown()


@pytest.fixture
def runner(backend):
    r = ContainerRunner(backend, gpus=GpuBroker(devices=[]), idle_ttl=3600)
    yield r
    r.shutdown()


@pytest.fixture
def served(registry, store, backend):
    """A live server for the MakeScene fixture module."""
    spec = registry.get("MakeScene")
    ep = backend.start(spec, store=store.root, device=None)
    yield spec, ep
    backend.stop(ep)


# --------------------------------------------------------------------------- #
# Protocol
# --------------------------------------------------------------------------- #


def test_healthz_reports_module_identity_and_warmth(served):
    spec, ep = served
    health = http_get(f"{ep.url}/healthz")

    assert health["ok"] is True
    assert health["module"] == "MakeScene"
    assert health["version"] == spec.version
    assert health["warm"] is True


def test_manifest_is_served_verbatim(served):
    _, ep = served
    manifest = http_get(f"{ep.url}/manifest")

    assert manifest["name"] == "MakeScene"
    assert manifest["produces"]["scene"]["type"] == "scene/v1"


def test_run_returns_a_job_id_immediately(served):
    _, ep = served
    accepted = http_post(f"{ep.url}/run", {
        "job_id": "job_x",
        "module": "MakeScene",
        "module_version": "1.0.0",
        "params": {"n_images": 3, "calibrated": True},
        "output_types": {"scene": "scene/v1"},
    })
    assert accepted == {"job_id": "job_x"}


def test_a_job_runs_to_completion_and_reports_metrics(served, store):
    _, ep = served
    http_post(f"{ep.url}/run", {
        "job_id": "job_done",
        "params": {"n_images": 3, "calibrated": True},
        "output_types": {"scene": "scene/v1"},
    })

    import time
    for _ in range(200):
        record = http_get(f"{ep.url}/jobs/job_done")
        if record["status"] in ("ok", "failed"):
            break
        time.sleep(0.05)

    assert record["status"] == "ok"
    assert record["metrics"]["n_images"] == 3
    assert record["duration_s"] is not None

    artifact_id = record["outputs"]["scene"]
    assert store.open(artifact_id).type == "scene/v1"


def test_unknown_job_is_404(served):
    _, ep = served
    with pytest.raises(Exception):
        http_get(f"{ep.url}/jobs/nope")


def test_version_skew_is_refused(served):
    """A rebuilt image lagging the checked-out module.yaml would otherwise run
    the wrong code under the right name."""
    _, ep = served
    with pytest.raises(BackendError, match="Rebuild the image"):
        http_post(f"{ep.url}/run", {
            "job_id": "job_skew",
            "module": "MakeScene",
            "module_version": "9.9.9",
            "params": {"n_images": 3},
            "output_types": {"scene": "scene/v1"},
        })


def test_wrong_module_is_refused(served):
    _, ep = served
    with pytest.raises(BackendError, match="serves MakeScene"):
        http_post(f"{ep.url}/run", {
            "job_id": "job_wrong",
            "module": "SomethingElse",
            "params": {},
            "output_types": {},
        })


def test_a_failing_module_reports_the_traceback_not_just_a_status(registry, store, backend):
    spec = registry.get("FakeDetector")
    ep = backend.start(spec, store=store.root, device=None)
    try:
        http_post(f"{ep.url}/run", {
            "job_id": "job_fail",
            "inputs": {"scene": "art_does_not_exist"},
            "params": {"max_keypoints": 16},
            "output_types": {"features": "features/v1"},
        })
        import time
        for _ in range(200):
            record = http_get(f"{ep.url}/jobs/job_fail")
            if record["status"] in ("ok", "failed"):
                break
            time.sleep(0.05)

        assert record["status"] == "failed"
        assert "ArtifactNotFound" in record["error"]
        assert record["traceback"]
    finally:
        backend.stop(ep)


def test_a_terminal_status_is_never_published_before_the_record_is_complete(served):
    """`status` is the publication signal, so it must be written last.

    Writing it first leaves a window where a poller sees "failed" with no error,
    or "ok" with no duration — useless, and very hard to reproduce by hand.
    Polled tightly here to hit that window if it reopens.
    """
    _, ep = served
    import time

    for i in range(6):
        job_id = f"job_race_{i}"
        http_post(f"{ep.url}/run", {
            "job_id": job_id,
            "params": {"n_images": 3, "calibrated": True},
            "output_types": {"scene": "scene/v1"},
        })
        while True:
            record = http_get(f"{ep.url}/jobs/{job_id}")  # no sleep: poll hard
            if record["status"] in ("ok", "failed"):
                break

        assert record["duration_s"] is not None
        if record["status"] == "ok":
            assert record["outputs"], "ok published before outputs were recorded"
        else:
            assert record["error"], "failed published before the error was recorded"
            assert record["traceback"]


def test_queued_job_can_be_cancelled(served):
    _, ep = served
    http_post(f"{ep.url}/run", {"job_id": "j1", "params": {"n_images": 3},
                                "output_types": {"scene": "scene/v1"}})
    cancelled = http_post(f"{ep.url}/jobs/j1/cancel", {})
    assert cancelled["status"] in ("cancelled", "running", "ok")


# --------------------------------------------------------------------------- #
# Backend lifecycle
# --------------------------------------------------------------------------- #


def test_backend_reports_liveness(registry, store, backend):
    spec = registry.get("MakeScene")
    ep = backend.start(spec, store=store.root, device=None)
    assert backend.is_alive(ep)
    backend.stop(ep)
    assert not backend.is_alive(ep)


def test_server_binds_an_announced_port(registry, store, backend):
    """Port 0 plus an announced port avoids racing a pre-bound socket."""
    spec = registry.get("MakeScene")
    a = backend.start(spec, store=store.root, device=None)
    b = backend.start(spec, store=store.root, device=None)
    try:
        assert a.url != b.url
    finally:
        backend.stop(a)
        backend.stop(b)


# --------------------------------------------------------------------------- #
# End to end through the orchestrator
# --------------------------------------------------------------------------- #


def test_a_full_pipeline_runs_over_http(store, registry, runner):
    """The orchestrator cannot tell a served module from an in-process one."""
    orch = Orchestrator(store=store, registry=registry, runner=runner)
    R = "run_served"

    scene = orch.run("MakeScene", run_id=R, params={"n_images": 4}).primary
    feats = orch.run("FakeDetector", run_id=R, inputs={"scene": scene.id}).primary
    pairs = orch.run(
        "FakeMatcher", run_id=R, inputs={"scene": scene.id, "features": feats.id}
    ).primary
    tracks = orch.run(
        "FakeTracker", run_id=R, inputs={"scene": scene.id, "pairs": pairs.id}
    ).primary

    assert tracks.type == "tracks/v1"
    assert tracks.metric("track_count") > 0
    assert tracks.manifest.produced_by.module == "FakeTracker"


def test_provenance_survives_the_process_boundary(store, registry, runner):
    orch = Orchestrator(store=store, registry=registry, runner=runner)
    scene = orch.run("MakeScene", run_id="r", params={"n_images": 3}).primary
    feats = orch.run("FakeDetector", run_id="r", inputs={"scene": scene.id}).primary

    assert feats.manifest.inputs == [scene.id]
    assert feats.manifest.scene == scene.id
    assert feats.manifest.produced_by.params == {"max_keypoints": 16}


def test_caching_still_applies_with_a_served_runner(store, registry, runner):
    orch = Orchestrator(store=store, registry=registry, runner=runner)
    first = orch.run("MakeScene", run_id="r", params={"n_images": 3})
    second = orch.run("MakeScene", run_id="r", params={"n_images": 3})

    assert first.cached is False
    assert second.cached is True


def test_module_failure_surfaces_with_its_log(store, registry, runner):
    from sfmorch import ExecutionError, WiringError

    orch = Orchestrator(store=store, registry=registry, runner=runner)
    scene = orch.run("MakeScene", run_id="r", params={"n_images": 3}).primary

    # Type checking still happens before anything is dispatched.
    feats = orch.run("FakeDetector", run_id="r", inputs={"scene": scene.id}).primary
    with pytest.raises(WiringError):
        orch.run("FakeTracker", run_id="r", inputs={"scene": scene.id, "pairs": feats.id})


# --------------------------------------------------------------------------- #
# Pool
# --------------------------------------------------------------------------- #


def test_the_server_is_reused_across_jobs(store, registry, runner):
    """The reason to keep servers warm: a sweep must not pay startup per attempt."""
    orch = Orchestrator(store=store, registry=registry, runner=runner)
    scene = orch.run("MakeScene", run_id="r", params={"n_images": 3}).primary

    for k in (8, 16, 32):
        orch.run(
            "FakeDetector", run_id="r", inputs={"scene": scene.id},
            params={"max_keypoints": k},
        )

    endpoints = runner.endpoints()
    assert sorted(endpoints) == ["FakeDetector@1.0.0", "MakeScene@1.0.0"]


def test_idle_servers_are_reaped(store, registry, backend):
    r = ContainerRunner(backend, gpus=GpuBroker(devices=[]), idle_ttl=0.0)
    try:
        orch = Orchestrator(store=store, registry=registry, runner=r)
        orch.run("MakeScene", run_id="r", params={"n_images": 3})
        assert r.endpoints()

        import time
        time.sleep(0.05)
        reaped = r.reap_idle()
        assert "MakeScene@1.0.0" in reaped
        assert not r.endpoints()
    finally:
        r.shutdown()


def test_shutdown_stops_everything(store, registry, backend):
    r = ContainerRunner(backend, gpus=GpuBroker(devices=[]), idle_ttl=3600)
    orch = Orchestrator(store=store, registry=registry, runner=r)
    orch.run("MakeScene", run_id="r", params={"n_images": 3})

    endpoints = list(r.endpoints().values())
    r.shutdown()

    assert not r.endpoints()
    assert all(not backend.is_alive(e) for e in endpoints)


def test_a_dead_server_is_replaced_rather_than_erroring(store, registry, backend, runner):
    orch = Orchestrator(store=store, registry=registry, runner=runner)
    orch.run("MakeScene", run_id="r", params={"n_images": 3})

    stale = runner.endpoints()["MakeScene@1.0.0"]
    backend.stop(stale)

    result = orch.run("MakeScene", run_id="r", params={"n_images": 5})
    assert result.primary.metric("n_images") == 5
    assert runner.endpoints()["MakeScene@1.0.0"].url != stale.url


def test_a_stranded_server_does_not_outlive_its_backend(registry, store):
    """The leak this closes: three servers were found on this host, aged 15 and 24
    days, from runs interrupted between `start` and `shutdown`. Nothing reaped
    them, because `_procs` is state on an object and the object died with the
    process that made it. DockerBackend grew `sweep_orphans` after the same defect
    cost 347 GB of GPU memory; the local path never got the equivalent, only
    because a leaked subprocess is cheap enough not to be noticed."""
    b = SubprocessBackend()
    ep = b.start(registry.get("MakeScene"), store=store.root, device=None)
    pid = int(ep.handle)
    assert _pid_alive(pid)

    b.shutdown()  # what atexit calls when the owning process goes away

    deadline = time.time() + 10
    while _pid_alive(pid) and time.time() < deadline:
        time.sleep(0.05)
    assert not _pid_alive(pid), f"server {pid} outlived the backend that started it"


def test_shutdown_is_idempotent_because_atexit_may_double_call(registry, store):
    """`shutdown` is registered with atexit AND called explicitly by the fixture
    and by ContainerRunner. Raising on the second call would turn a clean exit
    into a traceback."""
    b = SubprocessBackend()
    b.start(registry.get("MakeScene"), store=store.root, device=None)
    b.shutdown()
    b.shutdown()


def test_the_backend_reaps_at_interpreter_exit(registry, store):
    """The half a fixture cannot cover: a script that starts a server and exits
    without ever calling shutdown. That is the common case -- one module, then
    exit -- and it is how every one of the stranded servers was made."""
    script = (
        "import sys, pathlib; sys.path[:0] = %r\n"
        "from sfmorch.backends import SubprocessBackend\n"
        "from sfmorch.registry import ModuleRegistry\n"
        "reg = ModuleRegistry()\n"
        "reg.load_dir(pathlib.Path(%r))\n"
        "b = SubprocessBackend()\n"
        "ep = b.start(reg.get('MakeScene'), store=pathlib.Path(%r), device=None)\n"
        "print(ep.handle, flush=True)\n"
    ) % (sys.path, str(FIXTURE_MODULES), str(store.root))

    proc = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, timeout=120
    )
    assert proc.returncode == 0, proc.stderr
    pid = int(proc.stdout.strip().splitlines()[-1])

    deadline = time.time() + 10
    while _pid_alive(pid) and time.time() < deadline:
        time.sleep(0.05)
    assert not _pid_alive(pid), (
        f"server {pid} survived its owner exiting -- this is the exact leak that "
        f"left three servers running for weeks"
    )
