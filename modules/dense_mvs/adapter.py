"""DenseMVS -- scene/v1 + sparse_model/v1 -> dense_model/v1.

COLMAP PatchMatch stereo followed by depth-map fusion, via pycolmap built with
CUDA.

The module is a workspace-building exercise. COLMAP's MVS stack does not take
arrays; it takes a directory laid out its way -- undistorted images, a binary
reconstruction, and a stereo folder it fills in -- so most of what follows exists
to turn our artifacts into that directory and the result back into arrays.

Three things are worth knowing before reading it.

**The 2D observations do not matter to MVS.** COLMAP derives each view's depth
search range, and its choice of source views, from *which* images see a point --
never from where the point landed in them. So the fidelity that matters when
handing over a sparse model is the track structure, not the pixel coordinates.

**The pixel coordinates still have to be self-consistent, because of
undistortion.** `sparse_model/v1` stores observations already undistorted, and
`undistort_images` expects a reconstruction in the images' native frame. So the
distortion is re-applied here on the way in. That direction is closed form; it is
only the inverse that needs iteration.

**PatchMatch deletes rather than scores.** There is no confidence channel to
report. What corresponds to it is `depth_map_completeness` -- the fraction of
pixels that survived -- and the holes in the cloud are the module telling the
truth about where the evidence ran out.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import numpy as np
import pycolmap
from sfmkit import Ctx, camera_centres, module, render_points, write_ply


def distort(xy: np.ndarray, K: np.ndarray, dist: np.ndarray) -> np.ndarray:
    """Undistorted pixels -> distorted pixels, in the OpenCV model COLMAP shares.

    Forward only, which is why it is four lines: undistortion is the iterative
    direction. `dist` is OpenCV's [k1, k2, p1, p2, k3] and only the first four are
    used, because COLMAP's OPENCV camera model has no k3 and the reconstruction
    has to be expressed in a model COLMAP can invert.
    """
    if not np.any(dist[:4]):
        return xy

    k1, k2, p1, p2 = (float(v) for v in dist[:4])
    x = (xy[:, 0] - K[0, 2]) / K[0, 0]
    y = (xy[:, 1] - K[1, 2]) / K[1, 1]

    r2 = x * x + y * y
    radial = 1.0 + k1 * r2 + k2 * r2 * r2
    xd = x * radial + 2.0 * p1 * x * y + p2 * (r2 + 2.0 * x * x)
    yd = y * radial + p1 * (r2 + 2.0 * y * y) + 2.0 * p2 * x * y

    return np.stack([xd * K[0, 0] + K[0, 2], yd * K[1, 1] + K[1, 2]], axis=1)


def intrinsics_for(scene, sparse, n_images):
    """Per-image K and distortion.

    K comes from the sparse model when it carries one -- a bundle adjuster that
    refined focal and principal point did so jointly with the poses in the same
    file, and mixing that K with an older one is worse than either. Distortion
    always comes from the scene: `sparse_model/v1` has no distortion array by
    construction, because its observations are undistorted, so a refined K is
    combined with the calibrated coefficients. That is the usual arrangement --
    bundle adjustment refines focal length far more readily than distortion.
    """
    if not scene.has("calibration"):
        raise ValueError(
            "DenseMVS needs intrinsics and this scene carries no calibration. "
            "Pass calibration_path to SceneLoader. A sparse model from VGGT or "
            "MapAnything carries estimated intrinsics and those are used when "
            "present -- but the scene must still supply distortion, and an "
            "uncalibrated scene supplies neither."
        )

    calib = scene.load("calibration")
    dist = np.asarray(calib["distortions"], dtype=np.float64)
    cam_index = calib.get("camera_index")

    if sparse.has("intrinsics"):
        data = sparse.load("intrinsics")
        K = np.asarray(data["K"], dtype=np.float64)
        k_index = data.get("camera_index")
        k_source = "the sparse model"
    else:
        K = np.asarray(calib["intrinsics"], dtype=np.float64)
        k_index = cam_index
        k_source = "the scene's calibration"

    def expand(values, index):
        if index is None:
            index = (
                np.arange(n_images) if len(values) == n_images
                else np.zeros(n_images, int)
            )
        return values[np.asarray(index, dtype=int)]

    dist = dist.reshape(len(dist), -1)
    return expand(K, k_index), expand(dist, cam_index), k_source


def build_reconstruction(scene, sparse, n_images, K_all, dist_all, names, ctx):
    """Artifacts -> a pycolmap.Reconstruction in the images' native pixel frame.

    One COLMAP camera per image rather than per distinct calibration. Undistortion
    is per-image anyway, and a per-image camera is the shape that also survives a
    mixed-resolution scene -- which MVS meets more often than sparse reconstruction
    does, since it is the stage people point at a mixed capture.
    """
    poses = sparse.load("poses")
    cam_from_world = np.asarray(poses["cam_from_world"], dtype=np.float64)
    valid = np.asarray(poses["valid"], dtype=bool)
    image_index = np.asarray(poses["image_index"], dtype=int)

    points = sparse.load("points")
    xyz = np.asarray(points["xyz"], dtype=np.float64)
    rgb = points.get("rgb")

    obs = np.asarray(sparse.load("observations", "obs"), dtype=np.float64)
    sizes = scene.load("images", "size_current")

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

    track_elements: dict[int, list[tuple[int, int]]] = {}

    for frame, image_id in sorted(image_id_of.items(), key=lambda kv: kv[1]):
        K, dist = K_all[frame], dist_all[frame]
        camera = pycolmap.Camera()
        if np.any(dist[:4]):
            camera.model = pycolmap.CameraModelId.OPENCV
            params = [K[0, 0], K[1, 1], K[0, 2], K[1, 2],
                      dist[0], dist[1], dist[2], dist[3]]
        else:
            camera.model = pycolmap.CameraModelId.PINHOLE
            params = [K[0, 0], K[1, 1], K[0, 2], K[1, 2]]
        camera.camera_id = image_id
        camera.width = int(sizes[frame][0])
        camera.height = int(sizes[frame][1])
        camera.params = np.asarray(params, dtype=np.float64)
        camera.has_prior_focal_length = True
        rec.add_camera_with_trivial_rig(camera)

        rows = np.flatnonzero(obs_frame == frame)
        native = distort(obs_xy[rows], K, dist)

        points2D = []
        for local_index, r in enumerate(rows):
            points2D.append(pycolmap.Point2D(native[local_index]))
            track_elements.setdefault(int(obs_point[r]), []).append(
                (image_id, local_index)
            )

        image = pycolmap.Image(
            name=str(names[frame]), camera_id=image_id, points2D=points2D
        )
        image.image_id = image_id

        P = cam_from_world[np.flatnonzero(image_index == frame)[0]]
        rec.add_image_with_trivial_frame(
            image, pycolmap.Rigid3d(pycolmap.Rotation3d(P[:, :3]), P[:, 3])
        )

    ctx.progress(0.08, f"{len(image_id_of)} cameras, adding points")

    kept = 0
    for point_index, elements in track_elements.items():
        # Two views is the minimum COLMAP will accept in a track, and a
        # single-view point contributes nothing to a depth range that the
        # other points do not already contribute.
        if len(elements) < 2:
            continue
        track = pycolmap.Track([pycolmap.TrackElement(i, j) for i, j in elements])
        colour = (
            np.asarray(rgb[point_index], dtype=np.uint8)
            if rgb is not None
            else np.array([128, 128, 128], dtype=np.uint8)
        )
        rec.add_point3D(xyz[point_index], track, colour)
        kept += 1

    return rec, image_id_of, kept


def read_depth_map(path: Path) -> np.ndarray:
    """COLMAP's `<width>&<height>&<channels>&` header followed by float32 data."""
    with open(path, "rb") as handle:
        header = b""
        seen = 0
        while seen < 3:
            byte = handle.read(1)
            if not byte:
                raise IOError(f"{path}: end of file inside the header")
            header += byte
            if byte == b"&":
                seen += 1
        width, height, _ = (int(v) for v in header.decode("ascii").strip("&").split("&"))
        data = np.fromfile(handle, dtype=np.float32, count=width * height)
    if data.size != width * height:
        raise ValueError(
            f"{path}: expected {width * height} depth values, got {data.size}"
        )
    return data.reshape(height, width)


