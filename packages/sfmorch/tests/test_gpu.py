import threading
import time

import pytest

from sfmorch import GpuBroker, NoGpuAvailable


def test_leases_are_exclusive():
    """One module per device. Two containers sharing a GPU OOM each other
    halfway through, which reads as a confusing partial failure rather than a
    clean queue wait."""
    broker = GpuBroker(devices=[0, 1])
    a = broker.acquire("mod_a")
    b = broker.acquire("mod_b")

    assert {a.device, b.device} == {0, 1}
    with pytest.raises(NoGpuAvailable):
        broker.acquire("mod_c", timeout=0)


def test_release_returns_the_device_to_the_pool():
    broker = GpuBroker(devices=[0])
    lease = broker.acquire("a")
    assert broker.available == []

    broker.release(lease)
    assert broker.available == [0]
    assert broker.acquire("b").device == 0


def test_releasing_twice_is_not_an_error():
    broker = GpuBroker(devices=[0])
    lease = broker.acquire("a")
    broker.release(lease)
    broker.release(lease)
    assert broker.available == [0]


def test_a_waiter_is_woken_when_a_device_frees():
    broker = GpuBroker(devices=[0])
    held = broker.acquire("holder")
    got = []

    def waiter():
        got.append(broker.acquire("waiter", timeout=5).device)

    t = threading.Thread(target=waiter)
    t.start()
    time.sleep(0.1)
    assert got == []

    broker.release(held)
    t.join(timeout=5)
    assert got == [0]


def test_timeout_names_the_current_holders():
    broker = GpuBroker(devices=[0])
    broker.acquire("long_running_vggt")
    with pytest.raises(NoGpuAvailable, match="long_running_vggt"):
        broker.acquire("other", timeout=0.05)


def test_context_manager_releases_on_exception():
    broker = GpuBroker(devices=[0])
    with pytest.raises(RuntimeError):
        with broker.lease("a"):
            raise RuntimeError("module blew up")
    assert broker.available == [0]


def test_no_devices_gives_an_actionable_error():
    broker = GpuBroker(devices=[])
    with pytest.raises(NoGpuAvailable, match="CUDA_VISIBLE_DEVICES"):
        broker.acquire("a")


def test_a_runner_given_an_empty_broker_keeps_it():
    """`self.gpus = gpus or GpuBroker()` replaced a deliberately empty broker with
    one that discovers every device on the host, because __len__ is the device
    count and an empty broker is therefore falsy. It was invisible while the daemon
    could not pass a GPU into a container at all -- the run fell back to CPU either
    way. Once passthrough works, a caller who asked for no GPUs gets all of them,
    and the first symptom is a test suite quietly occupying the machine's GPUs."""
    from sfmorch import ContainerRunner
    from sfmorch.backends import SubprocessBackend

    runner = ContainerRunner(SubprocessBackend(), gpus=GpuBroker(devices=[]))
    assert runner.gpus.devices == []

    # Omitting it entirely still means "discover", which is the useful default.
    assert ContainerRunner(SubprocessBackend()).gpus is not None


def test_held_reports_who_has_what():
    broker = GpuBroker(devices=[0, 1])
    broker.acquire("vggt")
    assert list(broker.held.values()) == ["vggt"]


def test_an_empty_broker_runs_a_gpu_module_on_cpu_instead_of_refusing(store, registry):
    """`gpus=[]` means "this runner gets no devices", and that has to mean CPU.

    It used to raise NoGpuAvailable, which made the one documented way to say
    "run this without a GPU" the one way that could not work -- while every GPU
    module's limitations file promises a CPU fallback. The situation that needs it
    is a host whose devices are all held: the backend's own fallback only triggers
    when the daemon cannot pass a GPU AT ALL, so a visible-but-full device had no
    escape and the run simply failed.

    Exercised through the slot acquisition rather than a full run, because that is
    where the device decision is made and a renamed spec cannot get past the
    server's own name guard.
    """
    import dataclasses

    from sfmorch import SubprocessBackend
    from sfmorch.container import ContainerRunner
    from sfmorch.gpu import GpuBroker

    base = registry.get("SlowModule")
    gpu_spec = dataclasses.replace(
        base, resources=dataclasses.replace(base.resources, gpu=True)
    )

    runner = ContainerRunner(SubprocessBackend(), gpus=GpuBroker(devices=[]))
    try:
        slot = runner._acquire_slot(gpu_spec, store.root)
        # No lease, and nothing claiming a device it never had.
        assert slot.lease is None
        assert slot.endpoint.device is None
    finally:
        runner.shutdown()


def test_a_busy_device_still_waits_rather_than_silently_dropping_to_cpu(registry):
    """The CPU fallback is only for a broker with NO devices.

    A caller who assigned devices wants those devices; quietly taking a 50x slower
    path because a neighbour is mid-job would be a worse surprise than the wait.
    """
    import dataclasses

    from sfmorch.gpu import GpuBroker, NoGpuAvailable

    broker = GpuBroker(devices=[0])
    broker.acquire("someone-else", timeout=0)
    with pytest.raises(NoGpuAvailable):
        broker.acquire("me", timeout=0)
