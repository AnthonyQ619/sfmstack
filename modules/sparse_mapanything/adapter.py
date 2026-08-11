"""SparseMapAnything -- scene/v1 + tracks/v1 + poses/v1 -> sparse_model/v1.

Structure from MapAnything's learned depth, placed with the SUPPLIED poses.

Same construction as SparseVGGT, and for the same reason: a model's point maps and
camera poses are in the model's own world frame at its own scale, so reading them
directly is correct only when the poses also came from that model. Depth is
per-view and frame-agnostic; unprojecting it with the supplied K and pose puts the
point in the supplied frame whatever produced it.

What MapAnything adds is that it will *accept* the poses and intrinsics as input.
That was worth measuring rather than assuming, and the measurement decided the
design. On 8 DTU views with poses from PoseEssentialToPnP:

    images + intrinsics             scale 1.9485  spread 0.0071  conf  6.20
    + poses, is_metric_scale=False  scale 1.9495  spread 0.0059  conf 10.09
    + poses, is_metric_scale=True   scale 1.3205  spread 0.0082  conf  7.69

Three things follow.

**Conditioning improves the depth.** Confidence up 63%, scale spread down 17%.
That is the capability, and it is why `condition_on_poses` defaults to true.

**Conditioning does not put the output in the supplied frame.** The scale is
unmoved -- 1.9495 against 1.9485. The model returns its own frame and its own
scale whatever it is told, so the unprojection and the scale estimate stay exactly
as they are in SparseVGGT.

**`is_metric_scale` must be false.** MapAnything is a metric reconstructor;
`true` asserts the supplied poses are in metres, which is false for any SfM
reconstruction, and the model then rescales its depth to honour the claim. It is
hardcoded rather than exposed, because there is no pose artifact in this system for
which true would be correct.

Preprocessing is upstream's `preprocess_inputs`, which picks one aspect-preserving
target from a fixed table (4:3 -> 518x392) and centre-crops to it. The pixel map
from scene coordinates into that frame is recovered from the intrinsics it returns
rather than reimplemented -- a crop-and-resize is affine, so K in and K out
determine it exactly, and the module cannot drift out of step with upstream's
table.
"""

from __future__ import annotations

import os

import numpy as np
import torch
from mapanything.models import MapAnything
from mapanything.utils.image import preprocess_inputs
from PIL import Image
from sfmkit import Ctx, module

MODEL_ID = os.environ.get("MAPANYTHING_MODEL_ID", "facebook/map-anything")

_MODEL: MapAnything | None = None


def device() -> torch.device:
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def get_model() -> MapAnything:
    global _MODEL
    if _MODEL is None:
        # By name, not by path: the image bakes the HuggingFace and torch-hub
        # caches and sets HF_HUB_OFFLINE, so this resolves locally and a cache miss
        # is an immediate error rather than a network fetch.
        _MODEL = MapAnything.from_pretrained(MODEL_ID).to(device()).eval()
    return _MODEL


def warmup() -> None:
    get_model()


def per_image_intrinsics(scene, poses_art, n_images):
    """K per image, preferring what the POSE artifact carries over the scene's."""
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
            "SparseMapAnything needs intrinsics and neither the pose artifact nor "
            "the scene carries any. PoseVGGT writes its estimate beside its poses; "
            "a classical pose estimator expects the scene to have them."
        )
    if cam_index is None:
        cam_index = np.arange(n_images) if len(K) == n_images else np.zeros(n_images, int)
    return K[np.asarray(cam_index, dtype=int)], source


def cam_to_world(P: np.ndarray) -> np.ndarray:
    """Our 3x4 world-to-camera -> the 4x4 camera-to-world MapAnything expects."""
    T = np.eye(4, dtype=np.float32)
    T[:3, :3] = P[:, :3].T
    T[:3, 3] = -P[:, :3].T @ P[:, 3]
    return T


def pixel_map(K_in: np.ndarray, K_out: np.ndarray) -> tuple[float, float, float, float]:
    """Scene pixels -> model-frame pixels, recovered from the two intrinsics.

    `preprocess_inputs` resizes uniformly and centre-crops, which is affine, so the
    focal ratio is the scale and the principal-point offset falls out of it. Doing
    it this way rather than reimplementing the resolution table means the module
    stays correct if upstream changes the table.
    """
    sx = K_out[0, 0] / K_in[0, 0]
    sy = K_out[1, 1] / K_in[1, 1]
    return sx, K_out[0, 2] - sx * K_in[0, 2], sy, K_out[1, 2] - sy * K_in[1, 2]


