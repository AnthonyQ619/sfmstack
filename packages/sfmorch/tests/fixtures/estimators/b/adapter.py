import numpy as np
from sfmkit import Ctx, module


@module
def run(ctx: Ctx):
    n = int(ctx.inputs["scene"].load("images", "size_current").shape[0])
    out = ctx.output("poses")
    out.save("poses", **circle(n, ctx.params.shift / 100.0),
             valid=np.ones(n, dtype=bool), image_index=np.arange(n, dtype=np.int32))
    out.metric("registered_fraction", 1.0, direction="higher_better", healthy=(0.9, None))
    out.metric("registered_images", n, direction="higher_better")
    out.metric("mean_reprojection_error", None, direction="lower_better")
    out.metric("median_reprojection_error", None, direction="lower_better")


def circle(n, shift):
    """Cameras on a unit circle looking at its centre, every other one moved out by
    `shift` and the rest in by it."""
    cams = []
    for i in range(n):
        t = 2 * np.pi * i / n
        r = 1.0 + (shift if i % 2 else -shift)
        c = np.array([r * np.cos(t), r * np.sin(t), 0.1 * np.sin(3 * t)])
        R = np.array([[np.cos(t), np.sin(t), 0.0], [0.0, 0.0, -1.0], [-np.sin(t), np.cos(t), 0.0]])
        cams.append(np.hstack([R, (-R @ c)[:, None]]))
    return {"cam_from_world": np.stack(cams)}
