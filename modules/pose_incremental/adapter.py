"""PoseEssentialToPnP -- scene/v1 + tracks/v1 -> poses/v1.

Incremental structure-from-motion: essential-matrix bootstrap, then repeated PnP
registration against triangulated structure.

Geometry is done in NORMALISED camera coordinates throughout -- observations are
undistorted and premultiplied by K^-1 once, up front. That is what lets a scene
with per-image intrinsics (a mixed-resolution capture, or a multi-camera rig) work
without special-casing: the projection matrices are plain [R|t] and no K appears
again until reprojection error is reported, where it has to be in pixels.

Registration is interleaved with LOCAL bundle adjustment over a sliding window of
the most recently registered cameras (`local_ba`). Without it, every pose is
estimated against structure triangulated from poses that were themselves never
revised, so error compounds along the registration order -- the failure mode is a
model whose reprojection error looks acceptable everywhere locally and whose
cameras have drifted badly end to end.
"""

from __future__ import annotations

import cv2
import numpy as np
from sfmkit import Ctx, module

try:
    import pycolmap
except ImportError:  # local_ba: false still works without it
    pycolmap = None

DEG = 180.0 / np.pi

# pycolmap needs two fixed cameras to pin the 7-dof gauge. The predecessor fixed
# exactly one, which leaves scale free inside the window: each solve was then free
# to rescale the local structure relative to the model it was being written back
# into, which is a drift source rather than a drift fix.
MIN_FIXED = 2


def per_image_intrinsics(scene, n_images: int):
    """K and distortion for every image, whatever shape the calibration took."""
    calib = scene.load("calibration")
    K = np.asarray(calib["intrinsics"], dtype=np.float64)
    dist = np.asarray(calib["distortions"], dtype=np.float64)
    cam_index = calib.get("camera_index")

    if cam_index is None:
        # One camera per image, or one shared camera broadcast across the set.
        cam_index = np.arange(n_images) if len(K) == n_images else np.zeros(n_images, int)
    cam_index = np.asarray(cam_index, dtype=int)

    return K[cam_index], dist[cam_index]


def observations_by_frame(obs: np.ndarray, n_images: int, min_len: int):
    """Reorganise the flat observation table into per-frame lookups.

    Returns (frame -> track ids, frame -> pixel xy, track -> frame list). The
    tracks type is a flat table because that is what bundle adjustment wants;
    incremental registration wants it indexed both ways, and building both once
    is far cheaper than searching the table per image.
    """
    track_id = obs[:, 0].astype(np.int64)
    frame = obs[:, 1].astype(np.int64)

    lengths = np.bincount(track_id)
    keep = lengths[track_id] >= min_len
    track_id, frame, xy = track_id[keep], frame[keep], obs[keep, 2:4]

    order = np.lexsort((track_id, frame))
    track_id, frame, xy = track_id[order], frame[order], xy[order]

    bounds = np.searchsorted(frame, np.arange(n_images + 1))
    tracks_in = [track_id[bounds[i] : bounds[i + 1]] for i in range(n_images)]
    points_in = [xy[bounds[i] : bounds[i + 1]] for i in range(n_images)]

    frames_of: dict[int, list[int]] = {}
    for f, t in zip(frame, track_id):
        frames_of.setdefault(int(t), []).append(int(f))

    return tracks_in, points_in, frames_of


def normalise(points: np.ndarray, K: np.ndarray, dist: np.ndarray) -> np.ndarray:
    """Pixels -> undistorted normalised camera coordinates."""
    if len(points) == 0:
        return points.reshape(0, 2).astype(np.float64)
    p = np.ascontiguousarray(points, dtype=np.float64).reshape(-1, 1, 2)
    return cv2.undistortPoints(p, K, dist.reshape(1, -1)).reshape(-1, 2)


def shared(a_tracks, b_tracks):
    """Track ids present in both frames, with their row in each."""
    common, ia, ib = np.intersect1d(a_tracks, b_tracks, return_indices=True)
    return common, ia, ib


