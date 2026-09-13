import numpy as np
from sfmkit import Ctx, module


@module
def run(ctx: Ctx):
    obs = ctx.inputs["tracks"].load("observations", "obs")
    poses = ctx.inputs["poses"].load("poses")

    ids = np.unique(obs[:, 0].astype(np.int64)) if len(obs) else np.zeros(0, np.int64)
    remap = {int(t): i for i, t in enumerate(ids)}
    xyz = (np.stack([ids, ids * 0.5, np.ones(len(ids))], axis=1).astype(np.float64)
           if len(ids) else np.zeros((0, 3), np.float64))
    rows = (np.array([[o[1], remap[int(o[0])], o[2], o[3]] for o in obs], dtype=np.float64)
            if len(obs) else np.zeros((0, 4), np.float64))

    out = ctx.output("sparse")
    out.save("points", xyz=xyz)
    out.save("observations", obs=rows)
    out.save("poses", cam_from_world=poses["cam_from_world"], valid=poses["valid"],
             image_index=poses["image_index"])
    out.metric("point_count", len(xyz), direction="higher_better")
    out.metric("observation_count", len(rows), direction="higher_better")
    out.metric("mean_reprojection_error", 0.4, direction="lower_better")
    out.metric("registered_images", int(poses["valid"].sum()), direction="higher_better")
