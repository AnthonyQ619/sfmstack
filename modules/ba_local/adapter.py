"""BundleAdjustmentLocal -- scene/v1 + sparse_model/v1 -> sparse_model/v1.

Bundle adjustment over a window of cameras, with the rest of the model held fixed.

The translation to and from pycolmap is the same as in BundleAdjustmentGlobal; what
differs is the BundleAdjustmentConfig, which is where "local" actually lives.
"""

from __future__ import annotations

import numpy as np
import pycolmap
from sfmkit import Ctx, module

# pycolmap needs at least two fixed cameras to pin the 7-dof gauge. With fewer, the
# solve wanders along the similarity manifold instead of converging.
MIN_FIXED = 2


def intrinsics_for(scene, sparse, n_images):
    if sparse.has("intrinsics"):
        data = sparse.load("intrinsics")
        K = np.asarray(data["K"], dtype=np.float64)
        cam_index = data.get("camera_index")
    elif scene.has("calibration"):
        data = scene.load("calibration")
        K = np.asarray(data["intrinsics"], dtype=np.float64)
        cam_index = data.get("camera_index")
    else:
        raise ValueError(
            "bundle adjustment needs intrinsics and neither the sparse model nor "
            "the scene carries any."
        )
    if cam_index is None:
        cam_index = np.arange(n_images) if len(K) == n_images else np.zeros(n_images, int)
    return K[np.asarray(cam_index, dtype=int)]


def build_reconstruction(scene, sparse, n_images, min_track_length, ctx):
    """Arrays -> pycolmap.Reconstruction. One camera per registered image."""
    poses = sparse.load("poses")
    cam_from_world = np.asarray(poses["cam_from_world"], dtype=np.float64)
    valid = np.asarray(poses["valid"], dtype=bool)
    image_index = np.asarray(poses["image_index"], dtype=int)

    K_all = intrinsics_for(scene, sparse, n_images)
    points = sparse.load("points")
    xyz = np.asarray(points["xyz"], dtype=np.float64)
    rgb = points.get("rgb")
    obs = np.asarray(sparse.load("observations", "obs"), dtype=np.float64)

    sizes = scene.load("images", "size_current")
    names = scene.load("images", "names")

    rec = pycolmap.Reconstruction()

    image_id_of: dict[int, int] = {}
    next_id = 1
    for k in range(len(image_index)):
        if valid[k]:
            image_id_of[int(image_index[k])] = next_id
            next_id += 1

    obs_frame = obs[:, 0].astype(int)
    obs_point = obs[:, 1].astype(int)
    obs_xy = obs[:, 2:4]
    order = np.argsort(obs_frame, kind="stable")
    obs_frame, obs_point, obs_xy = obs_frame[order], obs_point[order], obs_xy[order]

    track_elements: dict[int, list[tuple[int, int]]] = {}

    for frame, image_id in sorted(image_id_of.items(), key=lambda kv: kv[1]):
        rows = np.flatnonzero(obs_frame == frame)
        K = K_all[frame]
        camera = pycolmap.Camera.create_from_model_id(
            camera_id=image_id,
            model=pycolmap.CameraModelId.PINHOLE,
            focal_length=float(K[0, 0]),
            width=int(sizes[frame][0]),
            height=int(sizes[frame][1]),
        )
        camera.params = [float(K[0, 0]), float(K[1, 1]), float(K[0, 2]), float(K[1, 2])]
        rec.add_camera_with_trivial_rig(camera)

        points2D = []
        for local_index, r in enumerate(rows):
            points2D.append(pycolmap.Point2D(obs_xy[r]))
            track_elements.setdefault(int(obs_point[r]), []).append((image_id, local_index))

        image = pycolmap.Image(name=str(names[frame]), camera_id=image_id, points2D=points2D)
        image.image_id = image_id
        P = cam_from_world[np.flatnonzero(image_index == frame)[0]]
        rec.add_image_with_trivial_frame(
            image, pycolmap.Rigid3d(pycolmap.Rotation3d(P[:, :3]), P[:, 3])
        )

    ctx.progress(0.3, f"{len(image_id_of)} cameras, adding points")

    kept: dict[int, int] = {}
    for point_index, elements in track_elements.items():
        if len(elements) < min_track_length:
            continue
        track = pycolmap.Track([pycolmap.TrackElement(i, j) for i, j in elements])
        colour = (
            np.asarray(rgb[point_index], dtype=np.uint8)
            if rgb is not None else np.array([128, 128, 128], dtype=np.uint8)
        )
        kept[point_index] = rec.add_point3D(xyz[point_index], track, colour)

    return rec, image_id_of, kept, cam_from_world, valid, image_index


