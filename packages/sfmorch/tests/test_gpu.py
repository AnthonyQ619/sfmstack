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
