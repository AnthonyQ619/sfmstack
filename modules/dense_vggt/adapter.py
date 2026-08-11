"""DenseVGGT -- scene/v1 + poses/v1 (+ optional tracks/v1) -> dense_model/v1.

Every pixel's depth, unprojected with the SUPPLIED poses, filtered by VGGT's own
confidence and by multi-view agreement.

Same frame-agnostic design as SparseVGGT: depth is per-view, so unprojecting it
with the supplied camera puts the point in the supplied world frame whatever
produced that pose. The one scale relating VGGT's depth unit to the poses' unit is
the problem this module cannot solve by itself -- it has no correspondences. So
`tracks` is an OPTIONAL input used for exactly that, and without it the scale is a
parameter whose default is only correct when the poses came from VGGT too.

Getting that wrong does not fail. It produces a cloud correctly shaped and wrongly
sized, sitting in front of cameras that are the wrong distance away, so
`depth_scale_source` is reported and the module says which case it is in.
"""

from __future__ import annotations

import os

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image
from sfmkit import Ctx, module, write_ply
from vggt.models.vggt import VGGT

VGGT_SIZE = 518
CHECKPOINT = os.environ.get("VGGT_CHECKPOINT", "/opt/weights/vggt-1b.pt")
DTYPES = {"bfloat16": torch.bfloat16, "float16": torch.float16, "float32": torch.float32}

_MODEL: VGGT | None = None


def device() -> torch.device:
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def get_model() -> VGGT:
    global _MODEL
    if _MODEL is None:
        model = VGGT()
        model.load_state_dict(torch.load(CHECKPOINT, map_location="cpu"))
        _MODEL = model.eval().to(device())
    return _MODEL


def warmup() -> None:
    get_model()


def letterbox(width: int, height: int) -> tuple[float, int, int, int, int]:
    scale = VGGT_SIZE / max(width, height)
    new_w = max(1, int(round(width * scale)))
    new_h = max(1, int(round(height * scale)))
    return scale, new_w, new_h, (VGGT_SIZE - new_w) // 2, (VGGT_SIZE - new_h) // 2


def load_batch(scene, frames, dev) -> torch.Tensor:
    paths = scene.load("images", "paths")
    batch = []
    for f in frames:
        image = Image.open(scene.resolve(str(paths[f]))).convert("RGB")
        array = np.asarray(image, dtype=np.float32) / 255.0
        tensor = torch.from_numpy(array).permute(2, 0, 1)[None]
        _, new_w, new_h, pad_x, pad_y = letterbox(image.width, image.height)
        resized = F.interpolate(
            tensor, size=(new_h, new_w), mode="bilinear", align_corners=False
        )[0]
        canvas = torch.ones(3, VGGT_SIZE, VGGT_SIZE, dtype=resized.dtype)
        canvas[:, pad_y : pad_y + new_h, pad_x : pad_x + new_w] = resized
        batch.append(canvas)
    return torch.stack(batch).to(dev)


def intrinsics_for(scene, poses_art, n_images):
    if poses_art.has("intrinsics"):
        data = poses_art.load("intrinsics")
        K = np.asarray(data["K"], dtype=np.float64)
        cam_index = data.get("camera_index")
        source = "the pose artifact"
    elif scene.has("calibration"):
        data = scene.load("calibration")
        K = np.asarray(data["intrinsics"], dtype=np.float64)
        cam_index = data.get("camera_index")
        source = "the scene's calibration"
    else:
        raise ValueError(
            "DenseVGGT needs intrinsics and neither the pose artifact nor the "
            "scene carries any."
        )
    if cam_index is None:
        cam_index = np.arange(n_images) if len(K) == n_images else np.zeros(n_images, int)
    return K[np.asarray(cam_index, dtype=int)], source


