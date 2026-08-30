"""SparseTriangulationGTSAM -- scene/v1 + tracks/v1 + poses/v1 -> sparse_model/v1.

Multi-view triangulation through GTSAM: the LOST estimator over every observing
view, optional nonlinear refinement, then the same filtering vocabulary as
SparseTriangulation so the two are interchangeable.

Observations are undistorted once and a distortion-free Cal3_S2 is handed to
GTSAM. Passing raw pixels with a Cal3DS2 would also work and would make every
solve pay for the distortion model; undistorting once is cheaper and keeps the
reprojection error reported here in the same units as every other module's.
"""

from __future__ import annotations

import cv2
import gtsam
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


def undistort(points: np.ndarray, K: np.ndarray, dist: np.ndarray) -> np.ndarray:
    """Pixels -> undistorted PIXELS (not normalised); GTSAM wants pixels + K."""
    if len(points) == 0:
        return points.reshape(0, 2).astype(np.float64)
    p = np.ascontiguousarray(points, dtype=np.float64).reshape(-1, 1, 2)
    normalised = cv2.undistortPoints(p, K, dist.reshape(1, -1)).reshape(-1, 2)
    return normalised @ K[:2, :2].T + K[:2, 2]


def camera_center(pose: np.ndarray) -> np.ndarray:
    return -pose[:, :3].T @ pose[:, 3]


def gtsam_camera(pose: np.ndarray, K: np.ndarray):
    """cam_from_world 3x4 -> a GTSAM camera, which wants world_from_cam."""
    R = np.asarray(pose[:, :3], dtype=np.float64)
    t = np.asarray(pose[:, 3], dtype=np.float64)
    world_from_cam = gtsam.Pose3(gtsam.Rot3(R.T), gtsam.Point3(-R.T @ t))
    cal = gtsam.Cal3_S2(
        float(K[0, 0]), float(K[1, 1]), 0.0, float(K[0, 2]), float(K[1, 2])
    )
    return gtsam.PinholeCameraCal3_S2(world_from_cam, cal)


def widest_angle(centers: np.ndarray, point: np.ndarray) -> float:
    """Largest angle any pair of observing views subtends at the point.

    The widest, not the mean: one well-separated pair conditions the depth, and
    averaging it against a cluster of near-coincident views hides that.
    """
    rays = point[None, :] - centers
    norms = np.linalg.norm(rays, axis=1)
    good = norms > 1e-12
    if good.sum() < 2:
        return 0.0
    unit = rays[good] / norms[good][:, None]
    cos = np.clip(unit @ unit.T, -1.0, 1.0)
    a, b = np.triu_indices(len(unit), k=1)
    return float(np.arccos(cos[a, b]).max() * DEG)


