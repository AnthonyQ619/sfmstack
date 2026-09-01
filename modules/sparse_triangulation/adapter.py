"""SparseTriangulation -- scene/v1 + tracks/v1 + poses/v1 -> sparse_model/v1.

Triangulate each track from its widest-baseline observing pair, then verify it in
every view that saw it. Geometry is in normalised camera coordinates so per-image
intrinsics need no special case; reprojection error is reported in pixels.
"""

from __future__ import annotations

import cv2
import numpy as np
from sfmkit import Ctx, module

DEG = 180.0 / np.pi


def per_image_intrinsics(scene, n_images: int):
    calib = scene.load("calibration")
    K = np.asarray(calib["intrinsics"], dtype=np.float64)
    dist = np.asarray(calib["distortions"], dtype=np.float64)
    cam_index = calib.get("camera_index")
    if cam_index is None:
        cam_index = np.arange(n_images) if len(K) == n_images else np.zeros(n_images, int)
    cam_index = np.asarray(cam_index, dtype=int)
    return K[cam_index], dist[cam_index]


def normalise(points, K, dist):
    if len(points) == 0:
        return np.zeros((0, 2))
    p = np.ascontiguousarray(points, dtype=np.float64).reshape(-1, 1, 2)
    return cv2.undistortPoints(p, K, dist.reshape(1, -1)).reshape(-1, 2)


def ray_angles(centers_a, centers_b, points):
    va, vb = points - centers_a, points - centers_b
    na = np.linalg.norm(va, axis=1)
    nb = np.linalg.norm(vb, axis=1)
    good = (na > 1e-12) & (nb > 1e-12)
    cos = np.ones(len(points))
    cos[good] = np.einsum("ij,ij->i", va[good], vb[good]) / (na[good] * nb[good])
    return np.arccos(np.clip(cos, -1.0, 1.0)) * DEG



def structure_readings(xyz, obs, error, cam_from_world, valid, K_all, n_images):
    """Per-frame and tail readings that a single mean cannot carry.

    Every one of these was computed by hand, from raw arrays, by readers driving
    this stage -- which is the definition of a metric that should have been
    published. They describe the ARTIFACT, so they belong to sparse_model/v1 and
    are emitted by every producer of it.
    """
    n_points = len(xyz)
    if n_points == 0 or len(obs) == 0:
        return {"min_frame_points": 0, "two_view_fraction": 0.0,
                "p95_reprojection_error": 0.0, "p05_triangulation_angle": 0.0,
                "median_triangulation_angle": 0.0}
    # sparse_model/v1 observations are [frame_idx, point_index, x, y]. tracks/v1
    # uses [track_id, frame_idx, x, y] -- the same shape with the first two columns
    # swapped -- so passing the wrong one indexes track ids as frames. Caught once;
    # assert rather than let it produce a plausible wrong number.
    fr = obs[:, 0].astype(np.int64)
    pt = obs[:, 1].astype(np.int64)
    if fr.max(initial=-1) >= n_images or pt.max(initial=-1) >= n_points:
        raise ValueError(
            f"observations do not match this artifact: frame index up to "
            f"{fr.max(initial=-1)} for {n_images} images, point index up to "
            f"{pt.max(initial=-1)} for {n_points} points. sparse_model/v1 obs "
            f"columns are [frame_idx, point_index, x, y]."
        )
    per_point = np.bincount(pt, minlength=n_points)[:n_points]
    per_frame = np.bincount(fr, minlength=n_images)[:n_images]
    seen = per_frame[per_frame > 0]

    # widest angle subtended at each point by any pair of cameras that saw it,
    # computed from the centres so it needs nothing the artifact does not carry.
    centres = np.full((n_images, 3), np.nan)
    for f in range(min(n_images, len(cam_from_world))):
        if bool(valid[f]):
            R, t = cam_from_world[f][:, :3], cam_from_world[f][:, 3]
            centres[f] = -R.T @ t
    widest = np.zeros(n_points)
    order = np.argsort(pt, kind="stable")
    pts, frs = pt[order], fr[order]
    starts = np.flatnonzero(np.r_[True, pts[1:] != pts[:-1]])
    for a, b in zip(starts, np.r_[starts[1:], len(pts)]):
        cs = centres[frs[a:b]]
        cs = cs[~np.isnan(cs).any(axis=1)]
        if len(cs) < 2:
            continue
        v = cs - xyz[pts[a]]
        n = np.linalg.norm(v, axis=1, keepdims=True)
        v = v / np.maximum(n, 1e-12)
        cosines = np.clip(v @ v.T, -1.0, 1.0)
        widest[pts[a]] = np.degrees(np.arccos(cosines.min()))
    ang = widest[widest > 0]
    return {
        "min_frame_points": int(seen.min()) if len(seen) else 0,
        "two_view_fraction": round(float((per_point == 2).sum() / n_points), 4),
        "p95_reprojection_error": round(float(np.percentile(error, 95)), 4) if len(error) else 0.0,
        "p05_triangulation_angle": round(float(np.percentile(ang, 5)), 2) if len(ang) else 0.0,
        "median_triangulation_angle": round(float(np.median(ang)), 2) if len(ang) else 0.0,
    }