def triangulate(P1, P2, x1, x2):
    """DLT triangulation in normalised coordinates. Returns (N, 3)."""
    X = cv2.triangulatePoints(P1, P2, x1.T, x2.T)
    with np.errstate(invalid="ignore", divide="ignore"):
        return (X[:3] / X[3]).T


def ray_angles(centers_a, centers_b, points):
    """Angle at each 3D point between the rays from two camera centres."""
    va = points - centers_a
    vb = points - centers_b
    na = np.linalg.norm(va, axis=1)
    nb = np.linalg.norm(vb, axis=1)
    good = (na > 1e-12) & (nb > 1e-12)
    cos = np.ones(len(points))
    cos[good] = np.einsum("ij,ij->i", va[good], vb[good]) / (na[good] * nb[good])
    return np.arccos(np.clip(cos, -1.0, 1.0)) * DEG


def camera_center(pose):
    return -pose[:, :3].T @ pose[:, 3]


def project(pose, K, points):
    """Normalised-frame projection to pixels. Returns (xy, in_front)."""
    cam = points @ pose[:, :3].T + pose[:, 3]
    z = cam[:, 2]
    in_front = z > 1e-8
    with np.errstate(invalid="ignore", divide="ignore"):
        normalised = cam[:, :2] / z[:, None]
    pix = normalised @ K[:2, :2].T + K[:2, 2]
    return pix, in_front


class Reconstruction:
    """Poses and points, with the bookkeeping that keeps them consistent."""

    def __init__(self, n_images: int):
        self.poses: dict[int, np.ndarray] = {}
        self.points: dict[int, np.ndarray] = {}  # track id -> xyz
        self.n_images = n_images

    @property
    def registered(self) -> list[int]:
        return sorted(self.poses)

    def center(self, frame: int) -> np.ndarray:
        return camera_center(self.poses[frame])


def _termination_name(termination) -> str:
    """'TerminationType.NO_CONVERGENCE' / an enum / a bare string -> 'NO_CONVERGENCE'."""
    name = getattr(termination, "name", None)
    if isinstance(name, str):
        return name.upper()
    return str(termination).rsplit(".", 1)[-1].upper()


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
    # of iterations.
    converged = termination is not None and _termination_name(termination) == "CONVERGENCE"
    if termination is None and getattr(summary, "is_solution_usable", None):
        converged = bool(summary.is_solution_usable())
    return iterations, converged