def unproject(depth: float, xy: np.ndarray, K: np.ndarray, pose: np.ndarray) -> np.ndarray:
    """One pixel + its depth -> a world point, in the SUPPLIED pose's frame."""
    ray = np.array([(xy[0] - K[0, 2]) / K[0, 0], (xy[1] - K[1, 2]) / K[1, 1], 1.0])
    return pose[:, :3].T @ (ray * depth - pose[:, 3])


def infer_group(model, scene, frames, K_all, pose_of, p):
    """One forward pass. Returns per-frame depth, confidence, mask and pixel map."""
    paths = scene.load("images", "paths")

    views = []
    for f in frames:
        view = {
            "img": np.asarray(
                Image.open(scene.resolve(str(paths[f]))).convert("RGB")
            )
        }
        if p.condition_on_intrinsics:
            view["intrinsics"] = K_all[f].astype(np.float32)
        if p.condition_on_poses:
            view["camera_poses"] = cam_to_world(pose_of[f])
            # Never true. See the module docstring: our poses are never metric.
            view["is_metric_scale"] = False
        views.append(view)

    processed = preprocess_inputs(views, norm_type=model.encoder.data_norm_type)

    # Captured BEFORE infer(), which moves the view tensors onto the device in
    # place and would leave these as cuda tensors.
    maps = {}
    for k, f in enumerate(frames):
        if "intrinsics" in processed[k]:
            K_out = processed[k]["intrinsics"][0].cpu().numpy().astype(np.float64)
            maps[f] = pixel_map(K_all[f], K_out)
        else:
            maps[f] = None

    with torch.no_grad():
        predictions = model.infer(
            processed,
            memory_efficient_inference=p.memory_efficient_inference,
            amp_dtype=p.amp_dtype,
        )

    out = {}
    for k, f in enumerate(frames):
        pred = predictions[k]
        depth = pred["depth_z"][0, ..., 0].float().cpu().numpy()
        confidence = pred["conf"][0].float().cpu().numpy()
        mask = pred["mask"][0, ..., 0].cpu().numpy().astype(bool)
        if maps[f] is None:
            # No intrinsics were supplied, so there is no K pair to derive the
            # map from. The model's own recovered intrinsics describe the same
            # frame and serve the purpose.
            recovered = pred["intrinsics"][0].float().cpu().numpy().astype(np.float64)
            maps[f] = pixel_map(K_all[f], recovered)
        out[f] = (depth, confidence, mask, maps[f])

    del predictions, processed
    if device().type == "cuda":
        torch.cuda.empty_cache()
    return out