@module
def run(ctx: Ctx):
    scene = ctx.inputs["scene"]
    tracks = ctx.inputs["tracks"]
    poses_art = ctx.inputs["poses"]
    p = ctx.params

    names = scene.load("images", "names")
    n_images = len(names)

    if not scene.has("calibration") and not poses_art.has("intrinsics"):
        raise ValueError(
            "triangulation needs intrinsics and neither the scene nor the poses "
            "carry any. A pose estimator that estimates intrinsics (VGGT, "
            "MapAnything) writes them into the poses artifact; a classical one "
            "expects them on the scene."
        )

    # Poses win when they carry intrinsics: a module that estimated K did so
    # jointly with the poses, and mixing its poses with the scene's K is wrong.
    if poses_art.has("intrinsics"):
        est = poses_art.load("intrinsics")
        K_raw = np.asarray(est["K"], dtype=np.float64)
        cam_index = est.get("camera_index")
        cam_index = (
            np.arange(n_images) if cam_index is None and len(K_raw) == n_images
            else (np.zeros(n_images, int) if cam_index is None else np.asarray(cam_index, int))
        )
        K_all = K_raw[cam_index]
        dist_all = np.zeros((n_images, 5))
    else:
        K_all, dist_all = per_image_intrinsics(scene, n_images)

    pose_data = poses_art.load("poses")
    cam_from_world = np.asarray(pose_data["cam_from_world"], dtype=np.float64)
    valid = np.asarray(pose_data["valid"], dtype=bool)
    image_index = np.asarray(pose_data["image_index"], dtype=int)

    pose_of = {
        int(image_index[k]): cam_from_world[k] for k in range(len(image_index)) if valid[k]
    }
    if len(pose_of) < 2:
        raise ValueError(
            f"only {len(pose_of)} image(s) carry a valid pose; triangulation needs "
            f"at least two. Check the pose artifact's registered_fraction."
        )
    centers = {f: -P[:, :3].T @ P[:, 3] for f, P in pose_of.items()}

    obs = tracks.load("observations", "obs")
    n_tracks_in = int(tracks.load("observations", "track_count"))

    track_id = obs[:, 0].astype(np.int64)
    frame = obs[:, 1].astype(np.int64)
    xy = obs[:, 2:4].astype(np.float64)

    # Drop observations in unregistered images before anything else -- they can
    # neither be triangulated from nor verified against.
    registered = np.array([f in pose_of for f in frame])
    track_id, frame, xy = track_id[registered], frame[registered], xy[registered]

    # Normalise per frame, in one pass per image rather than per observation.
    normalised = np.zeros_like(xy)
    undistorted = np.zeros_like(xy)
    for f in pose_of:
        rows = frame == f
        if not rows.any():
            continue
        nrm = normalise(xy[rows], K_all[f], dist_all[f])
        normalised[rows] = nrm
        undistorted[rows] = nrm @ K_all[f][:2, :2].T + K_all[f][:2, 2]

    order = np.argsort(track_id, kind="stable")
    track_id, frame = track_id[order], frame[order]
    normalised, undistorted = normalised[order], undistorted[order]

    starts = np.flatnonzero(np.r_[True, track_id[1:] != track_id[:-1]])
    ends = np.r_[starts[1:], len(track_id)] if len(starts) else np.array([], int)

    kept_xyz, kept_track, kept_error, kept_angle = [], [], [], []
    kept_obs_frame, kept_obs_point, kept_obs_xy = [], [], []
    rejected_cheirality = 0
    n_groups = len(starts)

    for g in range(n_groups):
        if g % 2000 == 0:
            ctx.progress(0.8 * g / max(n_groups, 1), f"triangulating {g}/{n_groups}")

        s, e = starts[g], ends[g]
        if e - s < p.min_observations:
            continue

        frames = frame[s:e]
        nrm = normalised[s:e]
        pix = undistorted[s:e]

        # Widest baseline available, which is the pair that conditions depth best.
        cams = np.array([centers[int(f)] for f in frames])
        a, b = np.triu_indices(len(frames), k=1)
        spans = np.linalg.norm(cams[a] - cams[b], axis=1)
        if not len(spans) or spans.max() < 1e-9:
            continue
        best = int(np.argmax(spans))
        f1, f2 = int(frames[a[best]]), int(frames[b[best]])

        X = cv2.triangulatePoints(
            pose_of[f1], pose_of[f2],
            nrm[a[best]].reshape(2, 1), nrm[b[best]].reshape(2, 1),
        )
        if abs(X[3, 0]) < 1e-12:
            continue
        X = (X[:3, 0] / X[3, 0])
        if not np.isfinite(X).all():
            continue

        angle = float(ray_angles(cams[a], cams[b], np.tile(X, (len(a), 1))).max())
        if angle < p.min_triangulation_angle_deg:
            continue

        # Verify in every observing view. Max, not mean: one bad observation is
        # enough to drag a bundle adjustment, and it costs nothing to refuse it.
        errors, behind = [], False
        for k in range(len(frames)):
            f = int(frames[k])
            cam = pose_of[f][:, :3] @ X + pose_of[f][:, 3]
            if cam[2] <= 1e-8:
                behind = True
                break
            proj = (cam[:2] / cam[2]) @ K_all[f][:2, :2].T + K_all[f][:2, 2]
            errors.append(float(np.linalg.norm(proj - pix[k])))

        if behind:
            rejected_cheirality += 1
            continue
        if max(errors) > p.max_reprojection_error:
            continue

        point_index = len(kept_xyz)
        kept_xyz.append(X)
        kept_track.append(int(track_id[s]))
        kept_error.append(float(np.mean(errors)))
        kept_angle.append(angle)
        for k in range(len(frames)):
            kept_obs_frame.append(int(frames[k]))
            kept_obs_point.append(point_index)
            kept_obs_xy.append(pix[k])

    out = ctx.output("sparse")

    if not kept_xyz:
        out.diagnostic(
            "no_points",
            severity="error",
            message=f"None of {n_groups} tracks survived triangulation.",
            see_also="limitations.md#when-triangulation-produces-nothing",
        )
        raise ValueError(
            f"no track survived triangulation: {n_groups} had at least "
            f"{p.min_observations} registered observations, {rejected_cheirality} "
            f"landed behind a camera, and the rest failed the "
            f"{p.min_triangulation_angle_deg} degree angle or "
            f"{p.max_reprojection_error}px reprojection filters. A high cheirality "
            f"count points at the poses, not at these thresholds."
        )

    xyz = np.array(kept_xyz, dtype=np.float64)
    obs_table = np.column_stack([
        np.array(kept_obs_frame, dtype=np.float64),
        np.array(kept_obs_point, dtype=np.float64),
        np.array(kept_obs_xy, dtype=np.float64),
    ])

    rgb = None
    if p.colour_points:
        ctx.progress(0.85, "sampling colour")
        rgb = sample_colour(scene, n_images, kept_obs_frame, kept_obs_point, kept_obs_xy, len(xyz))

    point_arrays = {
        "xyz": xyz,
        "error": np.array(kept_error, dtype=np.float64),
        "track_id": np.array(kept_track, dtype=np.int32),
    }
    if rgb is not None:
        point_arrays["rgb"] = rgb

    out.save("points", **point_arrays)
    out.save("observations", obs=obs_table)
    out.save(
        "poses",
        cam_from_world=cam_from_world,
        valid=valid,
        image_index=image_index.astype(np.int32),
    )

    mean_err = float(np.mean(kept_error))
    mean_len = len(obs_table) / len(xyz)
    median_angle = float(np.median(kept_angle))
    yield_ = len(xyz) / max(n_tracks_in, 1)
    cheirality_rate = rejected_cheirality / max(n_groups, 1)

    out.metric("point_count", len(xyz), direction="higher_better", healthy=(100, None))
    out.metric("observation_count", len(obs_table),
               direction="higher_better", healthy=(300, None))
    _s = structure_readings(xyz, obs_table, np.asarray(kept_error), cam_from_world, valid, None, n_images)
    out.metric("min_frame_points", _s["min_frame_points"],
               direction="higher_better", healthy=(50, None))
    out.metric("two_view_fraction", _s["two_view_fraction"],
               direction="lower_better", healthy=(None, 0.6))
    out.metric("p95_reprojection_error", _s["p95_reprojection_error"],
               direction="lower_better", healthy=(None, 2.0))
    out.metric("p05_triangulation_angle", _s["p05_triangulation_angle"],
               direction="higher_better", healthy=(1.0, None))
    out.metric("mean_reprojection_error", round(mean_err, 3),
               direction="lower_better", healthy=(None, 2.0))
    out.metric("mean_track_length", round(mean_len, 2),
               direction="higher_better", healthy=(3.0, None))
    out.metric("median_triangulation_angle", round(median_angle, 2),
               direction="higher_better", healthy=(3.0, None))
    out.metric("yield", round(yield_, 3), direction="higher_better", healthy=(0.3, None))
    out.metric("registered_images", int(np.asarray(valid, dtype=bool).sum()),
               direction="higher_better", healthy=(3, None))
    out.metric("rejected_cheirality", round(cheirality_rate, 4),
               direction="lower_better", healthy=(None, 0.05))

    if cheirality_rate > 0.05:
        out.diagnostic(
            "bad_poses_suspected",
            severity="warn",
            message=(
                f"{cheirality_rate:.0%} of tracks landed behind a camera "
                f"({rejected_cheirality} of {n_groups})."
            ),
            suggested_actions=[
                "Re-check the pose estimator's metrics before tuning anything here.",
            ],
            see_also="limitations.md#cheirality-failures-are-a-pose-problem",
        )

    if mean_len < 2.5:
        out.diagnostic(
            "two_view_cloud",
            severity="warn",
            message=f"Points carry {mean_len:.2f} observations each on average.",
            suggested_actions=[
                "Widen the matcher's pairing so tracks reach further -- `window` "
                "under sequential; under exhaustive lower min_matches.",
                "Raise min_observations to 3 to measure the genuine multi-view structure.",
            ],
            see_also="tuning.md#mean_track_length-near-20",
        )

    if median_angle < 3.0:
        out.diagnostic(
            "weak_geometry",
            severity="warn",
            message=f"Median triangulation angle is {median_angle:.2f} degrees.",
            suggested_actions=["Raise min_triangulation_angle_deg."],
            see_also="limitations.md#when-triangulation-produces-nothing",
        )

    out.note(
        f"Triangulated {len(xyz)} points from {n_groups} tracks with "
        f"{p.min_observations}+ registered observations ({yield_:.0%} of "
        f"{n_tracks_in} input tracks). {len(obs_table)} observations, mean "
        f"{mean_len:.2f} per point. Mean reprojection error {mean_err:.2f}px, "
        f"median triangulation angle {median_angle:.2f} degrees. "
        f"{rejected_cheirality} tracks rejected for cheirality."
    )


def sample_colour(scene, n_images, obs_frame, obs_point, obs_xy, n_points):
    """Mean colour over each point's observations.

    Opens each image once. The scene's paths are resolved through the artifact,
    so a scene built with `resize: none` needs the dataset mounted here too.
    """
    accum = np.zeros((n_points, 3), dtype=np.float64)
    count = np.zeros(n_points, dtype=np.int64)

    frames = np.array(obs_frame)
    points = np.array(obs_point)
    coords = np.array(obs_xy)
    paths = scene.load("images", "paths")

    for f in range(n_images):
        rows = frames == f
        if not rows.any():
            continue
        image = cv2.imread(str(scene.resolve(str(paths[f]))), cv2.IMREAD_COLOR)
        if image is None:
            continue
        h, w = image.shape[:2]
        u = np.clip(coords[rows, 0].astype(int), 0, w - 1)
        v = np.clip(coords[rows, 1].astype(int), 0, h - 1)
        bgr = image[v, u].astype(np.float64)
        np.add.at(accum, points[rows], bgr[:, ::-1])  # BGR -> RGB
        np.add.at(count, points[rows], 1)

    count = np.maximum(count, 1)
    return (accum / count[:, None]).clip(0, 255).astype(np.uint8)