def scale_from_tracks(tracks, sizes, K_all, pose_of, depth_maps, min_samples):
    """The same estimator SparseVGGT uses, on whatever tracks are supplied.

    Returns (scale, spread, n_samples) or None when there is not enough evidence.
    """
    obs = np.asarray(tracks.load("observations", "obs"), dtype=np.float64)
    track_id = obs[:, 0].astype(np.int64)
    frame = obs[:, 1].astype(np.int64)
    xy = obs[:, 2:4]

    order = np.argsort(track_id, kind="stable")
    track_id, frame, xy = track_id[order], frame[order], xy[order]
    bounds = np.flatnonzero(np.diff(track_id)) + 1

    ratios = []
    for rows in np.split(np.arange(len(track_id)), bounds):
        seen = [r for r in rows if int(frame[r]) in pose_of]
        if len(seen) < 2:
            continue
        centers = {f: -pose_of[f][:, :3].T @ pose_of[f][:, 3]
                   for f in {int(frame[r]) for r in seen}}
        best, span = None, -1.0
        for a in range(len(seen) - 1):
            for b in range(a + 1, len(seen)):
                fa, fb = int(frame[seen[a]]), int(frame[seen[b]])
                d = float(np.linalg.norm(centers[fa] - centers[fb]))
                if d > span:
                    span, best = d, (seen[a], seen[b])
        if best is None or span < 1e-9:
            continue

        ra, rb = best
        fa, fb = int(frame[ra]), int(frame[rb])
        Pa, Pb = K_all[fa] @ pose_of[fa], K_all[fb] @ pose_of[fb]
        A = np.vstack([
            xy[ra, 0] * Pa[2] - Pa[0], xy[ra, 1] * Pa[2] - Pa[1],
            xy[rb, 0] * Pb[2] - Pb[0], xy[rb, 1] * Pb[2] - Pb[1],
        ])
        _, _, vh = np.linalg.svd(A)
        X = vh[-1]
        if abs(X[3]) < 1e-12:
            continue
        X = X[:3] / X[3]

        s, _, _, pad_x, pad_y = letterbox(int(sizes[fa, 0]), int(sizes[fa, 1]))
        px = int(np.clip(round(xy[ra, 0] * s + pad_x), 0, VGGT_SIZE - 1))
        py = int(np.clip(round(xy[ra, 1] * s + pad_y), 0, VGGT_SIZE - 1))
        predicted = float(depth_maps[fa][py, px])
        triangulated = float(pose_of[fa][2] @ np.append(X, 1.0))
        if predicted > 1e-9 and triangulated > 1e-9:
            ratios.append(triangulated / predicted)

    if len(ratios) < min_samples:
        return None
    ratios = np.asarray(ratios)
    scale = float(np.median(ratios))
    mad = float(np.median(np.abs(ratios - scale)))
    return scale, (mad / abs(scale) if scale else float("inf")), len(ratios)


