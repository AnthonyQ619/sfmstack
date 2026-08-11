import numpy as np
from sfmkit import Ctx, module, write_ply


@module
def run(ctx: Ctx):
    sparse = ctx.inputs["sparse"]
    xyz = np.asarray(sparse.load("points", "xyz"), dtype=np.float64)
    n = int(ctx.params.per_point)

    # A deterministic halo around each sparse point. Deterministic because an
    # artifact id is derived from the recipe, so a fixture that varied run to run
    # would break replay rather than the thing under test.
    offsets = np.stack(np.meshgrid(*[np.linspace(-0.05, 0.05, n)] * 1), -1)
    dense = np.concatenate(
        [xyz + np.array([d, d * 0.5, -d]) for d in offsets.ravel()]
    ) if len(xyz) else np.zeros((0, 3))
    rgb = (np.abs(dense * 40) % 255).astype(np.uint8)

    out = ctx.output("dense")
    out.save("points", xyz=dense.astype(np.float32), rgb=rgb)
    if ctx.params.write_ply and len(dense):
        write_ply(out.sidecar_dir("ply") / "cloud.ply", dense, rgb,
                  comments=["produced by FakeDensifier"])

    poses = sparse.load("poses")
    out.metric("point_count", int(len(dense)), direction="higher_better")
    out.metric("views_contributing", int(np.asarray(poses["valid"]).sum()),
               direction="higher_better")
    out.metric("mean_depth_confidence", None, direction="higher_better")
    out.note(f"{len(dense)} points from {len(xyz)} sparse ones.")
