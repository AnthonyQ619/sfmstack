"""SparseGlobalCOLMAP -- scene/v1 + pairwise_matches/v1 -> sparse_model/v1.

GLOMAP-style global reconstruction through pycolmap: rotation averaging, global
positioning, triangulation, bundle adjustment.

Two things make this module different from everything else here.

It consumes PAIRS, not tracks. Rotation averaging operates on relative poses
between image pairs, and a track table has already discarded that structure --
it says which observations belong together, not which pair they came from.

It estimates poses itself, so no pose module runs before it. The output is a
`sparse_model/v1`, whose pose block is filled by this module rather than copied
from an input.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import numpy as np
import pycolmap
from sfmkit import Ctx, module


def per_image_intrinsics(scene, n_images: int):
    calib = scene.load("calibration")
    K = np.asarray(calib["intrinsics"], dtype=np.float64)
    dist = np.asarray(calib["distortions"], dtype=np.float64)
    cam_index = calib.get("camera_index")
    if cam_index is None:
        cam_index = np.arange(n_images) if len(K) == n_images else np.zeros(n_images, int)
    cam_index = np.asarray(cam_index, dtype=int)
    return K[cam_index], dist[cam_index], cam_index


def keypoint_table(xy, pair_index, image_pair, feature_index, n_images):
    """Per-image keypoint arrays, plus the row each match endpoint occupies.

    COLMAP's database is keypoint-centric: a match is a pair of indices into two
    images' keypoint tables. Detector-based input already has that numbering in
    `feature_index` and it is used directly. Detector-free input has none, so every
    endpoint becomes its own keypoint -- correct, and it means a physical point
    seen in three pairs enters as three keypoints that COLMAP's own track builder
    then has to merge by geometry rather than by identity.
    """
    per_image: list[list[tuple[float, float]]] = [[] for _ in range(n_images)]
    rows = np.zeros((len(xy), 2), dtype=np.int64)

    if feature_index is not None:
        # Exact: keypoint k of image i is always row k. Sizes come from the max
        # index cited, since a keypoint no match used still occupies its slot.
        counts = np.zeros(n_images, dtype=np.int64)
        for row in range(len(xy)):
            i, j = image_pair[pair_index[row]]
            counts[i] = max(counts[i], feature_index[row, 0] + 1)
            counts[j] = max(counts[j], feature_index[row, 1] + 1)
        coords = [np.zeros((int(c), 2), dtype=np.float64) for c in counts]
        for row in range(len(xy)):
            i, j = image_pair[pair_index[row]]
            coords[i][feature_index[row, 0]] = xy[row, :2]
            coords[j][feature_index[row, 1]] = xy[row, 2:4]
            rows[row] = (feature_index[row, 0], feature_index[row, 1])
        return coords, rows

    for row in range(len(xy)):
        i, j = image_pair[pair_index[row]]
        rows[row, 0] = len(per_image[i])
        per_image[i].append((float(xy[row, 0]), float(xy[row, 1])))
        rows[row, 1] = len(per_image[j])
        per_image[j].append((float(xy[row, 2]), float(xy[row, 3])))

    coords = [
        np.asarray(pts, dtype=np.float64).reshape(-1, 2) for pts in per_image
    ]
    return coords, rows


def two_view_geometry(points_i, points_j, camera_i, camera_j, matches, p):
    """Verify one pair the way COLMAP will trust it.

    Estimated here rather than left to the pipeline because the database wants a
    verified geometry per pair, and because doing it ourselves is what lets
    `verified_pairs` be reported honestly: the gap between it and the matcher's
    `pairs_matched` is this module's own rejection, and it is the single most
    useful number when a global solve comes out short.
    """
    options = pycolmap.TwoViewGeometryOptions()
    options.ransac.max_error = p.max_epipolar_error
    options.ransac.confidence = p.verification_confidence
    options.ransac.min_inlier_ratio = p.min_inlier_ratio
    options.min_inlier_ratio = p.min_inlier_ratio
    options.min_num_inliers = p.min_num_matches

    # points are the FULL per-image keypoint tables and `matches` indexes into
    # them -- passing pre-selected points with 0..n indices silently verifies a
    # different correspondence set.
    return pycolmap.estimate_calibrated_two_view_geometry(
        camera_i, points_i, camera_j, points_j, matches, options
    )


@module
def run(ctx: Ctx):
    scene = ctx.inputs["scene"]
    matches_art = ctx.inputs["matches"]
    p = ctx.params

    names = scene.load("images", "names")
    sizes = scene.load("images", "size_current")
    n_images = len(names)

    # COLMAP reads the pixels itself to colour points, so it needs a directory and
    # a name per image that actually resolve. A scene artifact stores resized
    # copies under data/images with sequential filenames, so the scene's display
    # names do not: passing them silently produces a grey cloud.
    resolved = [scene.resolve(str(pth)) for pth in scene.load("images", "paths")]
    image_root = Path(os.path.commonpath([str(pth.parent) for pth in resolved]))
    colmap_name = [str(pth.relative_to(image_root)) for pth in resolved]

    if not scene.has("calibration"):
        out = ctx.output("sparse")
        out.diagnostic(
            "uncalibrated_scene",
            severity="error",
            message="The scene carries no intrinsics.",
            see_also="limitations.md#uncalibrated-scenes",
        )
        raise ValueError(
            "SparseGlobalCOLMAP needs intrinsics and this scene has none. Pass "
            "calibration_path to SceneLoader, or use a reconstructor that "
            "estimates them itself -- VGGT and MapAnything do."
        )

    K_all, dist_all, cam_index = per_image_intrinsics(scene, n_images)

    image_pair = np.asarray(matches_art.load("pairs", "image_pair"), dtype=np.int64)
    match_data = matches_art.load("matches")
    xy = np.asarray(match_data["xy"], dtype=np.float64)
    pair_index = np.asarray(match_data["pair_index"], dtype=np.int64)
    feature_index = match_data.get("feature_index")
    if feature_index is not None:
        feature_index = np.asarray(feature_index, dtype=np.int64)

    ctx.progress(0.05, f"{len(image_pair)} pairs, {len(xy)} matches")

    coords, rows = keypoint_table(xy, pair_index, image_pair, feature_index, n_images)

    with tempfile.TemporaryDirectory(prefix="glomap-") as tmp:
        work = Path(tmp)
        db_path = work / "database.db"
        out_dir = work / "sparse"
        out_dir.mkdir()

        verified, kept_edges = 0, []

        with pycolmap.Database.open(str(db_path)) as db:
            # One COLMAP camera per distinct calibration, not per image: global
            # positioning shares observations across cameras, and inventing N
            # identical cameras costs the solve nothing but says the scene has N
            # unknown calibrations when it has one.
            camera_of = {}
            cameras = {}
            for frame in range(n_images):
                key = int(cam_index[frame])
                if key in camera_of:
                    continue
                K, dist = K_all[frame], np.asarray(dist_all[frame]).ravel()
                camera = pycolmap.Camera()
                if np.any(dist[:4]):
                    camera.model = pycolmap.CameraModelId.OPENCV
                    params = [K[0, 0], K[1, 1], K[0, 2], K[1, 2],
                              dist[0], dist[1], dist[2], dist[3]]
                else:
                    camera.model = pycolmap.CameraModelId.PINHOLE
                    params = [K[0, 0], K[1, 1], K[0, 2], K[1, 2]]
                camera.width = int(sizes[frame][0])
                camera.height = int(sizes[frame][1])
                camera.params = np.asarray(params, dtype=np.float64)
                camera.has_prior_focal_length = True
                camera_of[key] = db.write_camera(camera)
                cameras[key] = camera

            image_id_of = {}
            for frame in range(n_images):
                image = pycolmap.Image()
                image.name = colmap_name[frame]
                image.camera_id = camera_of[int(cam_index[frame])]
                image_id_of[frame] = db.write_image(image)
                db.write_keypoints(image_id_of[frame], coords[frame].astype(np.float32))

            for pair in range(len(image_pair)):
                i, j = int(image_pair[pair, 0]), int(image_pair[pair, 1])
                sel = np.flatnonzero(pair_index == pair)
                if len(sel) < p.min_num_matches:
                    continue

                pair_matches = rows[sel].astype(np.uint32)
                db.write_matches(image_id_of[i], image_id_of[j], pair_matches)

                geometry = two_view_geometry(
                    coords[i],
                    coords[j],
                    cameras[int(cam_index[i])],
                    cameras[int(cam_index[j])],
                    pair_matches,
                    p,
                )
                if geometry is None or len(geometry.inlier_matches) < p.min_num_matches:
                    continue
                db.write_two_view_geometry(image_id_of[i], image_id_of[j], geometry)
                verified += 1
                kept_edges.append((i, j))

        if verified == 0:
            out = ctx.output("sparse")
            out.diagnostic(
                "no_verified_pairs",
                severity="error",
                message=f"None of {len(image_pair)} pairs survived verification.",
                see_also="tuning.md#verified_pairs-is-zero",
            )
            raise ValueError(
                f"no pair survived two-view verification: {len(image_pair)} "
                f"attempted, min_num_matches={p.min_num_matches}, "
                f"max_epipolar_error={p.max_epipolar_error}px at working "
                f"resolution, min_inlier_ratio={p.min_inlier_ratio}. The threshold "
                f"is in WORKING pixels -- on a heavily downscaled scene it is the "
                f"first thing to raise."
            )

        ctx.progress(0.35, f"{verified} pairs verified, running global mapping")

        options = pycolmap.GlobalPipelineOptions()
        options.min_num_matches = p.min_num_matches
        options.num_threads = p.num_threads
        options.random_seed = p.random_seed

        mapper = options.mapper
        mapper.num_threads = p.num_threads
        mapper.random_seed = p.random_seed
        mapper.track_min_num_views_per_track = p.min_track_len
        mapper.min_tri_angle_deg = p.min_tri_angle_deg
        mapper.max_angular_reproj_error_deg = p.max_angular_reproj_error_deg
        mapper.max_normalized_reproj_error = p.max_normalized_reproj_error
        mapper.ba_num_iterations = p.ba_num_iterations
        mapper.global_positioning.random_seed = p.random_seed
        mapper.global_positioning.min_num_view_per_track = p.min_track_len

        ba = mapper.bundle_adjustment
        ba.refine_focal_length = p.refine_focal_length
        ba.refine_principal_point = p.refine_principal_point
        ba.refine_extra_params = False  # observations are undistorted by the model
        ba.min_track_length = p.min_track_len
        if p.num_threads > 0:
            ba.ceres.solver_options.num_threads = p.num_threads

        models = pycolmap.global_mapping(
            database_path=db_path,
            image_path=image_root,
            output_path=out_dir,
            options=options,
        )

        if not models:
            raise ValueError(
                f"global mapping produced no reconstruction from {verified} "
                f"verified pairs. Rotation averaging needs a connected graph: "
                f"check the matcher's graph_components, and raise min_num_matches "
                f"only after confirming the graph is whole."
            )

        # Largest by registered images. Several models means the graph split, and
        # only one can be returned -- the others' images come back valid=False,
        # with a diagnostic saying so rather than silently.
        rec = max(models.values(), key=lambda r: r.num_reg_images())

    ctx.progress(0.8, f"{rec.num_reg_images()} cameras, {rec.num_points3D()} points")

    rec.update_point_3d_errors()  # COLMAP leaves per-point error unset until asked

    frame_of_name = {colmap_name[f]: f for f in range(n_images)}
    frame_of_image_id = {}
    for image_id, image in rec.images.items():
        frame = frame_of_name.get(str(image.name))
        if frame is not None:
            frame_of_image_id[image_id] = frame

    cam_from_world = np.tile(
        np.hstack([np.eye(3), np.zeros((3, 1))]), (n_images, 1, 1)
    )
    valid = np.zeros(n_images, dtype=bool)
    for image_id, frame in frame_of_image_id.items():
        image = rec.image(image_id)
        if not image.has_pose:
            continue
        pose = image.cam_from_world()
        cam_from_world[frame] = np.hstack(
            [pose.rotation.matrix(), pose.translation.reshape(3, 1)]
        )
        valid[frame] = True

    point_ids = sorted(rec.points3D)
    index_of = {pid: k for k, pid in enumerate(point_ids)}
    xyz = np.array([rec.point3D(pid).xyz for pid in point_ids], dtype=np.float64)
    rgb = np.array([rec.point3D(pid).color for pid in point_ids], dtype=np.uint8)
    error = np.array([rec.point3D(pid).error for pid in point_ids], dtype=np.float64)

    obs_rows = []
    for pid in point_ids:
        for element in rec.point3D(pid).track.elements:
            frame = frame_of_image_id.get(element.image_id)
            if frame is None:
                continue
            point2d = rec.image(element.image_id).point2D(element.point2D_idx)
            obs_rows.append([frame, index_of[pid], float(point2d.xy[0]), float(point2d.xy[1])])
    obs = np.array(obs_rows, dtype=np.float64).reshape(-1, 4)

    refined_K = np.zeros((n_images, 3, 3), dtype=np.float64)
    for frame in range(n_images):
        refined_K[frame] = K_all[frame]
    for image_id, frame in frame_of_image_id.items():
        params = rec.camera(rec.image(image_id).camera_id).params
        refined_K[frame] = np.array(
            [[params[0], 0.0, params[2]], [0.0, params[1], params[3]], [0, 0, 1.0]]
        )

    out = ctx.output("sparse")
    out.save("points", xyz=xyz, rgb=rgb, error=error)
    out.save("observations", obs=obs)
    out.save(
        "poses",
        cam_from_world=cam_from_world,
        valid=valid,
        image_index=np.arange(n_images, dtype=np.int32),
    )
    # The solve may refine intrinsics, so the model carries its own rather than
    # letting a downstream module read the scene's and disagree with the poses.
    out.save("intrinsics", K=refined_K, camera_index=np.arange(n_images, dtype=np.int32))
    rec.write_binary(str(out.sidecar_dir("colmap")))

    registered = int(valid.sum())
    mean_error = float(rec.compute_mean_reprojection_error())
    track_length = len(obs) / len(point_ids) if len(point_ids) else 0.0

    parent = list(range(n_images))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i, j in kept_edges:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[rj] = ri
    roots = [find(i) for i in range(n_images)]
    biggest = max(roots.count(r) for r in set(roots))

    out.metric("point_count", len(point_ids),
               direction="higher_better", healthy=(100, None))
    out.metric("observation_count", len(obs),
               direction="higher_better", healthy=(300, None))
    out.metric("mean_track_length", round(track_length, 3),
               direction="higher_better", healthy=(3.0, None))
    out.metric("mean_reprojection_error", round(mean_error, 4),
               direction="lower_better", healthy=(None, 2.0))
    out.metric("registered_fraction", round(registered / n_images, 3),
               direction="higher_better", healthy=(0.9, None))
    out.metric("registered_images", registered,
               direction="higher_better", healthy=(3, None))
    out.metric("verified_pairs", verified,
               direction="higher_better", healthy=(1, None))
    out.metric("largest_component_fraction", round(biggest / n_images, 3),
               direction="higher_better", healthy=(1.0, None))
    out.metric("models_found", len(models), direction="neutral")

    if verified < 0.7 * len(image_pair):
        out.diagnostic(
            "graph_thinned_by_verification",
            severity="warn",
            message=(
                f"Verification kept {verified} of {len(image_pair)} pairs "
                f"({verified / max(len(image_pair), 1):.0%})."
            ),
            suggested_actions=[
                f"Raise max_epipolar_error above {p.max_epipolar_error} "
                f"(working-resolution pixels).",
                "Check the matcher's planarity; degenerate pairs fail correctly.",
            ],
            see_also="tuning.md#verified_pairs-far-below-pairs_matched",
        )

    if registered < n_images:
        missing = [str(names[f]) for f in range(n_images) if not valid[f]]
        out.diagnostic(
            "partial_registration",
            severity="warn",
            message=(
                f"{len(missing)} of {n_images} images were not placed: "
                f"{missing[:5]}."
            ),
            suggested_actions=[
                "Check largest_component_fraction; a split graph cannot be one model.",
                "Widen the matcher's window, or use pairing: exhaustive.",
            ],
            see_also="limitations.md#what-global-cannot-recover-from",
        )

    if len(models) > 1:
        sizes_found = sorted((r.num_reg_images() for r in models.values()), reverse=True)
        out.diagnostic(
            "split_into_models",
            severity="warn",
            message=f"{len(models)} reconstructions of sizes {sizes_found}; largest returned.",
            suggested_actions=[
                "The scene has disconnected components; link them in the matcher.",
                "Or reconstruct each component as its own scene.",
            ],
            see_also="limitations.md#what-global-cannot-recover-from",
        )

    if mean_error > 2.0:
        out.diagnostic(
            "high_reprojection_error",
            severity="warn",
            message=f"Mean reprojection error is {mean_error:.2f}px.",
            suggested_actions=[
                f"Raise ba_num_iterations above {p.ba_num_iterations}.",
                f"Raise min_num_matches above {p.min_num_matches} so thin pairs "
                f"stop feeding rotation averaging.",
            ],
            see_also="tuning.md#mean_reprojection_error-above-2",
        )

    out.note(
        f"Global reconstruction: {verified} of {len(image_pair)} pairs survived "
        f"two-view verification, {registered}/{n_images} cameras placed, "
        f"{len(point_ids)} points from {len(obs)} observations "
        f"(mean track length {track_length:.2f}). Mean reprojection error "
        f"{mean_error:.3f}px at working resolution. Poses were estimated HERE -- "
        f"no pose module ran before this, and none needs to run after it."
    )
