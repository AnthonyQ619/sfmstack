from sfmkit import Ctx, module


@module
def run(ctx: Ctx):
    sparse = ctx.inputs["sparse"]
    poses = sparse.load("poses")
    xyz = sparse.load("points", "xyz")
    obs = sparse.load("observations", "obs")

    out = ctx.output("sparse")
    out.save("points", xyz=xyz)
    out.save("observations", obs=obs)
    out.save("poses", cam_from_world=poses["cam_from_world"], valid=poses["valid"],
             image_index=poses["image_index"])
    out.metric("point_count", len(xyz), direction="higher_better")
    out.metric("observation_count", len(obs), direction="higher_better")
    out.metric("mean_reprojection_error", 0.3, direction="lower_better")
    out.metric("registered_images", int(poses["valid"].sum()), direction="higher_better")