def bundle_adjust_window(rec, window, *, K_all, undist_in, tracks_in, row_of,
                         sizes, names, min_track_len, max_iterations, robust_loss,
                         loss_scale):
    """Refine the cameras in `window` and the structure they see, in place.

    `window` is in REGISTRATION order and its first MIN_FIXED entries are held
    constant, which both pins the gauge and keeps the refined block attached to the
    part of the model that is not in the solve. Only the window is put into the
    pycolmap reconstruction: observations from cameras outside it would anchor the
    points better, but the whole point of a local solve is that its cost does not
    grow with the model.

    Returns (error_before, error_after, iterations, converged) in pixels, or None
    if the window carried too little structure to solve.
    """
    if len(window) <= MIN_FIXED:
        return None

    image_id_of = {frame: i + 1 for i, frame in enumerate(window)}
    sub = pycolmap.Reconstruction()
    elements: dict[int, list[tuple[int, int]]] = {}

    for frame in window:
        image_id = image_id_of[frame]
        K = K_all[frame]
        camera = pycolmap.Camera.create_from_model_id(
            camera_id=image_id,
            model=pycolmap.CameraModelId.PINHOLE,
            focal_length=float(K[0, 0]),
            width=int(sizes[frame][0]),
            height=int(sizes[frame][1]),
        )
        camera.params = [float(K[0, 0]), float(K[1, 1]), float(K[0, 2]), float(K[1, 2])]
        sub.add_camera_with_trivial_rig(camera)

        points2D, seen = [], []
        for track in tracks_in[frame]:
            track = int(track)
            if track not in rec.points:
                continue
            elements.setdefault(track, []).append((image_id, len(points2D)))
            points2D.append(pycolmap.Point2D(undist_in[frame][row_of[frame][track]]))
            seen.append(track)

        image = pycolmap.Image(name=str(names[frame]), camera_id=image_id, points2D=points2D)
        image.image_id = image_id
        P = rec.poses[frame]
        sub.add_image_with_trivial_frame(
            image, pycolmap.Rigid3d(pycolmap.Rotation3d(P[:, :3]), P[:, 3])
        )

    point_id_of: dict[int, int] = {}
    for track, obs in elements.items():
        if len(obs) < max(min_track_len, 2):
            continue
        point_id_of[track] = sub.add_point3D(
            rec.points[track],
            pycolmap.Track([pycolmap.TrackElement(i, j) for i, j in obs]),
            np.array([128, 128, 128], dtype=np.uint8),
        )

    if len(point_id_of) < 8:
        return None

    sub.update_point_3d_errors()  # COLMAP leaves per-point error unset until asked
    before = float(sub.compute_mean_reprojection_error())

    config = pycolmap.BundleAdjustmentConfig()
    for image_id in image_id_of.values():
        config.add_image(image_id)
    for frame in window[:MIN_FIXED]:
        config.set_constant_rig_from_world_pose(image_id_of[frame])

    options = pycolmap.BundleAdjustmentOptions()
    options.refine_focal_length = False
    options.refine_principal_point = False
    options.refine_extra_params = False
    options.refine_points3D = True
    options.refine_rig_from_world = True
    options.ceres.solver_options.max_num_iterations = int(max_iterations)
    if robust_loss:
        options.ceres.loss_function_type = pycolmap.LossFunctionType.CAUCHY
        options.ceres.loss_function_scale = float(loss_scale)
    else:
        options.ceres.loss_function_type = pycolmap.LossFunctionType.TRIVIAL

    summary = pycolmap.create_default_bundle_adjuster(options, config, sub).solve()

    sub.update_point_3d_errors()
    after = float(sub.compute_mean_reprojection_error())
    iterations, converged = read_summary(summary)

    # Write back. The fixed cameras did not move, so skipping them is not an
    # optimisation -- reading their pose back would round-trip a float for nothing.
    for frame in window[MIN_FIXED:]:
        pose = sub.image(image_id_of[frame]).cam_from_world()
        rec.poses[frame] = np.hstack(
            [pose.rotation.matrix(), pose.translation.reshape(3, 1)]
        )
    # Structure has to be written back too: the next PnP registers against these
    # points, and refining poses against stale structure undoes the solve.
    for track, point_id in point_id_of.items():
        rec.points[track] = np.asarray(sub.point3D(point_id).xyz, dtype=np.float64)

    return before, after, iterations, converged


