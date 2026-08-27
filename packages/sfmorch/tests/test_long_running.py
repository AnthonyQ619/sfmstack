"""Behaviour under varied job durations.

Modules range from a two-second union-find to a forty-minute dense
reconstruction, so nothing in the call path may assume a job is quick. These
tests pin the parts that only break on slow work -- which is exactly the class of
bug that does not show up in a fast test suite.
"""

import time

import pytest
from sfmkit import ArtifactStore

from sfmorch import Orchestrator, SubprocessBackend
from sfmorch.container import ContainerRunner
from sfmorch.gpu import GpuBroker
from sfmorch.service import DurationEstimator, ServiceConfig, SfmService


@pytest.fixture
def service(registry, store):
    from pathlib import Path

    svc = SfmService(
        config=ServiceConfig(
            modules_dir=Path("packages/sfmorch/tests/fixtures/modules").resolve(),
            store_root=store.root,
            inline_wait_s=5.0,
            probe_wait_s=0.2,
        ),
        orchestrator=Orchestrator(store=store, registry=registry),
        registry=registry,
    )
    yield svc
    svc.jobs.shutdown()


# --------------------------------------------------------------------------- #
# The wait is derived per module, not global
# --------------------------------------------------------------------------- #


def test_a_declared_slow_module_is_not_blocked_on(service):
    """SlowModule declares expected_duration_s=120 against a 5s budget, so the
    call must hand back a job id rather than burning the full budget."""
    started = time.monotonic()
    result = service.run("SlowModule", run_id="r", params={"steps": 4, "step_s": 0.4})
    elapsed = time.monotonic() - started

    assert elapsed < 2.0, "blocked on a module declared as slow"
    assert result["status"] in ("queued", "running")
    assert result["poll_after_s"] > 0
    assert result["expected_duration_s"] == 120


def test_the_response_tells_the_caller_when_to_come_back(service):
    result = service.run("SlowModule", run_id="r", params={"steps": 4, "step_s": 0.4})

    assert "poll_after_s" in result
    assert "hint" in result and result["job_id"] in result["hint"]


def test_a_fast_module_still_completes_inline(service):
    """The other half: a quick module must not cost a round trip."""
    result = service.run("MakeScene", run_id="r", params={"n_images": 3})
    assert result["status"] == "ok"
    assert "poll_after_s" not in result


def test_a_cached_result_returns_inline_however_slow_the_module(service):
    """Cache hits are instant regardless of the module's usual cost, so handing
    back a job id for one is pure latency."""
    first = service.run("SlowModule", run_id="r", params={"steps": 2, "step_s": 0.05})
    service.job(first["job_id"], wait_s=30)

    started = time.monotonic()
    again = service.run("SlowModule", run_id="r", params={"steps": 2, "step_s": 0.05})
    assert time.monotonic() - started < 3.0
    assert again["status"] == "ok"
    assert again["cached"] is True


def test_the_estimate_is_learned_from_observed_runs(service):
    assert not service.durations.has_observed("MakeScene")
    service.run("MakeScene", run_id="r", params={"n_images": 3})
    assert service.durations.has_observed("MakeScene")


def test_the_estimator_rises_faster_than_it_falls():
    """Under-estimating costs a wasted round trip on every later call;
    over-estimating costs one bounded block. The asymmetry is deliberate."""
    est = DurationEstimator()
    est.observe("m", 10.0)

    est.observe("m", 100.0)
    after_spike = est.estimate("m", None)

    est2 = DurationEstimator()
    est2.observe("m", 100.0)
    est2.observe("m", 10.0)
    after_drop = est2.estimate("m", None)

    assert after_spike > 50, "a slow observation should move the estimate quickly"
    assert after_drop > 50, "a fast observation should move it only gradually"


# --------------------------------------------------------------------------- #
# Progress
# --------------------------------------------------------------------------- #


def test_progress_is_reported_while_a_job_runs(service):
    """The difference between 'working' and 'wedged' on a twenty-minute job."""
    result = service.run(
        "SlowModule", run_id="r", params={"steps": 8, "step_s": 0.15}, wait_s=0.3
    )
    assert result["status"] in ("queued", "running")

    seen = []
    for _ in range(60):
        record = service.job(result["job_id"])
        if record.get("stage"):
            seen.append(record["stage"])
        if record["status"] in ("ok", "failed"):
            break
        time.sleep(0.05)

    assert seen, "no progress was reported"
    assert any(s.startswith("step ") for s in seen)
    assert service.job(result["job_id"], wait_s=30)["status"] == "ok"


def test_progress_survives_the_container_boundary(registry, store):
    """A module reporting progress inside a container must reach the caller."""
    backend = SubprocessBackend()
    runner = ContainerRunner(backend, gpus=GpuBroker(devices=[]), idle_ttl=3600)
    try:
        from pathlib import Path

        svc = SfmService(
            config=ServiceConfig(
                modules_dir=Path("packages/sfmorch/tests/fixtures/modules").resolve(),
                store_root=store.root,
                inline_wait_s=5.0,
                probe_wait_s=0.2,
            ),
            orchestrator=Orchestrator(store=store, registry=registry, runner=runner),
            registry=registry,
        )
        result = svc.run(
            "SlowModule", run_id="r", params={"steps": 10, "step_s": 0.2}, wait_s=0.5
        )

        stages = []
        for _ in range(80):
            record = svc.job(result["job_id"])
            if record.get("stage"):
                stages.append(record["stage"])
            if record["status"] in ("ok", "failed"):
                break
            time.sleep(0.1)

        assert any(s.startswith("step ") for s in stages), stages
        svc.jobs.shutdown()
    finally:
        runner.shutdown()


