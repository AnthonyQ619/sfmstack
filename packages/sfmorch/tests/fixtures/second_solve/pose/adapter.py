import numpy as np
from sfmkit import Ctx, module


@module
def run(ctx: Ctx):
    p = ctx.params
    if p.fail_at and p.local_ba_window == p.fail_at:
        raise ValueError(f"staged failure at local_ba_window={p.fail_at}")

    n = int(ctx.inputs["scene"].load("images", "size_current").shape[0])
    out = ctx.output("poses")
    out.save(
        "poses",
        cam_from_world=np.tile(np.hstack([np.eye(3), np.zeros((3, 1))]), (n, 1, 1)),
        valid=np.ones(n, dtype=bool),
        image_index=np.arange(n, dtype=np.int32),
    )
    escaped = 5 if p.local_ba_window < p.escape_below else 0
    out.metric("registered_fraction", 1.0, direction="higher_better")
    out.metric("registered_images", n, direction="higher_better")
    out.metric("mean_reprojection_error", 0.5, direction="lower_better")
    out.metric("median_reprojection_error", 0.4, direction="lower_better")
    out.metric("escaped_points", escaped, direction="lower_better", healthy=(None, 0))
    out.note(f"Posed {n} images at window {p.local_ba_window}; {escaped} escaped.")
