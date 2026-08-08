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


@module
def run(ctx: Ctx):
    scene = ctx.inputs["scene"]
    sparse = ctx.inputs["sparse"]
    p = ctx.params

    n_images = len(scene.load("images", "names"))

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
    source_track = np.asarray(sparse.load("points").get("track_id"))
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

    if p.refine_focal_length or p.refine_principal_point:
        K = np.tile(np.eye(3), (n_images, 1, 1))
        for frame, image_id in image_id_of.items():
            camera = rec.camera(image_id)
            fx, fy, cx, cy = camera.params
            K[frame] = [[fx, 0, cx], [0, fy, cy], [0, 0, 1]]
        out.save("intrinsics", K=K)

    # Native rendering beside the authoritative npz.
    rec.write_binary(str(out.sidecar_dir("colmap")))

    reduction = (error_before - error_after) / error_before if error_before > 0 else 0.0

    out.metric("reprojection_error_before", round(error_before, 4),
               direction="lower_better", healthy=(None, 2.0))
    out.metric("reprojection_error_after", round(error_after, 4),
               direction="lower_better", healthy=(None, 1.0))
    out.metric("error_reduction", round(reduction, 4),
               direction="higher_better", healthy=(0.0, None))
    out.metric("points_optimized", len(point_ids),
               direction="higher_better", healthy=(100, None))
    out.metric("observations_optimized", len(obs_rows),
               direction="higher_better", healthy=(300, None))
    out.metric("iterations", iterations, direction="neutral")
    out.metric("converged", int(converged), direction="higher_better", healthy=(1, None))

    if not converged:
        out.diagnostic(
            "did_not_converge",
            severity="warn",
            message=f"Ceres stopped after {iterations} iterations without converging.",
            suggested_actions=[
                "Check reprojection_error_before; BA cannot rescue a badly wrong input.",
                f"Raise max_iterations above {p.max_iterations} if it stopped at the cap.",
            ],
            see_also="tuning.md#converged-is-0",
        )

    if abs(reduction) < 0.01:
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

    if error_after > 1.5:
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

    out.note(
        f"Global bundle adjustment over {len(image_id_of)} cameras, "
        f"{len(point_ids)} points and {len(obs_rows)} observations. "
        f"Reprojection error {error_before:.3f}px -> {error_after:.3f}px "
        f"({reduction:+.1%}) in {iterations} iterations, "
        f"{'converged' if converged else 'DID NOT converge'}. "
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
    converged = termination is not None and "CONVERGENCE" in str(termination).upper()

    # is_solution_usable is the weaker but more reliable signal when the
    # termination enum is not exposed.
    if termination is None and getattr(summary, "is_solution_usable", None):
        converged = bool(summary.is_solution_usable())

    return iterations, converged