# --------------------------------------------------------------------------- #
# The pool must not evict a server that is working
# --------------------------------------------------------------------------- #


def test_a_busy_server_is_never_reaped(registry, store):
    """`last_used` only advances while a job is polled, so before the busy guard
    the longest-running job looked like the stalest server and was the first
    thing reaped. That only ever fails on slow modules."""
    import threading

    backend = SubprocessBackend()
    runner = ContainerRunner(backend, gpus=GpuBroker(devices=[]), idle_ttl=0.0)
    try:
        orch = Orchestrator(store=store, registry=registry, runner=runner)
        done = threading.Event()
        outcome = {}

        def long_job():
            try:
                outcome["result"] = orch.run(
                    "SlowModule", run_id="r", params={"steps": 12, "step_s": 0.15}
                )
            except Exception as e:  # noqa: BLE001
                outcome["error"] = e
            finally:
                done.set()

        thread = threading.Thread(target=long_job)
        thread.start()

        # Hammer the reaper while the job is in flight; TTL is zero, so anything
        # not protected would be stopped immediately.
        for _ in range(15):
            runner.reap_idle()
            time.sleep(0.05)

        done.wait(timeout=60)
        thread.join(timeout=5)

        assert "error" not in outcome, outcome.get("error")
        assert outcome["result"].primary.metric("n_images") == 2
    finally:
        runner.shutdown()


def test_a_slot_is_busy_the_moment_it_is_acquired(registry, store):
    """The deterministic half of the test above.

    `_acquire_slot` holds the pool lock while it spawns, so a `reap_idle()`
    waiting on that lock runs the instant it returns -- before the caller can
    mark the slot busy. Marking it inside the lock is what closes the window;
    leaving it to the caller lost 2 runs in 3, because lock handoff makes the
    waiting reaper the likely winner rather than an unlikely one.

    Asserted directly rather than through a race, so a regression fails every
    time instead of two times in three.
    """
    backend = SubprocessBackend()
    runner = ContainerRunner(backend, gpus=GpuBroker(devices=[]), idle_ttl=0.0)
    try:
        slot = runner._acquire_slot(registry.get("SlowModule"), store.root)
        assert slot.busy == 1

        time.sleep(0.05)  # comfortably past a zero TTL
        assert runner.reap_idle() == []
        assert runner.endpoints()

        # And it becomes reapable again once the caller is done with it.
        slot.busy -= 1
        assert runner.reap_idle() == ["SlowModule@1.0.0"]
    finally:
        runner.shutdown()


def test_an_idle_server_is_still_reaped_once_the_job_finishes(registry, store):
    backend = SubprocessBackend()
    runner = ContainerRunner(backend, gpus=GpuBroker(devices=[]), idle_ttl=0.0)
    try:
        orch = Orchestrator(store=store, registry=registry, runner=runner)
        orch.run("SlowModule", run_id="r", params={"steps": 1, "step_s": 0.01})

        assert runner.endpoints()
        time.sleep(0.05)
        assert "SlowModule@1.0.0" in runner.reap_idle()
    finally:
        runner.shutdown()


def test_a_module_can_declare_its_own_timeout(registry, store):
    """SlowModule declares timeout_s=60; the runner must honour the manifest
    rather than a global default that cannot suit every module."""
    spec = registry.get("SlowModule")
    assert spec.resources.timeout_s == 60
    assert spec.resources.expected_duration_s == 120


def test_a_runner_reaps_its_servers_when_the_process_exits(store, registry):
    """A one-shot process must not leave its module servers running.

    Pooling is per-process -- a new process starts with no slots and spawns its
    own servers -- so nothing is reused across processes and there is nothing to
    gain by outliving one. Before this hook, the ONLY thing that reaped a server
    was another job starting inside the same live process, which for a script
    that runs one module and exits never comes. On this host that leaked 501
    containers holding 347 GB across every GPU, and readers driving the pipeline
    misreported it in writing as other tenants' load.
    """
    import atexit

    backend = SubprocessBackend()
    runner = ContainerRunner(backend, gpus=GpuBroker(devices=[]), idle_ttl=3600)
    orch = Orchestrator(store=store, registry=registry, runner=runner)
    orch.run("SlowModule", run_id="r", params={"steps": 1, "step_s": 0.01})

    assert runner.endpoints(), "expected a live server to reap"

    # The registration is the contract; call it the way interpreter shutdown
    # would. `unregister` first so the real hook cannot fire twice at exit.
    atexit.unregister(runner.shutdown)
    runner.shutdown()

    assert runner.endpoints() == {}
    # Idempotent: a caller using `with` shuts down too, and the hook still fires.
    runner.shutdown()


def test_a_dead_process_id_is_not_mistaken_for_a_live_one(store, registry):
    """The orphan sweep asks the OWNING PID whether anyone still needs a server.

    An idle clock cannot tell a finished process from a slow one, which is why
    the TTL never caught the leak. Liveness has to be exact in both directions:
    a live pid must never be reaped (that kills a running job), and a permission
    error means the process exists under another uid, which is alive.
    """
    import os

    from sfmorch.backends import _pid_alive

    assert _pid_alive(os.getpid())
    assert _pid_alive(1)  # init: exists, not ours to signal
    # A pid that cannot exist. 2^22 is above any Linux pid_max default.
    assert not _pid_alive(2**22 + 7)
