"""One GPU, shared by the captures the launcher placed on it.

A dense step runs alone on its GPU, and so does a step whose manifest declares the
large footprint of the correspondence-free estimators (`exclusive_on_gpu`); other GPU
steps share it with each other, as they did in the sparse batch. Two PatchMatch
runs, or one beside a large matcher, exhaust a 48 GB device, and an agent that meets
that out-of-memory error reads it as a property of its own settings. A turnstile
keeps a waiting exclusive step from being starved by a stream of shared ones.
Nothing here is visible to an agent: a gated step is simply slower, and the wait
is logged to `<root>/.gpu/gate.log` only.
"""
import fcntl
import json
import time
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def gpu_gate(root: Path, gpu: int, exclusive: bool, who: str = ""):
    d = Path(root) / ".gpu"
    d.mkdir(parents=True, exist_ok=True)
    t = time.time()
    with open(d / f"gpu{gpu}.turn", "a+") as turn, open(d / f"gpu{gpu}.rw", "a+") as rw:
        fcntl.flock(turn, fcntl.LOCK_EX)
        try:
            fcntl.flock(rw, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        finally:
            fcntl.flock(turn, fcntl.LOCK_UN)
        waited = round(time.time() - t, 1)
        with open(d / "gate.log", "a") as fh:
            fh.write(json.dumps({"t": t, "gpu": gpu, "who": who, "exclusive": exclusive,
                                 "waited_s": waited}) + "\n")
        try:
            yield waited
        finally:
            fcntl.flock(rw, fcntl.LOCK_UN)


def exclusive_on_gpu(desc) -> bool:
    """Does this step get its GPU to itself?

    Dense steps always did. The correspondence-free estimators did not, and two sessions'
    `PoseMapAnything` runs on one device ran out of memory in a batch where three of five
    sessions on that pair met it; each retried and recovered, at a run apiece. Their
    manifests already declare the footprint (24 GB, as `DenseVGGT` does), so the line is
    drawn there rather than at a list of names a new module would not be on.
    """
    res = desc.get("resources") or {}
    return desc.get("kind") == "dense" or (bool(res.get("gpu"))
                                          and float(res.get("min_ram_gb") or 0) >= 24)