def patch_match_options(p) -> pycolmap.PatchMatchOptions:
    opts = pycolmap.PatchMatchOptions()
    # Left at the default "-1", meaning every visible device. The GPU broker
    # hands this container exactly one -- via `--gpus device=N` under Docker and
    # CUDA_VISIBLE_DEVICES under the subprocess backend -- so "all visible" and
    # "the leased one" are the same set, and naming ctx.device here would name a
    # host index the container cannot see.
    opts.max_image_size = p.max_image_size if p.max_image_size > 0 else -1
    opts.window_radius = p.window_radius
    opts.window_step = p.window_step
    opts.num_samples = p.num_samples
    opts.num_iterations = p.num_iterations
    opts.geom_consistency = p.geom_consistency
    opts.geom_consistency_max_cost = p.geom_consistency_max_cost
    opts.filter = True
    opts.filter_min_ncc = p.filter_min_ncc
    opts.filter_min_triangulation_angle = p.filter_min_triangulation_angle
    opts.filter_min_num_consistent = p.filter_min_num_consistent
    # Fusion walks the consistency graph, so it has to have been written.
    opts.write_consistency_graph = True
    return opts


def fusion_options(p) -> pycolmap.StereoFusionOptions:
    opts = pycolmap.StereoFusionOptions()
    # Matched to PatchMatch's on purpose: fusion reads the images to colour
    # points and the depth maps to place them, and the two have to be indexed the
    # same way.
    opts.max_image_size = p.max_image_size if p.max_image_size > 0 else -1
    opts.min_num_pixels = p.fusion_min_num_pixels
    opts.max_reproj_error = p.fusion_max_reproj_error
    opts.max_depth_error = p.fusion_max_depth_error
    opts.max_normal_error = p.fusion_max_normal_error
    return opts


