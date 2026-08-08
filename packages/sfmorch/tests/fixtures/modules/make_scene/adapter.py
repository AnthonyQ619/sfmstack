import numpy as np
from sfmkit import Ctx, module


@module
def run(ctx: Ctx):
    n = ctx.params.n_images
    out = ctx.output("scene")

    out.save(
        "images",
        paths=np.array([f"/synthetic/img_{i:04d}.png" for i in range(n)]),
        names=np.array([f"img_{i:04d}.png" for i in range(n)]),
        size_original=np.full((n, 2), [1600, 1200], dtype=np.int32),
        size_current=np.full((n, 2), [800, 600], dtype=np.int32),
        scale=np.full((n, 2), [0.5, 0.5], dtype=np.float64),
        content_hash=np.array(f"synthetic-{n}"),
    )

    if ctx.params.calibrated:
        K = np.array([[400.0, 0, 400.0], [0, 400.0, 300.0], [0, 0, 1.0]])
        out.save(
            "calibration",
            intrinsics=K[None, ...],
            distortions=np.zeros((1, 5), dtype=np.float64),
        )

    out.metric("n_images", n, direction="neutral")
    out.note(f"Synthetic scene with {n} images.")