def choose_window(rec, image_id_of, anchor: str, size: int) -> list[int]:
    """Which frames to refine.

    Contiguous in FRAME order rather than in registration order, because the window
    is meant to be a spatial neighbourhood and frame order is the only proxy for
    that available here without reading the view graph.
    """
    frames = sorted(image_id_of)
    if len(frames) <= size:
        return frames

    if anchor == "first":
        return frames[:size]
    if anchor == "largest_error":
        worst, worst_error = frames[0], -1.0
        for frame in frames:
            image = rec.image(image_id_of[frame])
            errors = [
                rec.point3D(p2d.point3D_id).error
                for p2d in image.points2D
                if p2d.has_point3D() and rec.exists_point3D(p2d.point3D_id)
            ]
            mean = float(np.mean(errors)) if errors else 0.0
            if mean > worst_error:
                worst, worst_error = frame, mean
        centre = frames.index(worst)
        start = max(0, min(centre - size // 2, len(frames) - size))
        return frames[start : start + size]
    return frames[-size:]  # "last"


# The share of escaped points at which the solve counts as diverged. Tied to the
# tail percentile every sparse_model/v1 producer publishes: once escapees reach
# into the 95th percentile, no error reading on the artifact describes the model.
DIVERGED_SHARE = 0.05


def image_extent(scene) -> float:
    """The largest working-resolution image dimension, in pixels.

    A point whose reprojection error exceeds this cannot be a measurement: it no
    longer projects anywhere near the image it was observed in. That makes the
    bound scale-free -- it moves with the working resolution -- where a fixed
    pixel constant would be loose on a small image and tight on a large one.
    """
    sizes = np.asarray(scene.load("images", "size_current"), dtype=np.float64)
    return float(sizes.max()) if sizes.size else float("inf")


def error_readings(before, after, extent: float) -> dict:
    """Per-point (or per-observation) errors -> what the artifact can publish.

    The same function as BundleAdjustmentGlobal's, and for the same measured
    reason. The divergence guard used to trip on the MEAN, and a mean is owned by
    its largest value: one point in tens of thousands, left behind along
    near-parallel rays, put the mean at 1e149 while the median and the p95 did not
    move, and the guard called the most accurate of three models unusable.

    So each value is judged on its own. One larger than the image extent has
    ESCAPED: counted, and excluded from every error statistic. The solve is
    DIVERGED only when escapees reach the published tail (DIVERGED_SHARE), or the
    tail of what stayed grew a thousandfold. A real divergence moves the whole
    distribution and trips both; a single escapee trips neither.
    """
    before = np.asarray(before, dtype=np.float64)
    after = np.asarray(after, dtype=np.float64)
    escaped = ~np.isfinite(after) | (after > extent)
    kept_after = after[~escaped]
    kept_before = before[np.isfinite(before) & (before <= extent)]
    n_escaped = int(escaped.sum())
    share = n_escaped / len(after) if len(after) else 0.0

    def mean(a):
        return float(a.mean()) if a.size else float("nan")

    def p95(a):
        return float(np.percentile(a, 95)) if a.size else float("nan")

    p95_before, p95_after = p95(kept_before), p95(kept_after)
    blew_up = (
        kept_after.size == 0
        or share >= DIVERGED_SHARE
        or (np.isfinite(p95_before) and p95_after > 1e3 * max(p95_before, 1e-6))
    )
    return {
        "escaped": n_escaped,
        "escaped_share": share,
        "escaped_mask": escaped,
        "mean_before": mean(kept_before),
        "mean_after": mean(kept_after),
        "p95_before": p95_before,
        "p95_after": p95_after,
        "diverged": bool(blew_up),
    }


def window_errors(rec, image_ids: set[int]) -> np.ndarray:
    """Per-observation reprojection error over the given cameras only.

    The global figure dilutes a local solve with cameras that were held fixed, so
    it understates what this module actually did. Returned as the array rather
    than its mean, so the escape test can judge each observation on its own.
    """
    errors = []
    for image_id in image_ids:
        image = rec.image(image_id)
        for p2d in image.points2D:
            if not p2d.has_point3D() or not rec.exists_point3D(p2d.point3D_id):
                continue
            point = rec.point3D(p2d.point3D_id)
            projected = image.project_point(point.xyz)
            if projected is None:
                continue
            errors.append(float(np.linalg.norm(np.asarray(projected) - np.asarray(p2d.xy))))
    return np.asarray(errors, dtype=np.float64)


def read_summary(summary) -> tuple[int, bool]:
    if summary is None:
        return 0, False
    ceres = getattr(summary, "ceres_summary", None) or summary
    iterations = 0
    for attr in ("num_successful_steps", "iterations", "num_iterations"):
        value = getattr(ceres, attr, None)
        if isinstance(value, int):
            iterations = value
            break
        if isinstance(value, (list, tuple)):
            iterations = len(value)
            break
    termination = getattr(summary, "termination_type", None) or getattr(
        ceres, "termination_type", None
    )
    # Exact name comparison, not a substring test: "CONVERGENCE" is a substring of
    # "NO_CONVERGENCE", so `in` reports success on exactly the solves that ran out
    # of iterations -- the case this metric exists to catch.
    converged = termination is not None and _termination_name(termination) == "CONVERGENCE"
    if termination is None and getattr(summary, "is_solution_usable", None):
        converged = bool(summary.is_solution_usable())
    return iterations, converged


def _termination_name(termination) -> str:
    """'TerminationType.NO_CONVERGENCE' / an enum / a bare string -> 'NO_CONVERGENCE'."""
    name = getattr(termination, "name", None)
    if isinstance(name, str):
        return name.upper()
    return str(termination).rsplit(".", 1)[-1].upper()


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
    sparse = ctx.inputs["sparse"]
    p = ctx.params

    n_images = len(scene.load("images", "names"))
    points_in = len(np.asarray(sparse.load("points", "xyz")))

    ctx.progress(0.1, "building the reconstruction")
    rec, image_id_of, kept, cam_from_world, valid, image_index = build_reconstruction(
        scene, sparse, n_images, p.min_track_length, ctx
    )

    if rec.num_points3D() == 0:
        raise ValueError(
            f"no point survived min_track_length={p.min_track_length}. This module "
            f"defaults to 3 rather than 2, because a two-view point inside a window "
            f"contributes nothing a local solve can use -- lower it to 2 if the "
            f"cloud is genuinely two-view, or fix that upstream."
        )

    rec.update_point_3d_errors()  # COLMAP leaves per-point error unset until asked
    # Per point, not the scalar mean: the escape test judges each point on its
    # own, and the published means are taken over the points that stayed.
    extent = image_extent(scene)
    before_errors = np.array(
        [rec.point3D(pid).error for pid in kept.values()], dtype=np.float64
    )
    error_before = error_readings(before_errors, before_errors, extent)["mean_before"]

    window = choose_window(rec, image_id_of, p.anchor, p.window_size)
    window_ids = {image_id_of[f] for f in window}
    fixed_ids = [i for i in image_id_of.values() if i not in window_ids]
    win_before_errors = window_errors(rec, window_ids)
    win_before = error_readings(win_before_errors, win_before_errors, extent)["mean_before"]

    if len(fixed_ids) < MIN_FIXED:
        # Not an error: the model is simply smaller than the window. Refine
        # everything but the two anchors, and say so.
        movable = sorted(window_ids)[: max(0, len(window_ids) - MIN_FIXED)]
        fixed_ids = [i for i in image_id_of.values() if i not in set(movable)]
        window_ids = set(movable)

    config = pycolmap.BundleAdjustmentConfig()
    for image_id in image_id_of.values():
        config.add_image(image_id)
    for image_id in fixed_ids:
        config.set_constant_rig_from_world_pose(image_id)

    options = pycolmap.BundleAdjustmentOptions()
    options.refine_focal_length = False
    options.refine_principal_point = False
    options.refine_extra_params = False
    options.refine_points3D = True
    options.refine_rig_from_world = True
    options.min_track_length = p.min_track_length
    options.ceres.solver_options.max_num_iterations = p.max_iterations
    if p.robust_loss:
        options.ceres.loss_function_type = pycolmap.LossFunctionType.CAUCHY
        options.ceres.loss_function_scale = p.loss_scale
    else:
        options.ceres.loss_function_type = pycolmap.LossFunctionType.TRIVIAL

    ctx.progress(
        0.5,
        f"solving: {len(window_ids)} cameras free, {len(fixed_ids)} fixed, "
        f"{rec.num_points3D()} points",
    )
    summary = pycolmap.create_default_bundle_adjuster(options, config, rec).solve()

    rec.update_point_3d_errors()
    after_errors = np.array(
        [rec.point3D(pid).error for pid in kept.values()], dtype=np.float64
    )
    readings = error_readings(before_errors, after_errors, extent)
    win_readings = error_readings(win_before_errors, window_errors(rec, window_ids), extent)
    error_after = readings["mean_after"]
    win_after = win_readings["mean_after"]
    iterations, converged = read_summary(summary)

    ctx.progress(0.8, f"window {win_before:.3f} -> {win_after:.3f} px")

    # ------------------------------------------------------------- write back
    out = ctx.output("sparse")

    refined = cam_from_world.copy()
    for frame, image_id in image_id_of.items():
        pose = rec.image(image_id).cam_from_world()
        row = np.flatnonzero(image_index == frame)[0]
        refined[row] = np.hstack([pose.rotation.matrix(), pose.translation.reshape(3, 1)])

    point_ids = sorted(kept.values())
    inverse = {pid: idx for idx, pid in enumerate(point_ids)}
    original = {v: k for k, v in kept.items()}
    # NOT np.asarray(...) on the get(): np.asarray(None) is a 0-d object array,
    # which is not None, so the guard below would pass and the indexing would
    # raise. track_id is OPTIONAL in sparse_model/v1 and most producers omit it.
    source_track = sparse.load("points").get("track_id")
    source_track = None if source_track is None else np.asarray(source_track)

    obs_rows = []
    id_to_frame = {v: k for k, v in image_id_of.items()}
    for pid in point_ids:
        for element in rec.point3D(pid).track.elements:
            xy = rec.image(element.image_id).point2D(element.point2D_idx).xy
            obs_rows.append(
                [id_to_frame[element.image_id], inverse[pid], float(xy[0]), float(xy[1])]
            )

    # Named rather than inlined, because the artifact metrics below have to be
    # computed over the arrays this actually SHIPS. The input `xyz` from the top of
    # run() indexes differently -- min_track_length may have dropped points -- so
    # measuring against it would silently mismatch.
    out_xyz = np.array([rec.point3D(pid).xyz for pid in point_ids], dtype=np.float64)
    out_error = np.array([rec.point3D(pid).error for pid in point_ids], dtype=np.float64)
    out.save(
        "points",
        xyz=out_xyz,
        rgb=np.array([rec.point3D(pid).color for pid in point_ids], dtype=np.uint8),
        error=out_error,
        track_id=np.array(
            [
                int(source_track[original[pid]]) if source_track is not None else -1
                for pid in point_ids
            ],
            dtype=np.int32,
        ),
    )
    out.save("observations", obs=np.array(obs_rows, dtype=np.float64))
    out.save(
        "poses",
        cam_from_world=refined,
        valid=valid,
        image_index=image_index.astype(np.int32),
    )
    rec.write_binary(str(out.sidecar_dir("colmap")))

    # An ESCAPED point is not a diverged solve: it is counted in escaped_points and
    # left out of the means. Only a solve whose escapees reach the published tail,
    # in the whole model or in the window, is suppressed.
    blew_up = readings["diverged"] or win_readings["diverged"]

    out.metric("reprojection_error_before", round(error_before, 4),
               direction="lower_better", healthy=(None, 2.0))
    out.metric("reprojection_error_after",
               None if blew_up else round(error_after, 4),
               direction="lower_better", healthy=(None, 1.0))
    out.metric("window_error_before", round(win_before, 4),
               direction="lower_better", healthy=(None, 2.0))
    out.metric("window_error_after",
               None if blew_up else round(win_after, 4),
               direction="lower_better", healthy=(None, 1.0))
    out.metric("cameras_refined", len(window_ids), direction="neutral")
    out.metric("cameras_fixed", len(fixed_ids), direction="neutral")
    out.metric("points_optimized", len(point_ids),
               direction="higher_better", healthy=(50, None))
    out.metric("converged", int(converged), direction="higher_better", healthy=(1, None))

    # The sparse_model/v1 contract: metrics describing the ARTIFACT, so a consumer
    # can compare this model against one from a triangulator or a feed-forward
    # reconstructor. The before/after pair above describes the PROCESS and is
    # comparable only against another bundle adjustment.
    _obs = np.array(obs_rows, dtype=np.float64)
    # The tail reading is taken over the points that stayed in the image. An
    # escaped point's error is not a measurement, so it cannot be ranked; it is
    # counted in escaped_points instead.
    stayed = np.isfinite(out_error) & (out_error <= extent)
    _s = structure_readings(out_xyz, _obs, out_error[stayed], refined, valid, None, n_images)
    out.metric("min_frame_points", _s["min_frame_points"],
               direction="higher_better", healthy=(50, None))
    out.metric("two_view_fraction", _s["two_view_fraction"],
               direction="lower_better", healthy=(None, 0.6))
    out.metric("p95_reprojection_error",
               None if blew_up else _s["p95_reprojection_error"],
               direction="lower_better", healthy=(None, 2.0))
    out.metric("p05_triangulation_angle", _s["p05_triangulation_angle"],
               direction="higher_better", healthy=(1.5, None))
    out.metric("point_count", len(point_ids),
               direction="higher_better", healthy=(50, None))
    out.metric("observation_count", len(obs_rows),
               direction="higher_better", healthy=(100, None))
    out.metric("mean_track_length",
               round(len(obs_rows) / len(point_ids), 3) if point_ids else 0.0,
               direction="higher_better", healthy=(2.5, None))
    out.metric("mean_reprojection_error",
               None if blew_up else round(error_after, 4),
               direction="lower_better", healthy=(None, 1.0))
    out.metric("registered_images", int(np.asarray(valid, dtype=bool).sum()),
               direction="higher_better", healthy=(3, None))
    out.metric("escaped_points", readings["escaped"],
               direction="lower_better", healthy=(None, 0))

    if len(fixed_ids) <= MIN_FIXED and len(image_id_of) > p.window_size:
        out.diagnostic(
            "window_covers_model",
            severity="info",
            message=(
                f"Only {len(fixed_ids)} of {len(image_id_of)} cameras were held "
                f"fixed; this is global BA with extra steps."
            ),
            suggested_actions=[
                "Use BundleAdjustmentGlobal, which fixes the gauge properly.",
                f"Or lower window_size below {p.window_size}.",
            ],
            see_also="tuning.md#when-to-use-global-ba-instead",
        )

    if not converged:
        out.diagnostic(
            "did_not_converge",
            severity="warn",
            message=(
                f"Ceres stopped after {iterations} iterations without "
                f"converging (cap {p.max_iterations})."
            ),
            suggested_actions=[
                f"Raise max_iterations above {p.max_iterations} if `iterations` is "
                f"AT OR NEAR the cap -- it reports cap+1 on a capped run, so it "
                f"never equals the cap.",
                "If it stalled well below the cap, the robust loss is the usual "
                "cause and more iterations will not help.",
                "A converged flag has been measured worth nothing here: capped and "
                "converged solves of one problem agreed to four decimals.",
            ],
            see_also="tuning.md#converged-is-0",
        )

    if blew_up:
        out.diagnostic(
            "bundle_adjustment_diverged",
            severity="error",
            message=(
                f"The solve diverged: {readings['escaped']} of {len(after_errors)} "
                f"points left the image, or the window's tail error grew by orders "
                f"of magnitude (p95 {win_readings['p95_before']:.3f}px -> "
                f"{win_readings['p95_after']:.3g}px). Every error metric on this "
                f"artifact is suppressed; the model it contains is not usable."
            ),
            suggested_actions=[
                "Do NOT raise max_iterations. More iterations of a diverging solve "
                "diverge further; the input is the problem, not the budget.",
                "A narrow window is a cause rather than a symptom: a point the "
                "window cannot constrain is what makes the solve blow up. Widen "
                "window_size, or use BundleAdjustmentGlobal, which holds nothing out.",
                "Check the input model's median_triangulation_angle. Structure on "
                "near-parallel rays is where this starts.",
            ],
            see_also="limitations.md#thin-windows",
        )

    if readings["escaped"] and not blew_up:
        out.diagnostic(
            "points_escaped",
            severity="warn",
            message=(
                f"{readings['escaped']} of {len(after_errors)} points ended the solve "
                f"with an error larger than the image ({extent:.0f}px). They are "
                f"counted in escaped_points and left out of every error reading, "
                f"the window's included; the tail of what stayed is intact, so the "
                f"solve did not diverge."
            ),
            suggested_actions=[
                "Judge the model on the readings that ARE published. An escaped "
                "point moves only a mean; a diverged solve moves the whole "
                "distribution, and this one did not.",
                ("Under the robust loss an escapee's pull on the cameras is bounded, "
                 "so it says nothing about the poses either way."
                 if p.robust_loss else
                 "robust_loss is OFF on this run, so nothing bounded the escapee's "
                 "pull on the cameras; read the pose-side readings with that in mind."),
                "The escapees are still in the artifact, with their values in "
                "points/error. Filter on that array before measuring anything else "
                "from the cloud.",
                "Here they usually mean the window left points it cannot constrain: "
                "widen window_size, or use BundleAdjustmentGlobal, which holds "
                "nothing out.",
            ],
            see_also="limitations.md#an-escaped-point-is-not-a-diverged-solve",
        )

    if not blew_up and win_before > 0 and abs(win_before - win_after) / win_before < 0.01:
        out.diagnostic(
            "no_improvement",
            severity="info",
            message=f"Window error moved {win_before:.3f} -> {win_after:.3f}px.",
            suggested_actions=[
                "Nothing, if the window error is already low.",
                "Try anchor: largest_error to refine somewhere that needs it.",
            ],
            see_also="tuning.md#window_error-does-not-move",
        )

    dropped = points_in - len(point_ids)
    if dropped > 0:
        share = dropped / points_in if points_in else 0.0
        out.diagnostic(
            "points_dropped_by_min_track_length",
            severity="warn" if share >= 0.10 else "info",
            message=(
                f"min_track_length={p.min_track_length} removed {dropped} of "
                f"{points_in} points ({share:.1%}). They are ABSENT FROM THIS "
                f"ARTIFACT, not merely excluded from the solve."
            ),
            suggested_actions=[
                "Read point_count, not points_optimized. points_optimized counts "
                "the window, so it cannot separate a point dropped by this filter "
                "from one that simply lies outside the window.",
                "This is not optional bookkeeping: a point held out of the solve "
                "would keep the INPUT's coordinate frame while every optimised "
                "point and camera moves, and bundle adjustment does not preserve "
                "the gauge. Dropping is the only consistent choice.",
                "This module defaults to 3 where the global one defaults to 2, so "
                "it discards more of the same cloud by default. On a two-view "
                "dominated model that is most of it -- read two_view_fraction on "
                "the input before choosing between the two adjusters.",
            ],
            see_also="tuning.md#min_track_length-defaults-to-3-here-not-2",
        )

    if len(point_ids) < 50:
        out.diagnostic(
            "too_few_points",
            severity="warn",
            message=f"Only {len(point_ids)} points survived into the solve.",
            suggested_actions=[
                f"Raise window_size above {p.window_size}.",
                "Lower min_track_length to 2.",
            ],
            see_also="limitations.md#thin-windows",
        )

    if blew_up:
        outcome = (f"Window error {win_before:.3f}px -> DIVERGED: "
                   f"{readings['escaped']} points left the image or the tail grew by "
                   f"orders of magnitude, in {iterations} iterations. Error metrics "
                   f"are suppressed; this model is not usable.")
    else:
        outcome = (f"Window error {win_before:.3f} -> {win_after:.3f}px; whole model "
                   f"{error_before:.3f} -> {error_after:.3f}px in {iterations} "
                   f"iterations, {'converged' if converged else 'DID NOT converge'}. "
                   f"The global figure is diluted by the cameras that were held "
                   f"fixed -- judge this on the window.")
        if readings["escaped"]:
            outcome += (f" {readings['escaped']} point(s) escaped the image and are "
                        f"left out of the error readings; the solve did not diverge.")
    out.note(
        f"Local bundle adjustment, anchor '{p.anchor}': {len(window_ids)} cameras "
        f"refined, {len(fixed_ids)} held fixed, {len(point_ids)} points. " + outcome
    )
