"""BundleAdjustmentGlobal -- scene/v1 + sparse_model/v1 -> sparse_model/v1.

Ceres bundle adjustment over every pose and every point, via pycolmap.

The whole module is a translation exercise: arrays in, a pycolmap Reconstruction,
the solve, arrays back out. The translation is where the care is needed, because
COLMAP's conventions and ours agree in most places and not all.
"""

from __future__ import annotations

import numpy as np
import pycolmap
from sfmkit import Ctx, module


def diverged(before: float, after: float) -> bool:
    """Did the solve blow up rather than refine?

    A Ceres solve that loses its trust region does not return a large-but-real
    number; it returns something with no physical meaning at all -- 1e151 px was
    observed on a model built from a learned depth prior. That value was then
    published as `mean_reprojection_error` with `direction: lower_better` and a
    `still_high_error` warning suggesting more iterations, which is advice that
    cannot help and a metric a downstream reader would try to compare.

    The pose estimator grew the same guard for its in-loop solve; this is the
    same check on the module that does the whole model at once. Bounded well above
    any real reprojection error at any working resolution, so a genuinely bad
    model still reports its bad number.
    """
    return not np.isfinite(after) or after > 1e4 or after > 1e3 * max(before, 1e-6)


def build_reconstruction(scene, sparse, n_images, min_track_length, ctx):
    """Arrays -> pycolmap.Reconstruction.

    One COLMAP camera per registered image. That is wasteful when the whole set
    shares intrinsics, but it is the only shape that also handles a
    mixed-resolution capture or a multi-camera rig, and BA does not care -- it
    solves the same problem either way unless intrinsics are being refined, in
    which case per-image cameras is the honest model for per-image K.
    """
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

    # frame index -> colmap image id. COLMAP ids are 1-based and must be dense
    # over what is registered; our frame indices are neither.
    image_id_of: dict[int, int] = {}
    next_id = 1
    for k in range(len(image_index)):
        if not valid[k]:
            continue
        image_id_of[int(image_index[k])] = next_id
        next_id += 1

    # Observations grouped by frame, because a colmap Image carries its own
    # points2D list and the index into that list is what a track element cites.
    obs_frame = obs[:, 0].astype(int)
    obs_point = obs[:, 1].astype(int)
    obs_xy = obs[:, 2:4]

    order = np.argsort(obs_frame, kind="stable")
    obs_frame, obs_point, obs_xy = obs_frame[order], obs_point[order], obs_xy[order]

    # point id -> [(image_id, index within that image's points2D)]
    track_elements: dict[int, list[tuple[int, int]]] = {}

    for frame, image_id in sorted(image_id_of.items(), key=lambda kv: kv[1]):
        rows = np.flatnonzero(obs_frame == frame)
        K = K_all[frame]
        w, h = int(sizes[frame][0]), int(sizes[frame][1])

        camera = pycolmap.Camera.create_from_model_id(
            camera_id=image_id,
            model=pycolmap.CameraModelId.PINHOLE,
            focal_length=float(K[0, 0]),
            width=w,
            height=h,
        )
        # PINHOLE is [fx, fy, cx, cy]. Set explicitly rather than trusting the
        # helper's square-pixel default -- a resized scene rarely has fx == fy.
        camera.params = [float(K[0, 0]), float(K[1, 1]), float(K[0, 2]), float(K[1, 2])]
        rec.add_camera_with_trivial_rig(camera)

        points2D = []
        for local_index, r in enumerate(rows):
            points2D.append(pycolmap.Point2D(obs_xy[r]))
            track_elements.setdefault(int(obs_point[r]), []).append(
                (image_id, local_index)
            )

        image = pycolmap.Image(
            name=str(names[frame]), camera_id=image_id, points2D=points2D
        )
        image.image_id = image_id

        P = cam_from_world[np.flatnonzero(image_index == frame)[0]]
        rigid = pycolmap.Rigid3d(pycolmap.Rotation3d(P[:, :3]), P[:, 3])
        rec.add_image_with_trivial_frame(image, rigid)

    ctx.progress(0.35, f"{len(image_id_of)} cameras, adding points")

    kept_point_ids: dict[int, int] = {}
    for point_index, elements in track_elements.items():
        if len(elements) < min_track_length:
            continue
        track = pycolmap.Track([pycolmap.TrackElement(i, j) for i, j in elements])
        colour = (
            np.asarray(rgb[point_index], dtype=np.uint8)
            if rgb is not None
            else np.array([128, 128, 128], dtype=np.uint8)
        )
        kept_point_ids[point_index] = rec.add_point3D(xyz[point_index], track, colour)

    return rec, image_id_of, kept_point_ids, cam_from_world, valid, image_index