@module
def run(ctx: Ctx):
    scene = ctx.inputs["scene"]
    tracks = ctx.inputs["tracks"]
    poses_art = ctx.inputs["poses"]
    p = ctx.params

    names = scene.load("images", "names")
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

    # ------------------------------------------------------------------ inference
    model = get_model()

    # Only posed views. An unposed one cannot place a point and only costs
    # attention -- but it is also not free to drop, since the model reasons across
    # the set, so this is the same trade SparseVGGT makes.
    posed = sorted(pose_of)
    chunk = p.max_images_per_pass or len(posed)
    groups = [posed[i : i + chunk] for i in range(0, len(posed), chunk)]

    depth_of, conf_of, mask_of, map_of = {}, {}, {}, {}
    for step, frames in enumerate(groups):
        ctx.progress(
            0.05 + 0.5 * step / len(groups),
            f"pass {step + 1}/{len(groups)}, {len(frames)} images"
            + (" conditioned on poses" if p.condition_on_poses else ""),
        )
        for f, (depth, confidence, mask, pmap) in infer_group(
            model, scene, frames, K_all, pose_of, p
        ).items():
            depth_of[f], conf_of[f], mask_of[f], map_of[f] = depth, confidence, mask, pmap

    # --------------------------------------------- sample depth per observation
    ctx.progress(0.6, "sampling depth at observations")

    obs_depth = np.zeros(len(obs), dtype=np.float64)
    obs_conf = np.zeros(len(obs), dtype=np.float64)
    # Two separate reasons an observation is unusable, kept apart because they have
    # different fixes: the centre crop put it outside the model's frame, or the
    # model's own mask rejected it.
    obs_inside = np.zeros(len(obs), dtype=bool)
    obs_unmasked = np.zeros(len(obs), dtype=bool)

    for f in posed:
        rows = np.flatnonzero(frame == f)
        if len(rows) == 0:
            continue
        depth, confidence, mask, (sx, tx, sy, ty) = (
            depth_of[f], conf_of[f], mask_of[f], map_of[f]
        )
        height, width = depth.shape
        # Nearest pixel, not bilinear: interpolating a depth map across a
        # discontinuity invents surface between foreground and background, exactly
        # where tracks like to sit.
        px = np.round(xy[rows, 0] * sx + tx).astype(int)
        py = np.round(xy[rows, 1] * sy + ty).astype(int)
        # A centre crop means some scene pixels fall outside the model's frame.
        # Those observations are dropped rather than clamped to the border, which
        # would sample an unrelated depth.
        inside = (px >= 0) & (px < width) & (py >= 0) & (py < height)
        rows_in = rows[inside]
        px, py = px[inside], py[inside]
        obs_depth[rows_in] = depth[py, px]
        obs_conf[rows_in] = confidence[py, px]
        obs_inside[rows_in] = True
        obs_unmasked[rows_in] = mask[py, px] if p.use_model_mask else True

    order = np.argsort(track_id, kind="stable")
    track_id, frame, xy = track_id[order], frame[order], xy[order]
    obs_depth, obs_conf = obs_depth[order], obs_conf[order]
    obs_inside, obs_unmasked = obs_inside[order], obs_unmasked[order]
    groups_of_rows = np.split(
        np.arange(len(track_id)), np.flatnonzero(np.diff(track_id)) + 1
    )

    # ----------------------------------------------------------- the scale
    ctx.progress(0.7, "estimating the depth scale")

    # MapAnything's depth is in its own unit and the poses are in theirs, and
    # conditioning does not change that -- measured, see the module docstring. One
    # scalar relates them: the ratio of the depth two-view triangulation implies to
    # the depth the model predicted, as a median over tracks.
    ratios = []
    for rows in groups_of_rows:
        seen = [r for r in rows if int(frame[r]) in pose_of and obs_depth[r] > 1e-9]
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

        triangulated = float(pose_of[fa][2] @ np.append(X, 1.0))
        predicted = float(obs_depth[ra])
        if triangulated > 1e-9 and predicted > 1e-9:
            ratios.append(triangulated / predicted)

    if len(ratios) < p.min_scale_samples:
        raise ValueError(
            f"only {len(ratios)} track(s) supported a depth-scale estimate and "
            f"min_scale_samples is {p.min_scale_samples}. This module has to relate "
            f"MapAnything's depth unit to the supplied poses' unit, and that needs "
            f"tracks seen in two posed views with real baseline. Check the tracker's "
            f"long_track_fraction and the pose estimator's registered_fraction."
        )

    ratios = np.asarray(ratios, dtype=np.float64)
    depth_scale = float(np.median(ratios))
    mad = float(np.median(np.abs(ratios - depth_scale)))
    spread = mad / abs(depth_scale) if depth_scale else float("inf")

    # ------------------------------------------------------------- build points
    ctx.progress(0.8, f"unprojecting at scale {depth_scale:.4f}")

    xyz_out, obs_out, errors, lengths, confidences = [], [], [], [], []
    rejected = {"short": 0, "outside": 0, "masked": 0, "confidence": 0,
                "cheirality": 0, "reprojection": 0}

    for rows in groups_of_rows:
        posed_rows = [r for r in rows if int(frame[r]) in pose_of]
        if len(posed_rows) < max(p.min_track_len, 1):
            rejected["short"] += 1
            continue

        inside_rows = [r for r in posed_rows if obs_inside[r] and obs_depth[r] > 1e-9]
        if not inside_rows:
            rejected["outside"] += 1
            continue

        usable = [r for r in inside_rows if obs_unmasked[r]]
        if not usable:
            rejected["masked"] += 1
            continue

        # The observation the model is most confident about, among those its own
        # mask kept.
        best = max(usable, key=lambda r: obs_conf[r])
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
        for r in posed_rows:
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
        lengths.append(len(posed_rows))
        confidences.append(float(obs_conf[best]))
        errors.extend(per_view)
        for r in posed_rows:
            obs_out.append([int(frame[r]), index, xy[r, 0], xy[r, 1]])

    if not xyz_out:
        out = ctx.output("sparse")
        out.diagnostic(
            "no_points",
            severity="error",
            message="No track survived.",
            see_also="tuning.md#nothing-survives",
        )
        dominant = max(rejected, key=rejected.get)
        advice = {
            "short": "Lower min_track_len, or check the tracker's long_track_fraction.",
            "outside": "Observations fell outside the model's centre crop, which is "
                       "unusual -- check the scene's aspect ratio against upstream's "
                       "resolution table.",
            "masked": "The model's own mask is the dominant rejection; set "
                      "use_model_mask false to see what it removed.",
            "confidence": "min_confidence is too high. MapAnything's confidence "
                          "starts near 1 and is unbounded; a threshold carried over "
                          "from SparseVGGT is roughly 5x too large.",
            "cheirality": "The depth prior and the poses disagree about which side of "
                          "the camera the scene is on. Check the poses.",
            "reprojection": "Raise max_reprojection_error, or check the poses.",
        }[dominant]
        raise ValueError(
            f"no track survived: {len(groups_of_rows)} in, rejected "
            f"{rejected['short']} as too short, {rejected['outside']} outside the "
            f"model's frame, {rejected['masked']} on the model's own mask, "
            f"{rejected['confidence']} on confidence, {rejected['cheirality']} on "
            f"cheirality, {rejected['reprojection']} on reprojection. Depth scale "
            f"was {depth_scale:.4f} with spread {spread:.3f}. {advice}"
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
    masked_share = rejected["masked"] / max(len(groups_of_rows), 1)

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
    out.metric("rejected_outside_frame", rejected["outside"], direction="lower_better")
    out.metric("rejected_masked", rejected["masked"], direction="lower_better")
    out.metric("rejected_confidence", rejected["confidence"], direction="lower_better")
    out.metric("rejected_cheirality", rejected["cheirality"], direction="lower_better")
    out.metric("rejected_reprojection", rejected["reprojection"], direction="lower_better")
    out.metric("single_view_points",
               int(sum(1 for n in lengths if n == 1)), direction="neutral")
    out.metric("conditioned", int(bool(p.condition_on_poses)), direction="neutral")

    if spread > 0.25:
        out.diagnostic(
            "depth_scale_inconsistent",
            severity="warn",
            message=(
                f"The depth/pose scale ratio varies by {spread:.0%} across tracks; "
                f"one scalar may not relate them."
            ),
            suggested_actions=[
                "Turn condition_on_poses off; if the spread improves, the poses are "
                "wrong and the model was agreeing with them rather than the scene.",
                "Or use SparseTriangulation, which needs no depth prior at all.",
                "Check the pose estimator's mean_reprojection_error first.",
            ],
            see_also="limitations.md#one-scale-for-the-whole-scene",
        )

    if masked_share > 0.2:
        out.diagnostic(
            "heavily_masked",
            severity="info",
            message=(
                f"The model's own mask rejected {masked_share:.0%} of tracks "
                f"outright."
            ),
            suggested_actions=[
                "Expected on a scene with sky, or with tracks concentrated on edges.",
                "Set use_model_mask false to keep them, at the cost of points "
                "sampled across depth discontinuities.",
            ],
            see_also="artifact.md#the-model-masks-its-own-output",
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
                "That is this module's capability on short tracks, and it is "
                "unverified structure.",
                "Raise min_track_len to 2 to keep only points a second view agrees with.",
            ],
            see_also="artifact.md#single-view-points-are-real-structure-and-unverified",
        )

    out.note(
        f"MapAnything depth unprojected with the SUPPLIED poses (intrinsics from "
        f"{k_source}), model "
        + ("conditioned on those poses and intrinsics"
           if p.condition_on_poses else "given images"
           + (" and intrinsics" if p.condition_on_intrinsics else " only"))
        + f", is_metric_scale false throughout. {len(xyz)} points from "
        f"{n_tracks_in} tracks ({yield_rate:.0%}), mean track length "
        f"{mean_length:.2f}, mean reprojection error {mean_error:.3f}px. Depth "
        f"scale {depth_scale:.4f} from {len(ratios)} tracks, spread {spread:.3f}. "
        f"Rejected {rejected['short']} short, {rejected['outside']} outside the "
        f"model's frame, {rejected['masked']} on its own mask, "
        f"{rejected['confidence']} on confidence, "
        f"{rejected['cheirality']} on cheirality, {rejected['reprojection']} on "
        f"reprojection. The cloud is in the SUPPLIED poses' frame and scale -- "
        f"conditioning does not change that, which is why the scale is measured "
        f"rather than assumed to be 1."
    )
