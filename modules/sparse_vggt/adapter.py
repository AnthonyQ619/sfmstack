"""SparseVGGT -- scene/v1 + tracks/v1 + poses/v1 -> sparse_model/v1.

Structure from VGGT's learned depth, placed with the SUPPLIED poses.

The design point that separates this from the predecessor: VGGT's point maps are
in VGGT's own world frame at VGGT's own scale. Reading them directly is correct
only when the poses also came from VGGT, and silently wrong when they came from
anywhere else -- the cloud ends up in one frame and the cameras in another, and
nothing reports it.

So this module uses the DEPTH head instead. Depth is per-view and frame-agnostic:
unprojecting it with the supplied K and pose puts the point in the supplied
world frame by construction, whatever produced that pose. What survives is a
single scale ambiguity between VGGT's depth unit and the poses' unit, and that is
estimated from the tracks and reported rather than assumed away.

The result is a triangulator that is interchangeable with SparseTriangulation and
SparseTriangulationGTSAM -- same three inputs, same output -- differing in where
depth comes from: a learned prior instead of ray intersection.
"""

from __future__ import annotations

import os

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image
from sfmkit import Ctx, module
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
    """Aspect-preserving fit into VGGT_SIZE, matching upstream's `pad` mode.

    The same convention as PoseVGGT, and for the same reason: squeezing changes the
    aspect ratio, which a model predicting square pixels cannot know about. Here it
    also decides where an observation lands in the depth map, so getting it wrong
    samples depth from the wrong pixel.
    """
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


def per_image_intrinsics(scene, poses_art, n_images):
    """K per image, preferring what the POSE artifact carries over the scene's.

    A pose estimator that estimated intrinsics wrote them beside its poses, and
    those are the ones its cameras are consistent with. Mixing them with the
    scene's calibration is how a model comes out subtly wrong with nothing to say
    so -- see PoseVGGT's artifact skill.
    """
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
            "SparseVGGT needs intrinsics and neither the pose artifact nor the "
            "scene carries any. PoseVGGT writes its estimate beside its poses; a "
            "classical pose estimator expects the scene to have them."
        )
    if cam_index is None:
        cam_index = np.arange(n_images) if len(K) == n_images else np.zeros(n_images, int)
    return K[np.asarray(cam_index, dtype=int)], source


def unproject(depth: float, xy: np.ndarray, K: np.ndarray, pose: np.ndarray) -> np.ndarray:
    """One pixel + its depth -> a world point, in the SUPPLIED pose's frame."""
    ray = np.array([(xy[0] - K[0, 2]) / K[0, 0], (xy[1] - K[1, 2]) / K[1, 1], 1.0])
    in_camera = ray * depth
    R, t = pose[:, :3], pose[:, 3]
    return R.T @ (in_camera - t)