@module
def run(ctx: Ctx):
    scene = ctx.inputs["scene"]
    tracks = ctx.inputs["tracks"]
    poses_art = ctx.inputs["poses"]
    p = ctx.params

    names = scene.load("images", "names")
    n_images = len(names)

    if not scene.has("calibration"):
        out = ctx.output("sparse")
        out.diagnostic(
            "uncalibrated_scene",
            severity="error",
            message="The scene carries no intrinsics.",
            see_also="limitations.md#uncalibrated-scenes",
        )
        raise ValueError(
            "SparseTriangulationGTSAM needs intrinsics and this scene has none. "
            "Pass calibration_path to SceneLoader."
        )

    K_all, dist_all = per_image_intrinsics(scene, n_images)

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
            f"only {len(pose_of)} image(s) carry a valid pose; triangulation needs "
            f"at least two. Check the pose estimator's registered_fraction."
        )

    obs = np.asarray(tracks.load("observations", "obs"), dtype=np.float64)
    n_tracks_in = int(tracks.load("observations", "track_count"))

    track_id = obs[:, 0].astype(np.int64)
    frame = obs[:, 1].astype(np.int64)

    # Undistort once per frame rather than per observation: the same call on a
    # frame's whole block is one OpenCV crossing instead of thousands.
    undistorted = np.zeros((len(obs), 2), dtype=np.float64)
    for f in range(n_images):
        rows = np.flatnonzero(frame == f)
        if len(rows) == 0:
            continue
        undistorted[rows] = undistort(obs[rows, 2:4], K_all[f], dist_all[f])

    order = np.argsort(track_id, kind="stable")
    track_id, frame, undistorted = track_id[order], frame[order], undistorted[order]
    bounds = np.flatnonzero(np.diff(track_id)) + 1
    groups = np.split(np.arange(len(track_id)), bounds)

    cameras_of_frame = {f: gtsam_camera(pose_of[f], K_all[f]) for f in pose_of}
    centers_of_frame = {f: camera_center(pose_of[f]) for f in pose_of}

    ctx.progress(0.15, f"{len(groups)} tracks, {len(pose_of)} posed cameras")

    xyz_out, obs_out, angles, errors, shifts, lengths = [], [], [], [], [], []
    kept_track: list[int] = []  # tracks/v1 id per surviving point, as the type allows
    rejected = {"angle": 0, "reprojection": 0, "cheirality": 0, "distance": 0, "solve": 0}

    for gi, rows in enumerate(groups):
        if gi % 2000 == 0 and gi:
            ctx.progress(
                0.15 + 0.65 * gi / max(len(groups), 1),
                f"{gi}/{len(groups)} tracks, {len(xyz_out)} points",
            )

        seen = [r for r in rows if int(frame[r]) in pose_of]
        if len(seen) < max(p.min_track_len, 2):
            continue

        frames = [int(frame[r]) for r in seen]
        cameras = gtsam.CameraSetCal3_S2()
        measurements = gtsam.Point2Vector()
        for r, f in zip(seen, frames):
            cameras.append(cameras_of_frame[f])
            measurements.append(gtsam.Point2(undistorted[r, 0], undistorted[r, 1]))

        try:
            point = np.asarray(
                gtsam.triangulatePoint3(
                    cameras, measurements, p.rank_tolerance, p.optimize,
                    None, p.use_lost,
                ),
                dtype=np.float64,
            ).ravel()
        except Exception:
            # GTSAM raises on cheirality and on a rank-deficient system. Both are
            # legitimate rejections, and both are counted rather than swallowed.
            rejected["solve"] += 1
            continue

        if not np.isfinite(point).all():
            rejected["solve"] += 1
            continue

        if p.optimize:
            try:
                linear = np.asarray(
                    gtsam.triangulatePoint3(
                        cameras, measurements, p.rank_tolerance, False,
                        None, p.use_lost,
                    ),
                    dtype=np.float64,
                ).ravel()
                if np.isfinite(linear).all():
                    shifts.append(float(np.linalg.norm(point - linear)))
            except Exception:
                pass

        centers = np.array([centers_of_frame[f] for f in frames])

        if p.max_landmark_distance > 0.0:
            if np.linalg.norm(point[None, :] - centers, axis=1).max() > p.max_landmark_distance:
                rejected["distance"] += 1
                continue

        angle = widest_angle(centers, point)
        if angle < p.min_triangulation_angle_deg:
            rejected["angle"] += 1
            continue

        # Cheirality and reprojection, checked in EVERY observing view: one bad
        # observation is enough to drag a bundle adjustment.
        per_view, ok = [], True
        for r, f in zip(seen, frames):
            cam = pose_of[f]
            in_camera = cam[:, :3] @ point + cam[:, 3]
            if in_camera[2] <= 1e-8:
                ok = False
                rejected["cheirality"] += 1
                break
            projected = in_camera[:2] / in_camera[2] @ K_all[f][:2, :2].T + K_all[f][:2, 2]
            err = float(np.linalg.norm(projected - undistorted[r]))
            if err > p.max_reprojection_error:
                ok = False
                rejected["reprojection"] += 1
                break
            per_view.append(err)
        if not ok:
            continue

        index = len(xyz_out)
        xyz_out.append(point)
        kept_track.append(int(track_id[seen[0]]))
        lengths.append(len(seen))
        angles.append(angle)
        errors.extend(per_view)
        for r, f in zip(seen, frames):
            obs_out.append([f, index, undistorted[r, 0], undistorted[r, 1]])

    if not xyz_out:
        out = ctx.output("sparse")
        out.diagnostic(
            "no_points",
            severity="error",
            message="No track survived triangulation.",
            see_also="tuning.md#nothing-survives",
        )
        # Name the filter that did it. "Nothing survived" plus five counts leaves
        # the reader to find the dominant one, and the right response is different
        # for each -- a distance bound eating everything is a units mistake, while
        # cheirality eating everything is a wrong pose.
        culprit, count = max(rejected.items(), key=lambda kv: kv[1])
        advice = {
            "angle": (f"lower min_triangulation_angle_deg below "
                      f"{p.min_triangulation_angle_deg} -- the capture has less "
                      f"baseline than the filter demands"),
            "reprojection": (f"max_reprojection_error is {p.max_reprojection_error} "
                             f"WORKING-resolution pixels; check the tracker's "
                             f"inconsistent_rate before raising it"),
            "cheirality": ("points landed behind cameras, which is the signature of "
                           "wrong POSES rather than strict thresholds -- check the "
                           "pose estimator's mean_reprojection_error"),
            "distance": (f"max_landmark_distance is {p.max_landmark_distance}, and it "
                         f"is a multiple of the seed pair's baseline, NOT metres. "
                         f"Set it to 0 to disable, then read the scene's actual "
                         f"extent before choosing a bound"),
            "solve": ("the observing views are near-coincident, so the linear system "
                      "is rank deficient -- the capture needs more baseline"),
        }[culprit]
        raise ValueError(
            f"no track survived: {len(groups)} tracks in, rejected "
            f"{rejected['angle']} on angle, {rejected['reprojection']} on "
            f"reprojection, {rejected['cheirality']} on cheirality, "
            f"{rejected['distance']} on distance, {rejected['solve']} unsolvable. "
            f"{count} of them went to '{culprit}': {advice}."
        )

    xyz = np.array(xyz_out, dtype=np.float64)
    obs_array = np.array(obs_out, dtype=np.float64)

    ctx.progress(0.9, f"{len(xyz)} points, sampling colour")

    # Colour by averaging the pixel under each observation. np.add.at rather than a
    # loop: one pass over the observation table instead of one per point.
    rgb = np.full((len(xyz), 3), 128, dtype=np.uint8)
    try:
        from PIL import Image  # noqa: PLC0415 -- optional; colour is not essential

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
    except ImportError:
        pass

    point_error = np.zeros(len(xyz), dtype=np.float64)
    counts = np.zeros(len(xyz), dtype=np.int64)
    residuals = np.array(errors, dtype=np.float64)
    np.add.at(point_error, obs_array[:, 1].astype(int), residuals)
    np.add.at(counts, obs_array[:, 1].astype(int), 1)
    point_error = point_error / np.maximum(counts, 1)

    out = ctx.output("sparse")
    # track_id makes this module actually interchangeable with SparseTriangulation:
    # without it a consumer cannot relate a point back to the track that made it,
    # and the two modules' outputs cannot be compared point for point.
    out.save("points", xyz=xyz, rgb=rgb, error=point_error,
             track_id=np.array(kept_track, dtype=np.int32))
    out.save("observations", obs=obs_array)
    out.save(
        "poses",
        cam_from_world=cam_from_world,
        valid=valid,
        image_index=image_index.astype(np.int32),
    )

    mean_error = float(residuals.mean())
    mean_length = float(np.mean(lengths))
    median_angle = float(np.median(angles))
    yield_rate = len(xyz) / max(n_tracks_in, 1)

    extent = float(np.linalg.norm(xyz.max(axis=0) - xyz.min(axis=0)))
    shift = (
        float(np.median(shifts) / extent) if shifts and extent > 0 else None
    )

    out.metric("point_count", len(xyz), direction="higher_better", healthy=(100, None))
    out.metric("observation_count", len(obs_array),
               direction="higher_better", healthy=(300, None))
    out.metric("mean_track_length", round(mean_length, 3),
               direction="higher_better", healthy=(2.5, None))
    out.metric("mean_reprojection_error", round(mean_error, 4),
               direction="lower_better", healthy=(None, 2.0))
    out.metric("median_triangulation_angle", round(median_angle, 2),
               direction="higher_better", healthy=(3.0, None))
    out.metric("yield", round(yield_rate, 3), direction="higher_better", healthy=(0.3, None))
    out.metric("registered_images", int(np.asarray(valid, dtype=bool).sum()),
               direction="higher_better", healthy=(3, None))
    out.metric("rejected_angle", rejected["angle"], direction="lower_better")
    out.metric("rejected_reprojection", rejected["reprojection"], direction="lower_better")
    out.metric("rejected_cheirality", rejected["cheirality"], direction="lower_better")
    out.metric("rejected_distance", rejected["distance"], direction="lower_better")
    out.metric("refinement_shift", round(shift, 6) if shift is not None else None,
               direction="lower_better", healthy=(None, 0.05))

    if mean_length < 2.2:
        out.diagnostic(
            "mostly_two_view",
            severity="info",
            message=(
                f"Mean track length is {mean_length:.2f}; LOST and a two-view DLT "
                f"are the same computation on a two-view track."
            ),
            suggested_actions=[
                "Use SparseTriangulation; it computes the same answer far more cheaply.",
                "Or widen the matcher's pairing so tracks reach more views -- "
                "`window` under sequential; under exhaustive lower min_matches.",
            ],
            see_also="limitations.md#two-view-tracks",
        )

    if rejected["cheirality"] > 0.2 * len(groups):
        out.diagnostic(
            "bad_poses_suspected",
            severity="warn",
            message=(
                f"{rejected['cheirality']} of {len(groups)} tracks landed behind "
                f"a camera."
            ),
            suggested_actions=[
                "Check the pose estimator's mean_reprojection_error and registered_fraction.",
                "Nothing in this module can fix a wrong pose.",
            ],
            see_also="limitations.md#it-cannot-fix-poses",
        )

    if median_angle < 3.0:
        out.diagnostic(
            "weak_structure",
            severity="warn",
            message=f"Median triangulation angle is {median_angle:.2f} degrees.",
            suggested_actions=[
                f"Raise min_triangulation_angle_deg above {p.min_triangulation_angle_deg}.",
                "Set max_landmark_distance to bound points escaping along near-parallel rays.",
            ],
            see_also="tuning.md#median_triangulation_angle-below-3",
        )

    out.note(
        f"{'LOST' if p.use_lost else 'DLT'} multi-view triangulation"
        f"{' with nonlinear refinement' if p.optimize else ''}: {len(xyz)} points "
        f"from {n_tracks_in} tracks ({yield_rate:.0%}), {len(obs_array)} "
        f"observations, mean track length {mean_length:.2f}. Mean reprojection "
        f"error {mean_error:.3f}px, median widest angle {median_angle:.2f} degrees. "
        f"Rejected {rejected['angle']} on angle, {rejected['reprojection']} on "
        f"reprojection, {rejected['cheirality']} on cheirality, "
        f"{rejected['distance']} on distance, {rejected['solve']} unsolvable."
        + (f" Refinement moved points {shift:.4f} of the scene extent (median)."
           if shift is not None else "")
    )
