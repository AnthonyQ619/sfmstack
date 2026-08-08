"""GPU leases.

One module holds one GPU exclusively for as long as its container is alive.
Simple, and it removes a whole class of failure -- two containers sharing a
device and OOMing each other halfway through a long reconstruction, which
produces a confusing partial failure rather than a clean queue wait.

The cost is that concurrency is capped at the device count, so a wide parameter
sweep queues. That is the right trade: a queued job finishes late, a
double-booked one fails.
"""

from __future__ import annotations

import os
import subprocess
import threading
from contextlib import contextmanager
from dataclasses import dataclass


class NoGpuAvailable(RuntimeError):
    """No device came free within the timeout."""


def discover_devices() -> list[int]:
    """Visible CUDA device indices.

    `CUDA_VISIBLE_DEVICES` wins when set, because that is how an operator fences
    off part of a shared box and the orchestrator must not reach past it.
    """
    env = os.environ.get("CUDA_VISIBLE_DEVICES")
    if env is not None:
        return [int(x) for x in env.split(",") if x.strip() != ""]

    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=index", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return []

    return [int(line) for line in out.split() if line.strip().isdigit()]


@dataclass(frozen=True)
class Lease:
    device: int
    holder: str


class GpuBroker:
    """Exclusive device leases, handed out FIFO.

    Fairness is per-waiter rather than per-session: with one module per device
    and containers that outlive a single job, a session cannot monopolise the
    pool by submitting faster than others.
    """

    def __init__(self, devices: list[int] | None = None):
        self.devices = list(devices) if devices is not None else discover_devices()
        self._free: list[int] = list(self.devices)
        self._held: dict[int, str] = {}
        self._cv = threading.Condition()

    def __len__(self) -> int:
        return len(self.devices)

    @property
    def available(self) -> list[int]:
        with self._cv:
            return sorted(self._free)

    @property
    def held(self) -> dict[int, str]:
        with self._cv:
            return dict(self._held)

    def acquire(self, holder: str, *, timeout: float | None = None) -> Lease:
        if not self.devices:
            raise NoGpuAvailable(
                "no CUDA devices visible. Set CUDA_VISIBLE_DEVICES, or route "
                "this module to a CPU runner if it does not need a GPU."
            )

        with self._cv:
            if not self._cv.wait_for(lambda: bool(self._free), timeout=timeout):
                raise NoGpuAvailable(
                    f"no GPU free within {timeout}s; all {len(self.devices)} are "
                    f"held by {sorted(self._held.values())}"
                )
            device = self._free.pop(0)
            self._held[device] = holder
            return Lease(device=device, holder=holder)

    def release(self, lease: Lease) -> None:
        with self._cv:
            if self._held.pop(lease.device, None) is None:
                return  # already released; releasing twice is not an error
            if lease.device not in self._free:
                self._free.append(lease.device)
            self._cv.notify()

    @contextmanager
    def lease(self, holder: str, *, timeout: float | None = None):
        acquired = self.acquire(holder, timeout=timeout)
        try:
            yield acquired
        finally:
            self.release(acquired)