@module
def run(ctx: Ctx):
    scene = ctx.inputs["scene"]
    tracks = ctx.inputs["tracks"]
    poses_art = ctx.inputs["poses"]
    p = ctx.params

    names = scene.load("images", "names")
    sizes = scene.load("images", "size_current")
    n_images = len(names)

    pose_data = poses_art.load("poses")
    cam_from_world = np.asarray(pose_data["cam_from_world"], dtype=np.float64)
    valid = np.asarray(pose_data["valid"], dtype=bool)
    image_index = np.asarray(pose_data["image_index"], dtype=int)
    pose_of = {
        int(image_index[k]): cam_from_world[k]
        for k in range(len(image_index)) if valid[k]
    }
    if len(pose_of) < 2:
        raise ValueError(
            f"only {len(pose_of)} image(s) carry a valid pose; this module needs at "
            f"least two to estimate the depth scale. Check the pose estimator's "
            f"registered_fraction."
        )

    K_all, k_source = per_image_intrinsics(scene, poses_art, n_images)

    obs = np.asarray(tracks.load("observations", "obs"), dtype=np.float64)
    n_tracks_in = int(tracks.load("observations", "track_count"))
    track_id = obs[:, 0].astype(np.int64)
    frame = obs[:, 1].astype(np.int64)
    xy = obs[:, 2:4]

    # ------------------------------------------------------------- inference
    model = get_model()
    dev = device()
    dtype = DTYPES[p.dtype]

    chunk = p.max_images_per_pass or n_images
    groups = [list(range(i, min(i + chunk, n_images))) for i in range(0, n_images, chunk)]

    depth_maps = np.zeros((n_images, VGGT_SIZE, VGGT_SIZE), dtype=np.float32)
    conf_maps = np.zeros((n_images, VGGT_SIZE, VGGT_SIZE), dtype=np.float32)

    for step, frames in enumerate(groups):
        ctx.progress(
            0.05 + 0.5 * step / len(groups),
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

    # ------------------------------------------------- sample depth per observation
    ctx.progress(0.6, "sampling depth at observations")

    # Where each observation lands in the 518-square, under the same letterbox the
    # model was fed. Nearest pixel: bilinear on a depth map interpolates across
    # depth discontinuities, which invents surface between foreground and
    # background exactly at the edges tracks like to sit on.
    obs_depth = np.zeros(len(obs), dtype=np.float64)
    obs_conf = np.zeros(len(obs), dtype=np.float64)
    for f in range(n_images):
        rows = np.flatnonzero(frame == f)
        if len(rows) == 0:
            continue
        scale, new_w, new_h, pad_x, pad_y = letterbox(int(sizes[f, 0]), int(sizes[f, 1]))
        px = np.clip(np.round(xy[rows, 0] * scale + pad_x).astype(int), 0, VGGT_SIZE - 1)
        py = np.clip(np.round(xy[rows, 1] * scale + pad_y).astype(int), 0, VGGT_SIZE - 1)
        obs_depth[rows] = depth_maps[f][py, px]
        obs_conf[rows] = conf_maps[f][py, px]

    order = np.argsort(track_id, kind="stable")
    track_id, frame, xy = track_id[order], frame[order], xy[order]
    obs_depth, obs_conf = obs_depth[order], obs_conf[order]
    bounds = np.flatnonzero(np.diff(track_id)) + 1
    groups_of_rows = np.split(np.arange(len(track_id)), bounds)

    # ------------------------------------------------------- the scale alignment
    ctx.progress(0.7, "estimating the depth scale")

    # VGGT's depth is in VGGT's unit; the poses are in theirs. One scalar relates
    # them. It is estimated per track from the ratio of the depth two-view
    # triangulation implies (in POSE units) to the depth VGGT predicted (in ITS
    # units), then taken as a median over tracks -- robust to the tracks where the
    # depth prior is simply wrong, which a mean would not be.
    ratios = []
    for rows in groups_of_rows:
        seen = [r for r in rows if int(frame[r]) in pose_of]
        if len(seen) < 2:
            continue
        # Widest baseline available for this track: the pair that conditions the
        # triangulated depth best, which is what the ratio is measured against.
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
        Pa = K_all[fa] @ pose_of[fa]
        Pb = K_all[fb] @ pose_of[fb]
        A = np.vstack([
            xy[ra, 0] * Pa[2] - Pa[0], xy[ra, 1] * Pa[2] - Pa[1],
            xy[rb, 0] * Pb[2] - Pb[0], xy[rb, 1] * Pb[2] - Pb[1],
        ])
        _, _, vh = np.linalg.svd(A)
        X = vh[-1]
        if abs(X[3]) < 1e-12:
            continue
        X = X[:3] / X[3]

        triangulated_depth = float(pose_of[fa][2] @ np.append(X, 1.0))
        vggt_depth = float(obs_depth[ra])
        if triangulated_depth > 1e-9 and vggt_depth > 1e-9:
            ratios.append(triangulated_depth / vggt_depth)

    if len(ratios) < p.min_scale_samples:
        raise ValueError(
            f"only {len(ratios)} track(s) supported a depth-scale estimate and "
            f"min_scale_samples is {p.min_scale_samples}. This module has to relate "
            f"VGGT's depth unit to the supplied poses' unit, and that needs tracks "
            f"seen in two posed views with real baseline. Check the tracker's "
            f"long_track_fraction and the pose estimator's registered_fraction."
        )

    ratios = np.asarray(ratios, dtype=np.float64)
    depth_scale = float(np.median(ratios))
    # Spread as a robust coefficient of variation. This is the honest answer to
    # "is VGGT's depth consistent with these poses at all" -- one scalar can only
    # relate the two if the ratio is actually constant across the scene.
    mad = float(np.median(np.abs(ratios - depth_scale)))
    spread = mad / abs(depth_scale) if depth_scale else float("inf")

    # ------------------------------------------------------------- build points
    ctx.progress(0.8, f"unprojecting at scale {depth_scale:.4f}")

    xyz_out, obs_out, errors, lengths, confidences = [], [], [], [], []
    rejected = {"short": 0, "confidence": 0, "cheirality": 0, "reprojection": 0}

    for rows in groups_of_rows:
        seen = [r for r in rows if int(frame[r]) in pose_of]
        if len(seen) < max(p.min_track_len, 1):
            rejected["short"] += 1
            continue

        # The observation VGGT is most confident about, not the first one. The
        # predecessor took views[0] and passed the confidence maps in without ever
        # reading them; picking the best view is what they are for.
        best = max(seen, key=lambda r: obs_conf[r])
        if obs_conf[best] < p.min_confidence:
            rejected["confidence"] += 1
            continue

        f = int(frame[best])
        depth = float(obs_depth[best]) * depth_scale
        if depth <= 1e-9:
            rejected["cheirality"] += 1
            continue
        point = unproject(depth, xy[best], K_all[f], pose_of[f])

        per_view, ok = [], True
        for r in seen:
            fr = int(frame[r])
            in_camera = pose_of[fr][:, :3] @ point + pose_of[fr][:, 3]
            if in_camera[2] <= 1e-8:
                ok = False
                rejected["cheirality"] += 1
                break
            projected = (
                in_camera[:2] / in_camera[2] @ K_all[fr][:2, :2].T + K_all[fr][:2, 2]
            )
            per_view.append(float(np.linalg.norm(projected - xy[r])))
        if not ok:
            continue
        if max(per_view) > p.max_reprojection_error:
            rejected["reprojection"] += 1
            continue

        index = len(xyz_out)
        xyz_out.append(point)
        lengths.append(len(seen))
        confidences.append(float(obs_conf[best]))
        errors.extend(per_view)
        for r in seen:
            obs_out.append([int(frame[r]), index, xy[r, 0], xy[r, 1]])

    if not xyz_out:
        out = ctx.output("sparse")
        out.diagnostic(
            "no_points",
            severity="error",
            message="No track survived.",
            see_also="tuning.md#nothing-survives",
        )
        raise ValueError(
            f"no track survived: {len(groups_of_rows)} in, rejected "
            f"{rejected['short']} as too short, {rejected['confidence']} on "
            f"confidence, {rejected['cheirality']} on cheirality, "
            f"{rejected['reprojection']} on reprojection. Depth scale was "
            f"{depth_scale:.4f} with spread {spread:.3f} -- a spread above ~0.5 "
            f"means VGGT's depth is not consistent with these poses and no single "
            f"scale relates them."
        )

    xyz = np.array(xyz_out, dtype=np.float64)
    obs_array = np.array(obs_out, dtype=np.float64)

    ctx.progress(0.92, f"{len(xyz)} points, sampling colour")

    rgb = np.full((len(xyz), 3), 128, dtype=np.uint8)
    totals = np.zeros((len(xyz), 3), dtype=np.float64)
    counts = np.zeros(len(xyz), dtype=np.int64)
    paths = scene.load("images", "paths")
    for f in range(n_images):
        rows = np.flatnonzero(obs_array[:, 0].astype(int) == f)
        if len(rows) == 0:
            continue
        image = np.asarray(Image.open(scene.resolve(str(paths[f]))).convert("RGB"))
        ys = np.clip(obs_array[rows, 3].astype(int), 0, image.shape[0] - 1)
        xs = np.clip(obs_array[rows, 2].astype(int), 0, image.shape[1] - 1)
        idx = obs_array[rows, 1].astype(int)
        np.add.at(totals, idx, image[ys, xs].astype(np.float64))
        np.add.at(counts, idx, 1)
    seen_any = counts > 0
    rgb[seen_any] = np.clip(
        totals[seen_any] / counts[seen_any][:, None], 0, 255
    ).astype(np.uint8)

    point_error = np.zeros(len(xyz), dtype=np.float64)
    obs_counts = np.zeros(len(xyz), dtype=np.int64)
    residuals = np.array(errors, dtype=np.float64)
    np.add.at(point_error, obs_array[:, 1].astype(int), residuals)
    np.add.at(obs_counts, obs_array[:, 1].astype(int), 1)
    point_error = point_error / np.maximum(obs_counts, 1)

    out = ctx.output("sparse")
    out.save("points", xyz=xyz, rgb=rgb, error=point_error)
    out.save("observations", obs=obs_array)
    out.save(
        "poses",
        cam_from_world=cam_from_world,
        valid=valid,
        image_index=image_index.astype(np.int32),
    )
    out.save("intrinsics", K=K_all, camera_index=np.arange(n_images, dtype=np.int32))

    mean_error = float(residuals.mean())
    mean_length = float(np.mean(lengths))
    yield_rate = len(xyz) / max(n_tracks_in, 1)

    out.metric("point_count", len(xyz), direction="higher_better", healthy=(100, None))
    out.metric("observation_count", len(obs_array),
               direction="higher_better", healthy=(300, None))
    out.metric("mean_track_length", round(mean_length, 3),
               direction="higher_better", healthy=(2.5, None))
    out.metric("mean_reprojection_error", round(mean_error, 4),
               direction="lower_better", healthy=(None, 2.0))
    out.metric("registered_images", int(valid.sum()),
               direction="higher_better", healthy=(3, None))
    out.metric("depth_scale", round(depth_scale, 6), direction="neutral")
    out.metric("depth_scale_spread", round(spread, 4),
               direction="lower_better", healthy=(None, 0.25))
    out.metric("scale_samples", len(ratios),
               direction="higher_better", healthy=(50, None))
    out.metric("mean_depth_confidence", round(float(np.mean(confidences)), 3),
               direction="higher_better", healthy=(1.0, None))
    out.metric("yield", round(yield_rate, 3),
               direction="higher_better", healthy=(0.3, None))
    out.metric("rejected_confidence", rejected["confidence"], direction="lower_better")
    out.metric("rejected_cheirality", rejected["cheirality"], direction="lower_better")
    out.metric("rejected_reprojection", rejected["reprojection"], direction="lower_better")
    out.metric("single_view_points",
               int(sum(1 for n in lengths if n == 1)), direction="neutral")

    if spread > 0.25:
        out.diagnostic(
            "depth_scale_inconsistent",
            severity="warn",
            message=(
                f"The depth/pose scale ratio varies by {spread:.0%} across tracks; "
                f"one scalar may not relate them."
            ),
            suggested_actions=[
                "Use PoseVGGT so the depth and the poses come from the same model.",
                "Or use SparseTriangulation, which needs no depth prior at all.",
                "Check the pose estimator's mean_reprojection_error first.",
            ],
            see_also="limitations.md#one-scale-for-the-whole-scene",
        )

    if mean_length < 1.5:
        out.diagnostic(
            "mostly_single_view",
            severity="info",
            message=(
                f"Mean track length is {mean_length:.2f}; most points rest on one "
                f"observation and one depth prediction."
            ),
            suggested_actions=[
                "That is the point of this module on short tracks, and it is unverified structure.",
                "Raise min_track_len to 2 to keep only points a second view agrees with.",
            ],
            see_also="artifact.md#single-view-points-are-real-structure-and-unverified",
        )

    out.note(
        f"VGGT depth unprojected with the SUPPLIED poses (intrinsics from "
        f"{k_source}): {len(xyz)} points from {n_tracks_in} tracks "
        f"({yield_rate:.0%}), mean track length {mean_length:.2f}, mean "
        f"reprojection error {mean_error:.3f}px. Depth scale {depth_scale:.4f} "
        f"estimated from {len(ratios)} tracks with spread {spread:.3f}. Rejected "
        f"{rejected['short']} short, {rejected['confidence']} on confidence, "
        f"{rejected['cheirality']} on cheirality, {rejected['reprojection']} on "
        f"reprojection. The cloud is in the SUPPLIED poses' frame and scale, not "
        f"VGGT's -- which is what lets this module take poses from anywhere."
    )
