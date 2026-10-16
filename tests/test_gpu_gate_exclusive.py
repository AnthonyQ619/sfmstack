"""Which steps get a GPU to themselves: dense steps, and the large-footprint estimators."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "harness"))
from gpu_gate import exclusive_on_gpu  # noqa: E402


def test_dense_and_the_estimators_are_exclusive():
    assert exclusive_on_gpu({"kind": "dense", "resources": {"gpu": True, "min_ram_gb": 16}})
    assert exclusive_on_gpu({"kind": "pose", "resources": {"gpu": True, "min_ram_gb": 24}})


def test_matchers_and_cpu_steps_still_share():
    """The control: lighter GPU steps and CPU steps keep sharing, as before."""
    assert not exclusive_on_gpu({"kind": "matching", "resources": {"gpu": True, "min_ram_gb": 8}})
    assert not exclusive_on_gpu({"kind": "sparse", "resources": {"gpu": False, "min_ram_gb": 16}})
    assert not exclusive_on_gpu({"kind": "sparse", "resources": {"gpu": False, "min_ram_gb": 32}})