def intrinsics_for(scene, sparse, n_images):
    """Per-image K, preferring what the sparse model carries over the scene."""
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
            "the scene carries any. A pose estimator that estimated K writes it "
            "into its artifact; a classical one expects it on the scene."
        )

    if cam_index is None:
        cam_index = np.arange(n_images) if len(K) == n_images else np.zeros(n_images, int)
    return K[np.asarray(cam_index, dtype=int)]


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
    rec, image_id_of, kept_point_ids, cam_from_world, valid, image_index = (
        build_reconstruction(scene, sparse, n_images, p.min_track_length, ctx)
    )

    if rec.num_points3D() == 0:
        raise ValueError(
            f"no point survived min_track_length={p.min_track_length}; there is "
            f"nothing to optimise. Lower it, or check the triangulator's "
            f"mean_track_length -- a purely two-view cloud has no redundancy for "
            f"bundle adjustment to exploit."
        )

    # compute_mean_reprojection_error() averages a per-point `error` field that
    # COLMAP leaves unset until asked. Without this call it reports 0.0 on a
    # freshly built reconstruction, which reads as a perfect model rather than an
    # unmeasured one -- and then "improves" to a nonzero number after the solve.
    rec.update_point_3d_errors()
    error_before = float(rec.compute_mean_reprojection_error())
    n_obs = int(rec.compute_num_observations())

    options = pycolmap.BundleAdjustmentOptions()
    options.refine_focal_length = p.refine_focal_length
    options.refine_principal_point = p.refine_principal_point
    options.refine_extra_params = False  # PINHOLE has none; observations are undistorted
    options.refine_points3D = True
    options.refine_rig_from_world = True
    options.min_track_length = p.min_track_length
    # Ceres solver knobs live one level down, on `ceres.solver_options`, and the
    # object rejects unknown attributes -- so a typo here is an AttributeError at
    # solve time rather than a silently ignored setting. That is the good case.
    options.ceres.solver_options.max_num_iterations = p.max_iterations
    if p.robust_loss:
        options.ceres.loss_function_type = pycolmap.LossFunctionType.CAUCHY
        options.ceres.loss_function_scale = p.loss_scale
    else:
        options.ceres.loss_function_type = pycolmap.LossFunctionType.TRIVIAL

    # `pycolmap.bundle_adjustment(rec, options)` is the one-liner, but it returns
    # None -- so iteration counts and convergence would be invented. Building the
    # adjuster explicitly costs three lines and gives a real summary, which is the
    # difference between reporting convergence and assuming it.
    config = pycolmap.BundleAdjustmentConfig()
    for image_id in image_id_of.values():
        config.add_image(image_id)
    config.fix_gauge(pycolmap.BundleAdjustmentGauge.TWO_CAMS_FROM_WORLD)

    ctx.progress(0.5, f"solving: {rec.num_points3D()} points, {n_obs} observations")
    adjuster = pycolmap.create_default_bundle_adjuster(options, config, rec)
    summary = adjuster.solve()

    rec.update_point_3d_errors()
    error_after = float(rec.compute_mean_reprojection_error())
    ctx.progress(0.8, f"{error_before:.3f}px -> {error_after:.3f}px")

    iterations, converged = read_summary(summary)

    # ------------------------------------------------------------- write back
    out = ctx.output("sparse")

    refined_poses = cam_from_world.copy()
    for frame, image_id in image_id_of.items():
        pose = rec.image(image_id).cam_from_world()
        row = np.flatnonzero(image_index == frame)[0]
        refined_poses[row] = np.hstack(
            [pose.rotation.matrix(), pose.translation.reshape(3, 1)]
        )

    point_ids = sorted(kept_point_ids.values())
    xyz = np.array([rec.point3D(pid).xyz for pid in point_ids], dtype=np.float64)
    rgb = np.array([rec.point3D(pid).color for pid in point_ids], dtype=np.uint8)
    error = np.array([rec.point3D(pid).error for pid in point_ids], dtype=np.float64)

    # Original track ids survive the round trip so a consumer can still relate a
    # point back to the tracks artifact that produced it.
    # NOT np.asarray(...) on the get(): np.asarray(None) is a 0-d object array,
    # which is not None, so the guard below would pass and the indexing would
    # raise. track_id is OPTIONAL in sparse_model/v1 and most producers omit it.
    source_track = sparse.load("points").get("track_id")
    source_track = None if source_track is None else np.asarray(source_track)
    inverse = {pid: idx for idx, pid in enumerate(point_ids)}
    original_index = {v: k for k, v in kept_point_ids.items()}
    track_id = np.array(
        [
            int(source_track[original_index[pid]]) if source_track is not None else -1
            for pid in point_ids
        ],
        dtype=np.int32,
    )

    obs_rows = []
    id_to_frame = {v: k for k, v in image_id_of.items()}
    for pid in point_ids:
        point = rec.point3D(pid)
        for element in point.track.elements:
            image = rec.image(element.image_id)
            xy = image.point2D(element.point2D_idx).xy
            obs_rows.append(
                [id_to_frame[element.image_id], inverse[pid], float(xy[0]), float(xy[1])]
            )

    out.save("points", xyz=xyz, rgb=rgb, error=error, track_id=track_id)
    out.save("observations", obs=np.array(obs_rows, dtype=np.float64))
    out.save(
        "poses",
        cam_from_world=refined_poses,
        valid=valid,
        image_index=image_index.astype(np.int32),
    )

    refined_K = None
    if p.refine_focal_length or p.refine_principal_point:
        refined_K = np.tile(np.eye(3), (n_images, 1, 1))
        for frame, image_id in image_id_of.items():
            camera = rec.camera(image_id)  # camera_id == image_id by construction
            fx, fy, cx, cy = camera.params
            refined_K[frame] = [[fx, 0, cx], [0, fy, cy], [0, 0, 1]]
        out.save("intrinsics", K=refined_K)

    # Native rendering beside the authoritative npz.
    rec.write_binary(str(out.sidecar_dir("colmap")))

    blew_up = diverged(error_before, error_after)
    reduction = (error_before - error_after) / error_before if error_before > 0 else 0.0
    if blew_up:
        # Suppress rather than publish. A diverged solve has no reprojection error
        # to report, and a number with no meaning is worse than a null because a
        # reader will compare it.
        reduction = None

    out.metric("reprojection_error_before", round(error_before, 4),
               direction="lower_better", healthy=(None, 2.0))
    out.metric("reprojection_error_after",
               None if blew_up else round(error_after, 4),
               direction="lower_better", healthy=(None, 1.0))
    out.metric("error_reduction", None if blew_up else round(reduction, 4),
               direction="higher_better", healthy=(0.0, None))
    out.metric("points_optimized", len(point_ids),
               direction="higher_better", healthy=(100, None))
    out.metric("observations_optimized", len(obs_rows),
               direction="higher_better", healthy=(300, None))
    out.metric("iterations", iterations, direction="neutral")
    out.metric("converged", int(converged), direction="higher_better", healthy=(1, None))

    # The sparse_model/v1 contract: metrics describing the ARTIFACT, so a consumer
    # can compare this model against one from a triangulator or a feed-forward
    # reconstructor. The before/after pair above describes the PROCESS and is
    # comparable only against another bundle adjustment.
    _obs = np.array(obs_rows, dtype=np.float64)
    _s = structure_readings(xyz, _obs, error, refined_poses, valid, None, n_images)
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

    # This module WRITES intrinsics that every downstream consumer prefers over the
    # scene's, and until now it published nothing about them -- so a refinement that
    # gave a one-lens rig twelve different focal lengths, and improved reprojection
    # error by 21% doing it, was invisible unless a reader dumped two artifacts and
    # divided. plan/pose.md names estimated_focal_ratio as the warning that
    # matters when a module estimates K; this is that reading, plus the spread that
    # says whether one physical camera is being modelled as many.
    if refined_K is not None:
        supplied = intrinsics_for(scene, sparse, n_images)
        reg = np.flatnonzero(np.asarray(valid, dtype=bool))
        ratios = np.array(
            [refined_K[f][0, 0] / supplied[f][0, 0] for f in reg
             if supplied[f][0, 0] > 0], dtype=np.float64
        )
        if len(ratios):
            out.metric("estimated_focal_ratio", round(float(ratios.mean()), 4),
                       direction="neutral", healthy=(0.95, 1.05))
            spread = float(ratios.max() - ratios.min())
            out.metric("focal_spread", round(spread, 4),
                       direction="lower_better", healthy=(None, 0.01))
            if spread > 0.01 and len(np.unique(supplied[reg, 0, 0])) == 1:
                out.diagnostic(
                    "refined_focal_disagrees_across_cameras",
                    severity="warn",
                    message=(
                        f"The scene supplies ONE focal length and the refinement "
                        f"produced {len(ratios)} that span {spread:.1%}."
                    ),
                    suggested_actions=[
                        "A fixed lens cannot have a different focal length per "
                        "frame. A spread this size is pose error being absorbed "
                        "into intrinsics, which is what a lower reprojection error "
                        "here is buying.",
                        "Turn refine_focal_length off. A supplied calibration beats "
                        "what BA recovers from a short sequence, and the refined K "
                        "is written into this artifact where every consumer will "
                        "prefer it.",
                        "If the calibration is genuinely suspect, estimated_focal_"
                        "ratio is the number to act on -- a consistent same-sign "
                        "pull across all cameras is a calibration error; a scatter "
                        "is over-fitting.",
                    ],
                    see_also="tuning.md#refine_focal_length",
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
                "Read point_count, not points_optimized. The two are equal by "
                "construction here, so points_optimized cannot reveal this.",
                "This is not optional bookkeeping: a point held out of the solve "
                "would keep the INPUT's coordinate frame while every optimised "
                "point and camera moves, and bundle adjustment does not preserve "
                "the gauge. Dropping is the only consistent choice.",
                "min_track_length: 2 keeps everything. On a two-view-dominated "
                "cloud that is usually right -- two-view points are measurably "
                "improved by the solve, because the cameras move and they move "
                "with them.",
            ],
            see_also="tuning.md#min_track_length",
        )

    if blew_up:
        out.diagnostic(
            "bundle_adjustment_diverged",
            severity="error",
            message=(
                f"The solve diverged: reprojection error went {error_before:.3f}px "
                f"-> {error_after:.3g}px. Every error metric on this artifact is "
                f"suppressed; the model it contains is not usable."
            ),
            suggested_actions=[
                "Do NOT raise max_iterations. More iterations of a diverging solve "
                "diverge further; the input is the problem, not the budget.",
                "Check the input model's own mean_reprojection_error and "
                "median_triangulation_angle. Divergence here has been traced to "
                "structure that is under-constrained rather than merely inaccurate "
                "-- points on near-parallel rays, or placed by a depth prior and "
                "never verified against a second view.",
                "min_track_length: 3 drops points carried by two views, which is "
                "where under-constrained structure concentrates. Read point_count "
                "afterwards: it will fall, and that is the trade.",
                "If the input came from a learned prior, triangulate the same tracks "
                "geometrically and bundle-adjust that instead.",
            ],
            see_also="limitations.md#what-bundle-adjustment-cannot-fix",
        )

    if not converged and not blew_up:
        out.diagnostic(
            "did_not_converge",
            severity="warn",
            message=(
                f"Ceres stopped after {iterations} iterations without "
                f"converging (cap {p.max_iterations})."
            ),
            suggested_actions=[
                f"Raise max_iterations above {p.max_iterations} if `iterations` is "
                f"AT OR NEAR the cap. It reports cap+1 on a capped run, so it never "
                f"equals the cap and 'stopped at the cap' is not a test that passes.",
                "If it stalled well BELOW the cap, more iterations will not help and "
                "the robust loss is the usual cause: a Cauchy loss can keep the "
                "trust-region step from meeting Ceres' tolerance on a model that is "
                "already at its optimum. Confirm by re-running at a higher cap -- if "
                "the error is identical to four decimals, the solve was finished and "
                "the flag is the only thing that was not.",
                "Before spending a run on either: a converged flag has been measured "
                "worth NOTHING on this stack. Capped and converged solves of the same "
                "problem agreed to four decimal places every time. Read "
                "reprojection_error_after, and treat `converged` as bookkeeping "
                "unless the error is also bad.",
                "Check reprojection_error_before; BA cannot rescue a badly wrong input.",
            ],
            see_also="tuning.md#converged-is-0",
        )

    if not blew_up and abs(reduction) < 0.01:
        out.diagnostic(
            "no_improvement",
            severity="info",
            message=f"Error moved {error_before:.3f} -> {error_after:.3f}px.",
            suggested_actions=[
                "Nothing, if the error is already low.",
                "If it is high and unchanged, the poses are at a bad local minimum.",
            ],
            see_also="tuning.md#error_reduction-near-zero",
        )

    if not blew_up and error_after > 1.5:
        out.diagnostic(
            "still_high_error",
            severity="warn",
            message=f"Mean reprojection error is {error_after:.2f}px after optimisation.",
            suggested_actions=[
                "Tighten the triangulator's angle and reprojection filters.",
                "Check the tracker's inconsistent_rate; wrong tracks cannot be optimised away.",
            ],
            see_also="limitations.md#what-bundle-adjustment-cannot-fix",
        )

    if blew_up:
        outcome = (f"Reprojection error {error_before:.3f}px -> DIVERGED "
                   f"({error_after:.3g}px) in {iterations} iterations. "
                   f"Error metrics are suppressed; this model is not usable. ")
    else:
        outcome = (f"Reprojection error {error_before:.3f}px -> {error_after:.3f}px "
                   f"({reduction:+.1%}) in {iterations} iterations, "
                   f"{'converged' if converged else 'DID NOT converge'}. ")
    out.note(
        f"Global bundle adjustment over {len(image_id_of)} cameras, "
        f"{len(point_ids)} points and {len(obs_rows)} observations. "
        + outcome +
        f"Intrinsics {'refined' if p.refine_focal_length else 'held fixed'}. "
        f"A COLMAP model is written as the `colmap` sidecar."
    )


