import time

import numpy as np
from sfmkit import Ctx, module


@module
def run(ctx: Ctx):
    steps = ctx.params.steps
    for i in range(steps):
        # Exactly the shape a real module's loop takes: report before the work,
        # so a caller polling early sees stage 1 rather than nothing.
        ctx.progress(i / steps, f"step {i + 1}/{steps}")
        time.sleep(ctx.params.step_s)
    ctx.progress(1.0, "sealing")

    out = ctx.output("scene")
    n = 2
    out.save(
        "images",
        paths=np.array([f"/synthetic/{i}.png" for i in range(n)]),
        names=np.array([f"{i}.png" for i in range(n)]),
        size_original=np.full((n, 2), [640, 480], dtype=np.int32),
        size_current=np.full((n, 2), [640, 480], dtype=np.int32),
        scale=np.ones((n, 2), dtype=np.float64),
        content_hash=np.array(f"slow-{steps}"),
    )
    out.metric("n_images", n, direction="neutral")
    out.note(f"Slept through {steps} steps.")