@module
def run(ctx: Ctx):
    scene = ctx.inputs["scene"]
    poses_art = ctx.inputs["poses"]
    tracks = ctx.inputs.get("tracks")
    p = ctx.params

    names = scene.load("images", "names")
    sizes = scene.load("images", "size_current")
    paths = scene.load("images", "paths")
    n_images = len(names)

    pose_data = poses_art.load("poses")
    cam_from_world = np.asarray(pose_data["cam_from_world"], dtype=np.float64)
    valid = np.asarray(pose_data["valid"], dtype=bool)
    image_index = np.asarray(pose_data["image_index"], dtype=int)
    pose_of = {
        int(image_index[k]): cam_from_world[k]
        for k in range(len(image_index)) if valid[k]
    }
    if not pose_of:
        raise ValueError("no image carries a valid pose; there is nothing to unproject.")

    K_all, k_source = intrinsics_for(scene, poses_art, n_images)

    model = get_model()
    dev = device()
    dtype = DTYPES[p.dtype]

    chunk = p.max_images_per_pass or n_images
    frames_all = sorted(pose_of)
    groups = [frames_all[i : i + chunk] for i in range(0, len(frames_all), chunk)]

    depth_maps = np.zeros((n_images, VGGT_SIZE, VGGT_SIZE), dtype=np.float32)
    conf_maps = np.zeros((n_images, VGGT_SIZE, VGGT_SIZE), dtype=np.float32)

    for step, frames in enumerate(groups):
        ctx.progress(
            0.05 + 0.45 * step / len(groups),
            f"depth pass {step + 1}/{len(groups)}, {len(frames)} images",
        )
        images = load_batch(scene, frames, dev)
        with torch.no_grad():
            with torch.amp.autocast(dev.type, dtype=dtype):
                tokens, patch_start = model.aggregator(images[None])
            depth, confidence = model.depth_head(
                tokens, images=images[None], patch_start_idx=patch_start
            )
        depth = depth[0, ..., 0].float().cpu().numpy()
        confidence = confidence[0].float().cpu().numpy()
        for k, f in enumerate(frames):
            depth_maps[f] = depth[k]
            conf_maps[f] = confidence[k]
        del images, tokens
        if dev.type == "cuda":
            torch.cuda.empty_cache()

    # ------------------------------------------------------------------ scale
    ctx.progress(0.55, "resolving the depth scale")

    scale, spread, samples, source = p.depth_scale, None, 0, "parameter"
    if tracks is not None:
        estimated = scale_from_tracks(
            tracks, sizes, K_all, pose_of, depth_maps, p.min_scale_samples
        )
        if estimated is not None:
            scale, spread, samples = estimated
            source = "tracks"

    # ------------------------------------------------------------- unprojection
    ctx.progress(0.6, f"unprojecting at scale {scale:.4f}")

    stride = max(1, p.stride)
    xyz_chunks, rgb_chunks, conf_chunks, contributing = [], [], [], 0

    for step, f in enumerate(frames_all):
        ctx.progress(
            0.6 + 0.3 * step / len(frames_all),
            f"unprojecting {step + 1}/{len(frames_all)}",
        )
        s, new_w, new_h, pad_x, pad_y = letterbox(int(sizes[f, 0]), int(sizes[f, 1]))

        # Only the letterboxed region holds image; the pad is white canvas the
        # model happily predicted depth for, and unprojecting it would add a flat
        # sheet at the edge of every view.
        ys = np.arange(pad_y, pad_y + new_h, stride)
        xs = np.arange(pad_x, pad_x + new_w, stride)
        gy, gx = np.meshgrid(ys, xs, indexing="ij")
        gy, gx = gy.ravel(), gx.ravel()

        depth = depth_maps[f][gy, gx].astype(np.float64) * scale
        confidence = conf_maps[f][gy, gx].astype(np.float64)

        keep = (depth > 1e-9) & (confidence >= p.min_confidence)
        if not keep.any():
            continue
        gy, gx, depth, confidence = gy[keep], gx[keep], depth[keep], confidence[keep]

        # Back to working-resolution pixels, which is the frame K is expressed in.
        u = (gx - pad_x) / s
        v = (gy - pad_y) / s

        K = K_all[f]
        rays = np.stack([
            (u - K[0, 2]) / K[0, 0], (v - K[1, 2]) / K[1, 1], np.ones_like(u)
        ], axis=1)
        in_camera = rays * depth[:, None]
        R, t = pose_of[f][:, :3], pose_of[f][:, 3]
        world = (in_camera - t) @ R

        image = np.asarray(Image.open(scene.resolve(str(paths[f]))).convert("RGB"))
        pu = np.clip(np.round(u).astype(int), 0, image.shape[1] - 1)
        pv = np.clip(np.round(v).astype(int), 0, image.shape[0] - 1)

        xyz_chunks.append(world)
        rgb_chunks.append(image[pv, pu])
        conf_chunks.append(confidence)
        contributing += 1

    if not xyz_chunks:
        out = ctx.output("dense")
        out.diagnostic(
            "no_points",
            severity="error",
            message="No pixel survived the confidence filter.",
            see_also="tuning.md#nothing-survives",
        )
        raise ValueError(
            f"no pixel survived: min_confidence={p.min_confidence}. VGGT's "
            f"confidence is unbounded above and centred near 1 on data it handles "
            f"well -- it is not a 0-1 probability, so a threshold set as if it were "
            f"rejects everything."
        )

    xyz = np.concatenate(xyz_chunks).astype(np.float32)
    rgb = np.concatenate(rgb_chunks).astype(np.uint8)
    confidence = np.concatenate(conf_chunks).astype(np.float32)

    ctx.progress(0.95, f"{len(xyz)} points")

    out = ctx.output("dense")
    out.save("points", xyz=xyz, rgb=rgb)
    # Depth maps are only expressible in this type when every view shares a
    # resolution. They do here -- all 518-square by construction -- but they are
    # VGGT's letterboxed frame rather than the scene's, so writing them would
    # invite a consumer to index them with scene pixels. Left out deliberately.
    out.save("confidence", value=confidence)

    # A .ply sidecar beside the npz, which is what dense_model/v1 calls
    # conventional: it is what a viewer, MeshLab, CloudCompare or an external
    # evaluation script opens without knowing anything about this repository. The
    # npz stays authoritative -- a consumer that ignores the sidecar loses nothing.
    ply_bytes = 0
    if p.write_ply:
        ply = write_ply(
            out.sidecar_dir("ply") / "cloud.ply", xyz, rgb,
            comments=[
                f"produced by DenseVGGT {ctx.module_version}",
                f"depth_scale {scale:.6f} from {source}",
                "frame: the SUPPLIED poses' world frame, in their scale",
            ],
        )
        ply_bytes = ply.stat().st_size

    out.metric("point_count", len(xyz), direction="higher_better", healthy=(10000, None))
    out.metric("views_contributing", contributing,
               direction="higher_better", healthy=(2, None))
    out.metric("mean_depth_confidence", round(float(confidence.mean()), 4),
               direction="higher_better", healthy=(1.0, None))
    out.metric("depth_scale", round(float(scale), 6), direction="neutral")
    out.metric("depth_scale_spread", round(spread, 4) if spread is not None else None,
               direction="lower_better", healthy=(None, 0.25))
    out.metric("scale_samples", samples, direction="higher_better")
    out.metric("points_per_view", round(len(xyz) / max(contributing, 1), 1),
               direction="neutral")
    out.metric("ply_megabytes", round(ply_bytes / 2**20, 2), direction="neutral")

    if source == "parameter":
        out.diagnostic(
            "scale_unverified",
            severity="warn",
            message=(
                f"The depth scale is the parameter value {p.depth_scale}, not "
                f"measured -- no tracks were supplied."
            ),
            suggested_actions=[
                "Pass a tracks/v1 input; the scale is then estimated and reported.",
                "The default 1.0 is correct ONLY when the poses came from VGGT too.",
                "Check the cloud sits at a plausible distance from the cameras.",
            ],
            see_also="limitations.md#the-scale-it-cannot-measure-alone",
        )

    if spread is not None and spread > 0.25:
        out.diagnostic(
            "depth_scale_inconsistent",
            severity="warn",
            message=f"The depth/pose scale ratio varies by {spread:.0%} across tracks.",
            suggested_actions=[
                "Use PoseVGGT so depth and poses come from the same model.",
                "Check the pose estimator's mean_reprojection_error.",
            ],
            see_also="limitations.md#the-scale-it-cannot-measure-alone",
        )

    out.note(
        f"VGGT depth unprojected with the SUPPLIED poses (intrinsics from "
        f"{k_source}): {len(xyz)} points from {contributing} views at stride "
        f"{stride}, {len(xyz) / max(contributing, 1):.0f} per view. Depth scale "
        f"{scale:.4f} from {source}"
        + (f" ({samples} tracks, spread {spread:.3f})" if spread is not None else "")
        + f". Only the letterboxed image region is unprojected -- the white pad "
        f"the model also predicted depth for would add a flat sheet at every view "
        f"edge. No depth maps are written: they exist, and they are in VGGT's "
        f"518-square frame rather than the scene's."
    )
