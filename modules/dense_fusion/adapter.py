"""DenseFusion -- dense_model/v1 (with a kept workspace) -> dense_model/v1.

The cheap half of MVS, on its own. PatchMatch searches every pixel for a depth and
normal and is measured in minutes per view; fusion decides which of those pixels
become points and is measured in seconds. They ship as one module, so revising a
fusion setting means re-buying the stereo pass -- which is why, across a whole batch,
every agent took the fusion defaults.

This module consumes the workspace `DenseMVS` kept (`keep_workspace: true`) and
re-fuses it. Same COLMAP call, same options object, so the result is the fusion the
producing module would have applied with these settings, not an imitation of it.

It cannot change anything PatchMatch decided: the depth maps, the normal maps and the
consistency graphs are inputs here. `filter_min_ncc` and friends live upstream.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pycolmap
from sfmkit import Ctx, InputError, module, render_points, write_ply


def fusion_options(p) -> pycolmap.StereoFusionOptions:
    opts = pycolmap.StereoFusionOptions()
    opts.min_num_pixels = p.min_num_pixels
    opts.max_reproj_error = p.max_reproj_error
    opts.max_depth_error = p.max_depth_error
    opts.max_normal_error = p.max_normal_error
    opts.check_num_images = p.check_num_images
    if p.max_image_size > 0:
        opts.max_image_size = p.max_image_size
    return opts


@module
def run(ctx: Ctx):
    source = ctx.inputs["dense"]
    p = ctx.params

    workspace = source.sidecar("workspace")
    if workspace is None:
        # The one fixed prerequisite, so the error names the call that satisfies it
        # rather than leaving the agent to work out that a replay is the route.
        raise InputError(
            f"input '{source.id}' carries no `workspace` sidecar, so there is nothing "
            f"to re-fuse. Next step: sfm_replay(run_id=<this run>, from_artifact="
            f"'{source.id}', overrides={{'keep_workspace': True}}), then run "
            f"DenseFusion on the dense output of that replay. The replay re-buys the "
            f"stereo pass once at the same settings; every fusion after it is seconds. "
            f"See DenseFusion's SKILL, 'Before you run it'."
        )

    stereo = workspace / "stereo"
    kind = p.input_type
    if kind == "auto":
        depth_dir = stereo / "depth_maps"
        geometric = any(depth_dir.glob("*.geometric.bin")) if depth_dir.exists() else False
        kind = "geometric" if geometric else "photometric"

    ctx.progress(0.1, f"re-fusing the kept workspace ({kind})")
    out = ctx.output("dense")
    # stereo_fusion insists on writing a reconstruction somewhere; the return value
    # is what is read, so the directory is scratch and goes away with the context.
    with tempfile.TemporaryDirectory(prefix="fuse-") as tmp:
        fused_dir = Path(tmp) / "fused"
        fused_dir.mkdir(parents=True, exist_ok=True)
        fused = pycolmap.stereo_fusion(
            output_path=str(fused_dir),
            workspace_path=str(workspace),
            input_type=kind,
            options=fusion_options(p),
        )

    xyz = np.array([pt.xyz for pt in fused.points3D.values()], dtype=np.float64)
    rgb = np.array([pt.color for pt in fused.points3D.values()], dtype=np.uint8)
    if len(xyz) == 0:
        out.metric("point_count", 0, direction="higher_better")
        out.diagnostic(
            "no_points", severity="error",
            message=f"Re-fusing produced no points at min_num_pixels={p.min_num_pixels}.",
            see_also="tuning.md#it-produced-nothing",
        )
        raise ValueError(
            f"fusion produced nothing from a workspace that PatchMatch had already "
            f"filled. min_num_pixels={p.min_num_pixels} is the first thing to lower."
        )

    ctx.progress(0.9, f"{len(xyz)} points")
    out.save("points", xyz=xyz.astype(np.float32), rgb=rgb)
    # Three orthographic views, one of them down the camera ring's own axis -- see
    # DenseMVS, which writes the same sidecar. It matters more here: re-fusing exists
    # to trade completeness against stray points, and that trade is exactly what a
    # scalar hides and a picture shows.
    # Reachable as sfm_artifact_image(<id>, 'browse/cloud_views.png').
    if p.write_cloud_views:
        centres = np.array([im.projection_center() for im in fused.images.values()])
        render_points(
            out.sidecar_dir("browse") / "cloud_views.png", xyz, rgb,
            centres=centres if len(centres) >= 3 else None)

    # Same sidecar name and writer as DenseMVS and DenseVGGT, so whatever opened the
    # original cloud opens this one.
    ply_bytes = 0
    if p.write_ply:
        ply = write_ply(
            out.sidecar_dir("ply") / "cloud.ply", xyz, rgb,
            comments=[
                f"produced by DenseFusion {ctx.module_version}",
                f"re-fused {kind} depth maps at min_num_pixels {p.min_num_pixels}",
                "frame: the sparse model's world frame, in its scale",
            ],
        )
        ply_bytes = ply.stat().st_size

    views = len({im.name for im in fused.images.values()}) if getattr(fused, "images", None) else 0
    out.metric("point_count", len(xyz), direction="higher_better", healthy=(10000, None))
    out.metric("views_contributing", views or None, direction="higher_better", healthy=(2, None))
    # Fusion has no confidence channel of its own, exactly as DenseMVS has none:
    # a null value here, with nullability declared in the manifest.
    out.metric("mean_depth_confidence", None, direction="higher_better")
    out.metric("fusion_min_num_pixels", p.min_num_pixels, direction="neutral")
    out.metric("ply_megabytes", round(ply_bytes / 1e6, 1), direction="neutral")
    # The number the tuning rule reads: how much this setting grew the cloud over
    # the fusion the stereo pass was delivered with.
    delivered = source.metric("point_count")
    out.metric("point_ratio_to_source",
               round(len(xyz) / delivered, 3) if delivered else None, direction="neutral")
    return out