def read_summary(summary) -> tuple[int, bool]:
    """Iterations and convergence out of the Ceres summary.

    Reported honestly or not at all: a summary this cannot read yields 0
    iterations and converged=False, so the artifact says "I do not know" rather
    than "it converged". The metric exists to be trusted when the solve goes
    wrong, which is exactly when a cheerful default would mislead.
    """
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

    termination = getattr(summary, "termination_type", None)
    if termination is None:
        termination = getattr(ceres, "termination_type", None)

    # Compare the enum NAME exactly. A substring test is wrong here in a way that
    # is easy to miss and always fails safe-looking: "CONVERGENCE" is a substring
    # of "NO_CONVERGENCE", so `in` reports success on precisely the solves that
    # ran out of iterations. That is the case this metric exists to catch.
    converged = termination is not None and _termination_name(termination) == "CONVERGENCE"

    # is_solution_usable is the weaker but more reliable signal when the
    # termination enum is not exposed at all.
    if termination is None and getattr(summary, "is_solution_usable", None):
        converged = bool(summary.is_solution_usable())

    return iterations, converged


def _termination_name(termination) -> str:
    """'TerminationType.NO_CONVERGENCE' / an enum / a bare string -> 'NO_CONVERGENCE'."""
    name = getattr(termination, "name", None)
    if isinstance(name, str):
        return name.upper()
    return str(termination).rsplit(".", 1)[-1].upper()