@module
def run(ctx: Ctx):
    scene = ctx.inputs["scene"]
    tracks = ctx.inputs["tracks"]
    p = ctx.params

    names = scene.load("images", "names")
    sizes = scene.load("images", "size_current")
    n_images = len(names)

    if p.local_ba and pycolmap is None:
        raise ValueError(
            "local_ba is on and pycolmap is not importable. Either install it "
            "(`pip install pycolmap`) or set local_ba: false and run the "
            "BundleAdjustmentLocal module afterwards instead."
        )

    if not scene.has("calibration"):
        out = ctx.output("poses")
        out.diagnostic(
            "uncalibrated_scene",
            severity="error",
            message="The scene carries no intrinsics.",
            see_also="limitations.md#uncalibrated-scenes",
        )
        raise ValueError(
            "PoseEssentialToPnP needs intrinsics and this scene has none. Pass "
            "calibration_path to SceneLoader, or use a pose estimator that "
            "estimates intrinsics itself -- VGGT and MapAnything do, and in fact "
            "do better without a supplied K."
        )

    K_all, dist_all = per_image_intrinsics(scene, n_images)
    obs = tracks.load("observations", "obs")
    n_tracks_in = int(tracks.load("observations", "track_count"))

    tracks_in, pixels_in, frames_of = observations_by_frame(obs, n_images, p.min_track_len)
    # Undistorted pixels are what reprojection error is measured against; the
    # raw ones carry lens distortion that the geometry has already removed.
    normal_in, undist_in = [], []
    for i in range(n_images):
        nrm = normalise(pixels_in[i], K_all[i], dist_all[i])
        normal_in.append(nrm)
        undist_in.append(nrm @ K_all[i][:2, :2].T + K_all[i][:2, 2])

    # Row of each track within each frame's arrays, so an observation can be
    # found in O(1) during registration rather than by searching.
    row_of = [
        {int(t): r for r, t in enumerate(tracks_in[i])} for i in range(n_images)
    ]

    rec = Reconstruction(n_images)

    # ----------------------------------------------------------------- seed
    ctx.progress(0.05, "choosing an initial pair")

    best = None
    candidates = [
        (i, j)
        for i in range(n_images)
        for j in range(i + 1, n_images)
        if len(tracks_in[i]) and len(tracks_in[j])
    ]

    for i, j in candidates:
        common, ia, ib = shared(tracks_in[i], tracks_in[j])
        if len(common) < max(p.min_pnp_inliers, 8):
            continue

        x1, x2 = normal_in[i][ia], normal_in[j][ib]
        E, mask = cv2.findEssentialMat(
            x1, x2, np.eye(3), method=cv2.USAC_MAGSAC,
            prob=p.confidence, threshold=p.pnp_reprojection_error / K_all[i][0, 0],
            maxIters=p.max_iterations,
        )
        if E is None or mask is None or E.shape != (3, 3):
            continue

        inlier = mask.ravel().astype(bool)
        if inlier.sum() < max(p.min_pnp_inliers, 8):
            continue

        n_good, R, t, _ = cv2.recoverPose(E, x1[inlier], x2[inlier], np.eye(3))
        if n_good < max(p.min_pnp_inliers, 8):
            continue

        P0 = np.hstack([np.eye(3), np.zeros((3, 1))])
        P1 = np.hstack([R, t.reshape(3, 1)])
        X = triangulate(P0, P1, x1[inlier], x2[inlier])
        finite = np.isfinite(X).all(axis=1)
        if finite.sum() < max(p.min_pnp_inliers, 8):
            continue

        X = X[finite]
        angles = ray_angles(camera_center(P0), camera_center(P1), X)
        median_angle = float(np.median(angles))

        # Score by inlier count gated on parallax, not by either alone: the pair
        # with the most matches is usually the pair with the least baseline, and
        # seeding there is the classic way to produce a confident wrong model.
        if median_angle < p.init_min_angle_deg:
            continue
        score = int(inlier.sum()) * median_angle
        if best is None or score > best[0]:
            best = (score, i, j, R, t.reshape(3), median_angle)

    if best is None:
        out = ctx.output("poses")
        out.diagnostic(
            "no_viable_initial_pair",
            severity="error",
            message=f"No pair of {n_images} images reached {p.init_min_angle_deg} degrees of parallax.",
            see_also="limitations.md#degenerate-captures",
        )
        raise ValueError(
            f"no pair of the {n_images} images had both {p.min_pnp_inliers}+ shared "
            f"tracks and {p.init_min_angle_deg} degrees of median parallax. Check the "
            f"matcher's `planarity` metric -- a planar or rotation-only capture "
            f"cannot seed an incremental reconstruction at all. If the capture does "
            f"have baseline, widen the matcher's PAIRING so more pairs are candidates -- "
            f"`window` only does this under sequential pairing; under exhaustive "
            f"every pair already exists and the dial is min_matches instead."
        )

    _, i0, j0, R, t, init_angle = best

    rec.poses[i0] = np.hstack([np.eye(3), np.zeros((3, 1))])
    rec.poses[j0] = np.hstack([R, t.reshape(3, 1)])

    ctx.progress(0.15, f"seeded on ({i0}, {j0}) at {init_angle:.1f} deg parallax")

    # ------------------------------------------------------- grow the model
    def triangulate_new():
        """Triangulate every track visible in 2+ registered frames without a point."""
        added = 0
        for track, frames in frames_of.items():
            if track in rec.points:
                continue
            seen = [f for f in frames if f in rec.poses]
            if len(seen) < 2:
                continue

            # Widest baseline available for this track, which is the pair that
            # conditions the depth best.
            centers = {f: rec.center(f) for f in seen}
            pair, span = None, -1.0
            for a in range(len(seen) - 1):
                for b in range(a + 1, len(seen)):
                    d = float(np.linalg.norm(centers[seen[a]] - centers[seen[b]]))
                    if d > span:
                        span, pair = d, (seen[a], seen[b])
            if pair is None or span < 1e-9:
                continue

            f1, f2 = pair
            x1 = normal_in[f1][row_of[f1][track]].reshape(1, 2)
            x2 = normal_in[f2][row_of[f2][track]].reshape(1, 2)
            X = triangulate(rec.poses[f1], rec.poses[f2], x1, x2)[0]
            if not np.isfinite(X).all():
                continue

            angle = ray_angles(centers[f1][None], centers[f2][None], X[None])[0]
            if angle < p.min_triangulation_angle_deg:
                continue

            # Cheirality and reprojection, checked in every registered view.
            ok = True
            for f in seen:
                pix, in_front = project(rec.poses[f], K_all[f], X[None])
                if not in_front[0]:
                    ok = False
                    break
                err = np.linalg.norm(pix[0] - undist_in[f][row_of[f][track]])
                if err > p.max_reprojection_error:
                    ok = False
                    break
            if ok:
                rec.points[track] = X
                added += 1
        return added

    triangulate_new()

    # ------------------------------------------------------------- local BA
    # Registration ORDER, not frame order. The predecessor took the window to be
    # frames [id-N, id] because it registered strictly in file order; here the next
    # image is whichever has the most 2D-3D links, so frame index says nothing about
    # what was solved recently and a frame-indexed window would fix cameras that had
    # just moved.
    order: list[int] = [i0, j0]
    ba_runs, ba_gains, ba_iterations, ba_failures = 0, [], 0, 0

    def refine():
        nonlocal ba_runs, ba_iterations, ba_failures
        if not p.local_ba:
            return
        n = len(order)
        # Every registration while the model is small -- that is where a bad pose
        # does the most damage, because everything after it is registered against
        # structure it triangulated -- then every local_ba_interval.
        if n > p.local_ba_warmup and n % p.local_ba_interval != 0:
            return
        result = bundle_adjust_window(
            rec, order[-p.local_ba_window :],
            K_all=K_all, undist_in=undist_in, tracks_in=tracks_in, row_of=row_of,
            sizes=sizes, names=names, min_track_len=p.min_track_len,
            max_iterations=p.local_ba_max_iterations,
            robust_loss=p.local_ba_robust_loss, loss_scale=p.local_ba_loss_scale,
        )
        if result is None:
            return
        before, after, iterations, converged = result
        ba_runs += 1
        ba_gains.append(before - after)
        ba_iterations += iterations
        if not converged:
            ba_failures += 1

    refine()

    # Images PnP has already refused. Kept separate from `rec.poses` rather than
    # parked there as a None: everything that walks the pose dict -- triangulation,
    # camera centres, reprojection -- assumes every entry is a real 3x4.
    refused: set[int] = set()

    while len(rec.poses) + len(refused) < n_images:
        # Register whichever unregistered image has the most 2D-3D links.
        candidate, best_count = None, 0
        for f in range(n_images):
            if f in rec.poses or f in refused:
                continue
            count = sum(1 for t in tracks_in[f] if int(t) in rec.points)
            if count > best_count:
                candidate, best_count = f, count

        if candidate is None or best_count < p.min_pnp_inliers:
            break

        f = candidate
        ids = [int(t) for t in tracks_in[f] if int(t) in rec.points]
        object_points = np.array([rec.points[t] for t in ids], dtype=np.float64)
        image_points = np.array(
            [normal_in[f][row_of[f][t]] for t in ids], dtype=np.float64
        )

        ok, rvec, tvec, inliers = cv2.solvePnPRansac(
            object_points,
            image_points,
            np.eye(3),
            np.zeros(5),
            reprojectionError=p.pnp_reprojection_error / K_all[f][0, 0],
            iterationsCount=p.max_iterations,
            confidence=p.confidence,
            flags=cv2.SOLVEPNP_SQPNP,
        )
        if not ok or inliers is None or len(inliers) < p.min_pnp_inliers:
            # Refuse it permanently, or the loop re-picks the same image forever.
            refused.add(f)
            continue

        idx = inliers.ravel()
        rvec, tvec = cv2.solvePnPRefineLM(
            object_points[idx], image_points[idx], np.eye(3), np.zeros(5), rvec, tvec
        )
        rec.poses[f] = np.hstack([cv2.Rodrigues(rvec)[0], tvec.reshape(3, 1)])
        order.append(f)

        ctx.progress(
            0.15 + 0.75 * len(rec.poses) / n_images,
            f"registered {len(rec.poses)}/{n_images}, {len(rec.points)} points",
        )
        # A new view can make previously untriangulable tracks viable, and can
        # give an existing one a wider baseline. Points are never re-triangulated
        # once accepted; local BA is what revises them.
        triangulate_new()
        refine()

    # ------------------------------------------------------------- finalise
    ctx.progress(0.92, "filtering structure")

    errors, angles_final = [], []
    for track, X in list(rec.points.items()):
        seen = [f for f in frames_of[track] if f in rec.poses]
        if len(seen) < 2:
            del rec.points[track]
            continue
        per_view = []
        for f in seen:
            pix, in_front = project(rec.poses[f], K_all[f], X[None])
            if not in_front[0]:
                per_view = None
                break
            per_view.append(float(np.linalg.norm(pix[0] - undist_in[f][row_of[f][track]])))
        if per_view is None or max(per_view) > p.max_reprojection_error:
            del rec.points[track]
            continue

        # Widest angle any pair of observing views subtends at this point. The
        # widest, not the mean: one well-separated pair conditions the depth, and
        # averaging it against a cluster of near-coincident views hides that.
        centers = np.array([rec.center(f) for f in seen])
        a, b = np.triu_indices(len(seen), k=1)
        widest = float(ray_angles(centers[a], centers[b], np.tile(X, (len(a), 1))).max())

        errors.extend(per_view)
        angles_final.append(widest)

    registered = sorted(rec.poses)
    if len(registered) < 2:
        raise ValueError(
            f"only {len(registered)} image(s) registered, which is not a "
            f"reconstruction. The seed pair was ({i0}, {j0}); growth stopped "
            f"because no unregistered image reached min_pnp_inliers="
            f"{p.min_pnp_inliers} 2D-3D correspondences. Check the tracker's "
            f"long_track_fraction -- two-view tracks cannot register a third image."
        )

    cam_from_world = np.zeros((n_images, 3, 4), dtype=np.float64)
    valid = np.zeros(n_images, dtype=bool)
    for f in registered:
        cam_from_world[f] = rec.poses[f]
        valid[f] = True
    cam_from_world[~valid] = np.hstack([np.eye(3), np.zeros((3, 1))])

    out = ctx.output("poses")
    out.save(
        "poses",
        cam_from_world=cam_from_world,
        valid=valid,
        image_index=np.arange(n_images, dtype=np.int32),
    )

    frac = len(registered) / n_images
    mean_err = float(np.mean(errors)) if errors else float("nan")
    # The mean/median pair separates a few bad observations from a systematically
    # wrong model: mean well above median is outliers, the two together is neither.
    median_err = float(np.median(errors)) if errors else float("nan")
    median_angle = float(np.median(angles_final)) if angles_final else 0.0
    utilisation = len(rec.points) / max(n_tracks_in, 1)

    out.metric("registered_fraction", round(frac, 3),
               direction="higher_better", healthy=(0.9, None))
    out.metric("registered_images", len(registered),
               direction="higher_better", healthy=(3, None))
    out.metric("points_triangulated", len(rec.points),
               direction="higher_better", healthy=(100, None))
    out.metric("mean_reprojection_error", round(mean_err, 3) if errors else None,
               direction="lower_better", healthy=(None, 2.0))
    out.metric("median_reprojection_error", round(median_err, 3) if errors else None,
               direction="lower_better", healthy=(None, 2.0))
    out.metric("median_triangulation_angle", round(median_angle, 2),
               direction="higher_better", healthy=(3.0, None))
    out.metric("track_utilization", round(utilisation, 3),
               direction="higher_better", healthy=(0.3, None))
    out.metric("init_pair_angle", round(float(init_angle), 2),
               direction="higher_better", healthy=(4.0, None))

    mean_gain = float(np.mean(ba_gains)) if ba_gains else None
    # A window solve that diverges produces a gain of ~1e150, which is not a
    # measurement. Publishing it as one put a 150-digit float into an artifact
    # note and an info-severity diagnostic whose first action was "nothing"; six
    # captures hit it through five unrelated parameters. The bound is deliberately
    # loose -- anything past a thousand pixels on a scene whose images are ~1e3 px
    # across is a solver failure, not a bad model.
    ba_diverged = mean_gain is not None and not (abs(mean_gain) < 1e3)
    if ba_diverged:
        mean_gain = None
    out.metric("local_ba_runs", ba_runs, direction="neutral")
    out.metric("local_ba_gain_px", round(mean_gain, 4) if mean_gain is not None else None,
               direction="higher_better", healthy=(0.0, None))

    if frac < 1.0:
        missing = [int(f) for f in range(n_images) if not valid[f]]
        out.diagnostic(
            "partial_registration",
            severity="warn",
            message=(
                f"{len(missing)} of {n_images} images could not be registered: "
                f"{[str(names[m]) for m in missing[:5]]}."
            ),
            suggested_actions=[
                "Check the tracker's min_frame_observations for those frames.",
                "Link those frames to more neighbours at the matcher -- under "
                "sequential pairing that is `window`; under exhaustive the pairs "
                "already exist and were dropped, so the dial is min_matches.",
            ],
            see_also="tuning.md#registered_fraction-below-10",
        )

    if errors and mean_err > 2.0:
        out.diagnostic(
            "high_reprojection_error",
            severity="warn",
            message=f"Mean reprojection error is {mean_err:.2f}px at working resolution.",
            suggested_actions=[
                f"Raise min_triangulation_angle_deg above {p.min_triangulation_angle_deg}.",
                "Run bundle adjustment; this module does not refine globally.",
            ],
            see_also="tuning.md#mean_reprojection_error-above-2",
        )

    if median_angle < 3.0:
        out.diagnostic(
            "weak_structure",
            severity="warn",
            message=f"Median triangulation angle is {median_angle:.2f} degrees.",
            suggested_actions=[
                "Raise min_triangulation_angle_deg.",
                "Widen the capture baseline; no parameter recovers missing parallax.",
            ],
            see_also="limitations.md#degenerate-captures",
        )

    if ba_diverged:
        out.diagnostic(
            "local_ba_diverged",
            severity="error",
            message=(
                f"A local bundle-adjustment solve diverged: window error moved by "
                f"a non-finite or absurd amount over {ba_runs} solves. The poses "
                f"above are not trustworthy."
            ),
            suggested_actions=[
                "Exclude under-constrained points from the window: raise "
                "min_triangulation_angle_deg, or min_track_len to 3. A two-view "
                "track and a near-parallel point are the same defect here and "
                "both were measured causing this.",
                "Do NOT read local_ba_gain_px on this run; it is suppressed.",
                "If it persists, set local_ba: false to get a usable model and "
                "report the configuration.",
            ],
            see_also="tuning.md#local-ba-diverged",
        )
    elif ba_failures:
        # Gated on whether non-convergence is CONSEQUENTIAL. Hitting the cap is a
        # Ceres termination condition, not a statement about the model: forcing
        # convergence by raising the cap eightfold converted solves and moved no
        # published metric at all. It matters only when the window still has real
        # drift to remove, which is what a gain large relative to the residual says.
        consequential = (
            mean_gain is not None and errors
            and mean_gain > 0.25 * mean_err
        )
        out.diagnostic(
            "local_ba_not_converging",
            severity="warn" if consequential else "info",
            message=(
                f"{ba_failures} of {ba_runs} local solves hit the "
                f"{p.local_ba_max_iterations}-iteration cap without converging"
                + (
                    ", and the window still has drift to remove."
                    if consequential else
                    f", but the window is already consistent (gain "
                    f"{mean_gain:+.4f}px against {mean_err:.3f}px of residual), so "
                    f"this is expected and costs nothing."
                )
            ),
            suggested_actions=(
                [
                    "Check local_ba_loss_scale FIRST: a scale far above the "
                    "residuals leaves the robust loss disengaged, and it is the "
                    "only one of these knobs measured to improve anything.",
                    "Raise local_ba_max_iterations only if the gain is large; "
                    "where it is not, this was measured to buy nothing at 8x cost.",
                    "On a set at or below local_ba_window, WIDEN the window to the "
                    "image count rather than narrowing it -- narrowing was measured "
                    "strictly harmful there.",
                ] if consequential else
                ["Nothing. Converging these solves was measured to change no "
                 "published metric; see tuning.md."]
            ),
            see_also="tuning.md#local-ba-is-not-converging",
        )

    if ba_runs and mean_gain is not None and mean_gain <= 0.0:
        out.diagnostic(
            "local_ba_not_helping",
            severity="info",
            message=(
                f"Local BA moved window error by {mean_gain:+.4f}px on average "
                f"over {ba_runs} solves."
            ),
            suggested_actions=[
                "Nothing, if reprojection error is already low -- there is no drift to remove.",
                "With robust_loss on, the robust cost can fall while the raw mean rises.",
                "Set local_ba: false if the runtime is not worth it for this stack.",
                "This metric is NOT comparable across local_ba_window settings, and "
                "it does not rank local_ba_loss_scale settings: it rose monotonically "
                "through the point where the model started getting worse. Judge those "
                "two on median_reprojection_error instead.",
            ],
            see_also="tuning.md#local_ba_gain_px-at-or-below-zero",
        )

    ba_note = (
        f"Local BA ran {ba_runs} times over a {p.local_ba_window}-camera window "
        f"({ba_iterations} Ceres iterations total), moving window reprojection "
        f"error by {mean_gain:+.3f}px per solve on average. "
        if ba_runs else
        ("Local BA was enabled but never had a window with enough structure to solve. "
         if p.local_ba else
         "Local BA was disabled; poses were never revised after registration, so "
         "error compounds along the registration order. ")
    )

    out.note(
        ba_note +
        f"Seeded on images ({i0}, {j0}) at {init_angle:.1f} degrees median parallax. "
        f"Registered {len(registered)}/{n_images} images and kept {len(rec.points)} "
        f"of {n_tracks_in} tracks as 3D points ({utilisation:.0%}). "
        f"Mean reprojection error {mean_err:.2f}px, median triangulation angle "
        f"{median_angle:.2f} degrees. Scale is arbitrary: the seed pair's baseline "
        f"is unit length."
    )
