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


def window_error(rec, image_ids: set[int]) -> float:
    """Mean reprojection error over the given cameras only.

    The global figure dilutes a local solve with cameras that were held fixed, so
    it understates what this module actually did.
    """
    total, count = 0.0, 0
    for image_id in image_ids:
        image = rec.image(image_id)
        for p2d in image.points2D:
            if not p2d.has_point3D() or not rec.exists_point3D(p2d.point3D_id):
                continue
            point = rec.point3D(p2d.point3D_id)
            projected = image.project_point(point.xyz)
            if projected is None:
                continue
            total += float(np.linalg.norm(np.asarray(projected) - np.asarray(p2d.xy)))
            count += 1
    return total / count if count else float("nan")


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


@module
def run(ctx: Ctx):
    scene = ctx.inputs["scene"]
    sparse = ctx.inputs["sparse"]
    p = ctx.params

    n_images = len(scene.load("images", "names"))

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
    error_before = float(rec.compute_mean_reprojection_error())

    window = choose_window(rec, image_id_of, p.anchor, p.window_size)
    window_ids = {image_id_of[f] for f in window}
    fixed_ids = [i for i in image_id_of.values() if i not in window_ids]
    win_before = window_error(rec, window_ids)

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
    error_after = float(rec.compute_mean_reprojection_error())
    win_after = window_error(rec, window_ids)
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
    source_track = np.asarray(sparse.load("points").get("track_id"))

    obs_rows = []
    id_to_frame = {v: k for k, v in image_id_of.items()}
    for pid in point_ids:
        for element in rec.point3D(pid).track.elements:
            xy = rec.image(element.image_id).point2D(element.point2D_idx).xy
            obs_rows.append(
                [id_to_frame[element.image_id], inverse[pid], float(xy[0]), float(xy[1])]
            )

    out.save(
        "points",
        xyz=np.array([rec.point3D(pid).xyz for pid in point_ids], dtype=np.float64),
        rgb=np.array([rec.point3D(pid).color for pid in point_ids], dtype=np.uint8),
        error=np.array([rec.point3D(pid).error for pid in point_ids], dtype=np.float64),
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

    out.metric("reprojection_error_before", round(error_before, 4),
               direction="lower_better", healthy=(None, 2.0))
    out.metric("reprojection_error_after", round(error_after, 4),
               direction="lower_better", healthy=(None, 1.0))
    out.metric("window_error_before", round(win_before, 4),
               direction="lower_better", healthy=(None, 2.0))
    out.metric("window_error_after", round(win_after, 4),
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
    out.metric("point_count", len(point_ids),
               direction="higher_better", healthy=(50, None))
    out.metric("observation_count", len(obs_rows),
               direction="higher_better", healthy=(100, None))
    out.metric("mean_track_length",
               round(len(obs_rows) / len(point_ids), 3) if point_ids else 0.0,
               direction="higher_better", healthy=(2.5, None))
    out.metric("mean_reprojection_error", round(error_after, 4),
               direction="lower_better", healthy=(None, 1.0))
    out.metric("registered_images", int(np.asarray(valid, dtype=bool).sum()),
               direction="higher_better", healthy=(3, None))

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
            message=f"Ceres stopped after {iterations} iterations without converging.",
            suggested_actions=[f"Raise max_iterations above {p.max_iterations}."],
            see_also="tuning.md#converged-is-0",
        )

    if win_before > 0 and abs(win_before - win_after) / win_before < 0.01:
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

    out.note(
        f"Local bundle adjustment, anchor '{p.anchor}': {len(window_ids)} cameras "
        f"refined, {len(fixed_ids)} held fixed, {len(point_ids)} points. "
        f"Window error {win_before:.3f} -> {win_after:.3f}px; whole model "
        f"{error_before:.3f} -> {error_after:.3f}px in {iterations} iterations, "
        f"{'converged' if converged else 'DID NOT converge'}. The global figure is "
        f"diluted by the cameras that were held fixed -- judge this on the window."
    )
