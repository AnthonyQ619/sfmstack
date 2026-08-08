import numpy as np
from sfmkit import Ctx, module


@module
def run(ctx: Ctx):
    tracks = ctx.inputs["tracks"]
    obs = tracks.load("observations", "obs")
    n_images = int(ctx.inputs["scene"].load("images", "size_current").shape[0])
    min_observe = ctx.params.min_observe

    ids, counts = (
        np.unique(obs[:, 0].astype(np.int64), return_counts=True)
        if len(obs)
        else (np.zeros(0, np.int64), np.zeros(0, np.int64))
    )
    keep = ids[counts >= min_observe]

    xyz = np.stack(
        [keep.astype(np.float64), keep.astype(np.float64) * 0.5, np.ones(len(keep))],
        axis=1,
    ) if len(keep) else np.zeros((0, 3), np.float64)

    remap = {int(t): i for i, t in enumerate(keep)}
    rows = [
        [o[1], remap[int(o[0])], o[2], o[3]]
        for o in obs
        if int(o[0]) in remap
    ]
    observations = (
        np.array(rows, dtype=np.float64) if rows else np.zeros((0, 4), np.float64)
    )

    poses = np.tile(np.hstack([np.eye(3), np.zeros((3, 1))]), (n_images, 1, 1))

    out = ctx.output("sparse")
    out.save("points", xyz=xyz)
    out.save("observations", obs=observations)
    out.save(
        "poses",
        cam_from_world=poses,
        valid=np.ones(n_images, dtype=bool),
        image_index=np.arange(n_images, dtype=np.int32),
    )

    # A COLMAP-backed module would write a real model here; the point under test
    # is that the sidecar survives sealing and is discoverable.
    sidecar = out.sidecar_dir("colmap")
    (sidecar / "points3D.bin").write_bytes(b"fixture")

    out.metric("num_points3d", len(xyz), direction="higher_better", healthy=(10, None))
    out.metric(
        "mean_reprojection_error", 0.42, direction="lower_better", healthy=(None, 1.0)
    )

    if len(xyz) < 10:
        out.diagnostic(
            "too_few_points",
            severity="error",
            message=f"Only {len(xyz)} points triangulated.",
            see_also="limitations.md#sparse-coverage",
        )

    out.note(f"Triangulated {len(xyz)} points from {len(ids)} tracks.")