@module
def run(ctx: Ctx):
    scene = ctx.inputs["scene"]
    sparse = ctx.inputs["sparse"]
    p = ctx.params

    names = scene.load("images", "names")
    n_images = len(names)

    # COLMAP opens the pixels itself, both to undistort and to colour the fused
    # points, so every Image.name has to resolve under one root directory. A scene
    # artifact stores resized copies under data/images with sequential filenames,
    # so its display names do not resolve and passing them yields a grey cloud --
    # the same trap SparseGlobalCOLMAP documents.
    resolved = [scene.resolve(str(pth)) for pth in scene.load("images", "paths")]
    image_root = Path(os.path.commonpath([str(pth.parent) for pth in resolved]))
    colmap_name = [str(pth.relative_to(image_root)) for pth in resolved]

    K_all, dist_all, k_source = intrinsics_for(scene, sparse, n_images)

    ctx.progress(0.02, "building the COLMAP workspace")

    with tempfile.TemporaryDirectory(prefix="mvs-") as tmp:
        work = Path(tmp)
        sparse_dir = work / "sparse"
        dense_dir = work / "dense"
        sparse_dir.mkdir()

        rec, image_id_of, n_points = build_reconstruction(
            scene, sparse, n_images, K_all, dist_all, colmap_name, ctx
        )
        registered = len(image_id_of)

        if registered < 2:
            raise ValueError(
                f"DenseMVS needs at least 2 posed views and the sparse model has "
                f"{registered}. Stereo needs a second view to correlate against."
            )

        out = ctx.output("dense")

        if n_points < 20 * registered:
            out.diagnostic(
                "sparse_too_thin",
                severity="warn",
                message=(
                    f"The sparse model has {n_points} multi-view points over "
                    f"{registered} views."
                ),
                suggested_actions=[
                    "COLMAP derives each view's depth search range from the sparse "
                    "points that view sees; too few gives a range that is wrong "
                    "rather than merely loose.",
                    "Triangulate more points, or bundle-adjust, before running MVS.",
                ],
                see_also="limitations.md#it-inherits-the-sparse-models-depth-range",
            )

        rec.write(str(sparse_dir))

        ctx.progress(0.1, f"undistorting {registered} images")
        pycolmap.undistort_images(
            output_path=str(dense_dir),
            input_path=str(sparse_dir),
            image_path=str(image_root),
            output_type="COLMAP",
        )

        ctx.progress(
            0.15,
            f"patch match over {registered} views"
            + (" with geometric consistency" if p.geom_consistency else ""),
        )
        pycolmap.patch_match_stereo(
            workspace_path=str(dense_dir), options=patch_match_options(p)
        )

        kind = "geometric" if p.geom_consistency else "photometric"

        ctx.progress(0.8, "reading the filtered depth maps")
        depth_dir = dense_dir / "stereo" / "depth_maps"
        depth_files = sorted(depth_dir.glob(f"*.{kind}.bin"))
        maps = [read_depth_map(path) for path in depth_files]

        valid_pixels = sum(int((m > 0).sum()) for m in maps)
        total_pixels = sum(int(m.size) for m in maps)
        completeness = valid_pixels / total_pixels if total_pixels else 0.0
        contributing = sum(1 for m in maps if (m > 0).any())

        ctx.progress(0.85, f"fusing, {completeness:.1%} of pixels valid")
        # A directory, not a file: with the default output_type of "bin" COLMAP
        # writes a whole reconstruction here. The return value is what is read --
        # this path exists only because the call insists on writing somewhere.
        fused_dir = work / "fused"
        fused_dir.mkdir()
        fused = pycolmap.stereo_fusion(
            output_path=str(fused_dir),
            workspace_path=str(dense_dir),
            input_type=kind,
            options=fusion_options(p),
        )

        xyz = np.array([point.xyz for point in fused.points3D.values()],
                       dtype=np.float64)
        rgb = np.array([point.color for point in fused.points3D.values()],
                       dtype=np.uint8)

        if len(xyz) == 0:
            out.metric("point_count", 0, direction="higher_better")
            out.metric("depth_map_completeness", round(completeness, 4),
                       direction="higher_better")
            out.diagnostic(
                "no_points",
                severity="error",
                message="Fusion produced no points.",
                see_also="tuning.md#nothing-survives-the-filters",
            )
            raise ValueError(
                f"fusion produced nothing. {completeness:.1%} of depth-map pixels "
                f"survived filtering across {contributing} of {registered} views."
                + (
                    " With completeness this low the filters are the cause, not "
                    "fusion: lower filter_min_ncc, filter_min_triangulation_angle "
                    "or filter_min_num_consistent."
                    if completeness < 0.02 else
                    " Completeness is healthy, so fusion is the cause: lower "
                    "fusion_min_num_pixels."
                )
            )

        # Same-resolution depth maps are the only case dense_model/v1 can express.
        # Undistortion preserves size for a PINHOLE camera and changes it for a
        # distorted one, so a mixed-resolution scene lands here ragged and the
        # arrays are simply omitted rather than padded.
        shapes = {m.shape for m in maps}
        write_depth = p.write_depth_maps and len(shapes) == 1 and len(maps) > 0

        # The workspace COLMAP fused from is complete at this point and is about to
        # be deleted with the temp directory. Keeping it lets a separate module
        # re-fuse at different settings without paying for the stereo pass again --
        # the depth arrays alone cannot do that, because fusion needs the normal
        # maps and consistency graphs too.
        if p.keep_workspace:
            ctx.progress(0.93, "keeping the COLMAP workspace")
            dest = out.sidecar_dir("workspace")
            for sub_dir in ("stereo", "sparse", "images"):
                src = dense_dir / sub_dir
                if src.exists():
                    shutil.copytree(src, dest / sub_dir, dirs_exist_ok=True)
            kept = sum(f.stat().st_size for f in dest.rglob("*") if f.is_file())
            out.metric("workspace_megabytes", round(kept / 1e6, 1), direction="neutral")

        ctx.progress(0.95, f"{len(xyz)} points")

        out.save("points", xyz=xyz.astype(np.float32), rgb=rgb)

        # A .ply sidecar beside the npz, the same one DenseVGGT writes and
        # byte-compatible with it because both go through sfmkit's writer. This
        # is what MeshLab, CloudCompare or an external evaluation script opens.
        # Three orthographic views, one of them down the camera ring's own axis --
        # a direction no input image had, which is where a backdrop plane or a shell
        # of floaters becomes visible. Every other reading this module publishes is a
        # scalar, and no scalar separates a clean surface from one wrapped in stray
        # points. Reachable as sfm_artifact_image(<id>, 'browse/cloud_views.png').
        outside = None
        if p.write_cloud_views:
            poses = sparse.load("poses")
            _, outside = render_points(
                out.sidecar_dir("browse") / "cloud_views.png", xyz, rgb,
                centres=camera_centres(poses["cam_from_world"], poses["valid"]))

        ply_bytes = 0
        if p.write_ply:
            ply = write_ply(
                out.sidecar_dir("ply") / "cloud.ply", xyz, rgb,
                comments=[
                    f"produced by DenseMVS {ctx.module_version}",
                    f"patch match {kind}, max_image_size {p.max_image_size or 0}",
                    "frame: the sparse model's world frame, in its scale",
                ],
            )
            ply_bytes = ply.stat().st_size
        if write_depth:
            # COLMAP marks invalid depth with 0; the type says non-finite, so the
            # translation happens here rather than leaving a real zero depth that
            # a consumer would unproject onto the camera centre.
            stacked = np.stack(maps).astype(np.float32)
            stacked[stacked <= 0] = np.nan
            # COLMAP names each map "<image name>.<kind>.bin", so the frame it
            # belongs to comes back through the same name table that got it there.
            frame_of_name = {name: frame for frame, name in enumerate(colmap_name)}
            suffix = f".{kind}.bin"
            out.save(
                "depth",
                maps=stacked,
                image_index=np.array(
                    [frame_of_name[path.name[: -len(suffix)]] for path in depth_files],
                    dtype=np.int32,
                ),
            )

        out.metric("point_count", len(xyz),
                   direction="higher_better", healthy=(10000, None))
        out.metric("views_contributing", contributing,
                   direction="higher_better", healthy=(2, None))
        # PatchMatch expresses confidence by deleting pixels rather than scoring
        # them. depth_map_completeness is the same information.
        out.metric("mean_depth_confidence", None, direction="higher_better")
        out.metric("depth_map_completeness", round(completeness, 4),
                   direction="higher_better", healthy=(0.2, None))
        out.metric("points_per_view", round(len(xyz) / max(contributing, 1), 1),
                   direction="neutral")
        out.metric("fusion_ratio", round(valid_pixels / max(len(xyz), 1), 2),
                   direction="neutral")
        out.metric("input_registered_images", registered, direction="higher_better")
        out.metric("ply_megabytes", round(ply_bytes / 2**20, 2), direction="neutral")

        if completeness < 0.05:
            out.diagnostic(
                "low_completeness",
                severity="warn",
                message=(
                    f"Only {completeness:.1%} of depth-map pixels survived the "
                    f"filters."
                ),
                suggested_actions=[
                    "Lower filter_min_ncc if the scene is low-texture.",
                    "Lower filter_min_triangulation_angle if the baselines are small.",
                    "Lower filter_min_num_consistent if each surface is seen by few views.",
                    "Check the poses first -- imprecise poses fail the geometric "
                    "pass, and turning geom_consistency off to 'fix' that hides the "
                    "problem rather than solving it.",
                ],
                see_also="tuning.md#nothing-survives-the-filters",
            )

        if contributing < registered:
            out.diagnostic(
                "views_dropped",
                severity="warn",
                message=(
                    f"{registered - contributing} of {registered} posed views "
                    f"produced no valid depth."
                ),
                suggested_actions=[
                    "A view that sees no sparse points gets no depth range and is "
                    "skipped; read the sparse model's coverage first.",
                    "Otherwise check those images for blur, exposure change, or "
                    "being an outlier viewpoint with no overlap.",
                ],
                see_also="limitations.md#only-posed-views-contribute",
            )

        out.note(
            f"COLMAP PatchMatch stereo ({kind}) over {registered} posed views at "
            f"max_image_size {p.max_image_size or 'full'}, intrinsics from "
            f"{k_source}. {completeness:.1%} of depth-map pixels survived "
            f"filtering, {contributing} views contributed, and fusion produced "
            f"{len(xyz)} points -- {valid_pixels / max(len(xyz), 1):.1f} valid "
            f"pixels per point. Confidence is null by construction: PatchMatch "
            f"deletes pixels rather than scoring them, so completeness is the "
            f"number that carries that information. Depth maps were "
            + ("written." if write_depth else
               "not written (write_depth_maps is off)."
               if len(shapes) <= 1 else
               f"not written -- the {len(shapes)} distinct undistorted resolutions "
               f"cannot be expressed as one array.")
            + ("" if outside is None else
               f" browse/cloud_views.png holds three orthographic views of the cloud "
               f"-- two from the cameras' own ring and the third down its axis, a "
               f"direction no input image had. It is framed on the bulk of the cloud, "
               f"so {outside} of {len(xyz)} points sit outside the frame and are not "
               f"all visible in it.")
        )
