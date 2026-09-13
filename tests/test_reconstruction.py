"""The reconstruction half of the pipeline: poses, structure, refinement.

These are slower than the front half because each one builds a real model. They
are still worth running end to end rather than against fixtures, because every bug
found in this stage so far has been a convention mismatch between two libraries --
exactly what a fixture would have encoded rather than caught.
"""

import numpy as np
import pytest

from dataset_paths import DTU_CALIB, DTU_SCAN1, needs_cv2, needs_dtu, needs_pil
from sfmorch import ExecutionError

pytestmark = [needs_dtu, needs_cv2, needs_pil]


def needs(name):
    import importlib.util

    return pytest.mark.skipif(
        importlib.util.find_spec(name) is None, reason=f"{name} not installed"
    )


needs_pycolmap = needs("pycolmap")


def build(orch, *, n=8, upto="sparse", **overrides):
    """Run the classical chain as far as `upto`, returning every artifact."""
    out = {}
    out["scene"] = orch.run("SceneLoader", run_id="rc", params={
        "image_dir": str(DTU_SCAN1),
        "calibration_path": str(DTU_CALIB),
        "max_images": n,
        "sampling": "head",
        "resize": "auto",
        "max_edge": 1024,
    }).primary
    out["features"] = orch.run(
        "FeatureDetectionSIFT", run_id="rc", inputs={"scene": out["scene"].id}
    ).primary
    out["matches"] = orch.run(
        "FeatureMatchNN", run_id="rc",
        inputs={"scene": out["scene"].id, "features": out["features"].id},
        params={"pairing": "exhaustive"},
    ).primary
    out["tracks"] = orch.run(
        "FeatureTrackUnionFind", run_id="rc",
        inputs={"scene": out["scene"].id, "matches": out["matches"].id},
    ).primary
    if upto == "tracks":
        return out

    out["poses"] = orch.run(
        "PoseEssentialToPnP", run_id="rc",
        inputs={"scene": out["scene"].id, "tracks": out["tracks"].id},
        params=overrides.get("pose", {}),
    ).primary
    if upto == "poses":
        return out

    out["sparse"] = orch.run(
        "SparseTriangulation", run_id="rc",
        inputs={"scene": out["scene"].id, "tracks": out["tracks"].id,
                "poses": out["poses"].id},
        params=overrides.get("sparse", {}),
    ).primary
    return out


# --------------------------------------------------------------------------- #
# Poses
# --------------------------------------------------------------------------- #


def test_a_contiguous_dtu_capture_registers_completely(orch):
    poses = build(orch, upto="poses")["poses"]

    assert poses.type == "poses/v1"
    assert poses.metric("registered_fraction") == 1.0
    assert poses.metric("mean_reprojection_error") < 2.0
    assert poses.metric("median_triangulation_angle") > 3.0


def test_poses_are_valid_rigid_transforms(orch):
    """A rotation that is not a rotation produces a model that looks fine and is
    wrong, and nothing downstream checks it."""
    poses = build(orch, upto="poses")["poses"]
    P = poses.load("poses", "cam_from_world")[poses.load("poses", "valid")]

    for R in P[:, :, :3]:
        assert np.allclose(R @ R.T, np.eye(3), atol=1e-6)
        assert np.isclose(np.linalg.det(R), 1.0, atol=1e-6)


def test_the_world_frame_is_the_seed_camera(orch):
    """Exactly one registered camera is the identity: the first of the seed pair."""
    poses = build(orch, upto="poses")["poses"]
    P = poses.load("poses", "cam_from_world")[poses.load("poses", "valid")]

    identity = np.hstack([np.eye(3), np.zeros((3, 1))])
    at_origin = [i for i, pose in enumerate(P) if np.allclose(pose, identity, atol=1e-9)]
    assert len(at_origin) == 1


def test_the_seed_pair_is_chosen_for_parallax_not_for_match_count(orch):
    """The predecessor hardcoded index 0. On a turntable capture the adjacent pair
    has the most matches and the least baseline, so a match-count criterion picks
    exactly the wrong pair."""
    poses = build(orch, n=12, upto="poses")["poses"]
    assert poses.metric("init_pair_angle") > 4.0
    assert "0 and 8" in poses.manifest.body or "images (" in poses.manifest.body


def test_an_uncalibrated_scene_is_refused_with_the_alternative_named(orch):
    scene = orch.run("SceneLoader", run_id="rc", params={
        "image_dir": str(DTU_SCAN1), "max_images": 6, "sampling": "head",
        "resize": "auto", "max_edge": 640,
    }).primary
    feats = orch.run(
        "FeatureDetectionSIFT", run_id="rc", inputs={"scene": scene.id}
    ).primary
    matches = orch.run(
        "FeatureMatchNN", run_id="rc",
        inputs={"scene": scene.id, "features": feats.id},
        params={"pairing": "exhaustive"},
    ).primary
    tracks = orch.run(
        "FeatureTrackUnionFind", run_id="rc",
        inputs={"scene": scene.id, "matches": matches.id},
    ).primary

    with pytest.raises(ExecutionError, match="VGGT|estimates intrinsics"):
        orch.run("PoseEssentialToPnP", run_id="rc",
                 inputs={"scene": scene.id, "tracks": tracks.id})


def test_raising_the_parallax_floor_buys_a_wider_baseline_seed(orch):
    """The scorer trades match count for parallax on demand. Measured on 8
    contiguous DTU frames: floor 4 seeds at 12.1 degrees, floor 40 at 49.8."""
    built = build(orch, upto="tracks")
    common = {"scene": built["scene"].id, "tracks": built["tracks"].id}

    low = orch.run("PoseEssentialToPnP", run_id="rc", inputs=common,
                   params={"init_min_angle_deg": 4.0}).primary
    high = orch.run("PoseEssentialToPnP", run_id="rc", inputs=common,
                    params={"init_min_angle_deg": 40.0}).primary

    assert high.metric("init_pair_angle") > low.metric("init_pair_angle")
    assert high.metric("init_pair_angle") >= 40.0


def test_no_viable_seed_is_refused_with_the_numbers_that_explain_it(orch):
    """Triggered here by demanding tracks longer than the set can produce, rather
    than by a degenerate capture -- DTU has ample parallax and ample matches. It is
    the same refusal path, and the message has to name both conditions it checked."""
    built = build(orch, n=8, upto="tracks")
    with pytest.raises(ExecutionError, match="shared tracks"):
        # No track can span 20 views when there are only 8 images.
        orch.run("PoseEssentialToPnP", run_id="rc",
                 inputs={"scene": built["scene"].id, "tracks": built["tracks"].id},
                 params={"min_track_len": 20})


# --------------------------------------------------------------------------- #
# In-loop local bundle adjustment
# --------------------------------------------------------------------------- #


@needs_pycolmap
def test_in_loop_local_ba_lowers_the_error_it_registers_against(orch):
    """The whole point of refining during registration rather than after it.

    Measured on 16 contiguous DTU frames: 0.647 -> 0.551px for SIFT+NN, and
    1.068 -> 0.843px for SuperPoint+LightGlue, where the drift is four times
    larger. On the full 49-frame set the learned stack registers 34/49 without it
    and 48/49 with it -- that one is too slow to assert here, but it is the reason
    the default is on.
    """
    built = build(orch, n=16, upto="tracks")
    common = {"scene": built["scene"].id, "tracks": built["tracks"].id}

    off = orch.run("PoseEssentialToPnP", run_id="rc", inputs=common,
                   params={"local_ba": False}).primary
    on = orch.run("PoseEssentialToPnP", run_id="rc", inputs=common,
                  params={"local_ba": True}).primary

    assert on.metric("mean_reprojection_error") < off.metric("mean_reprojection_error")
    assert on.metric("registered_images") >= off.metric("registered_images")


@needs_pycolmap
def test_local_ba_reports_nothing_when_it_did_not_run(orch):
    """A metric that reports 0.0 gain when it never ran reads as `tried, useless`.
    None is the only honest value for a measurement that was not taken."""
    built = build(orch, n=8, upto="tracks")
    off = orch.run("PoseEssentialToPnP", run_id="rc",
                   inputs={"scene": built["scene"].id, "tracks": built["tracks"].id},
                   params={"local_ba": False}).primary

    assert off.metric("local_ba_runs") == 0
    assert off.metric("local_ba_gain_px") is None
    assert off.metric("escaped_points") == 0


@needs_pycolmap
def test_escaped_points_are_reported_and_never_called_a_divergence(orch):
    """The pose stage counts escapes and judges nothing: the diagnostic appears
    exactly when the count is above zero, and no divergence error exists."""
    poses = build(orch, n=16, upto="poses")["poses"]
    codes = {d.code for d in poses.manifest.diagnostics}
    assert ("points_escaped" in codes) == (poses.metric("escaped_points") > 0)
    assert "local_ba_diverged" not in codes


@needs_pycolmap
def test_an_escaped_point_is_counted_and_left_out_of_the_window_gain():
    """One escapee put the old mean gain near 1e150; counted apart, the gain
    describes the points that stayed and is bounded by the image."""
    ad = _adapter("pose_incremental")
    before = np.full(500, 0.5)
    after = np.full(500, 0.3)
    after[7] = 1e150
    after[9] = np.nan
    r = ad.window_readings(before, after, extent=1024.0)

    assert r["escaped"] == 2
    assert r["gain"] == pytest.approx(0.2)


@needs_pycolmap
def test_a_point_that_escaped_in_an_earlier_solve_does_not_own_the_next_gain():
    ad = _adapter("pose_incremental")
    before = np.full(500, 0.5)
    before[3] = 5e3  # left behind by the previous solve, back inside after this one
    after = np.full(500, 0.3)
    r = ad.window_readings(before, after, extent=1024.0)

    assert r["escaped"] == 0
    assert r["gain"] == pytest.approx(0.2)


@needs_pycolmap
def test_the_local_ba_schedule_is_what_the_parameters_say(orch):
    """warmup solves after every registration, then every interval-th one. Getting
    this wrong is invisible in the output model and shows up only as runtime."""
    built = build(orch, n=16, upto="tracks")
    common = {"scene": built["scene"].id, "tracks": built["tracks"].id}

    every = orch.run("PoseEssentialToPnP", run_id="rc", inputs=common,
                     params={"local_ba_warmup": 0, "local_ba_interval": 1}).primary
    sparse_schedule = orch.run(
        "PoseEssentialToPnP", run_id="rc", inputs=common,
        params={"local_ba_warmup": 0, "local_ba_interval": 5},
    ).primary

    # 16 registrations, minus the seed pair that is already in place when the first
    # refine() runs; the exact count depends only on the schedule, not the scene.
    assert every.metric("local_ba_runs") > sparse_schedule.metric("local_ba_runs")
    assert sparse_schedule.metric("local_ba_runs") >= 3


@needs_pycolmap
def test_local_ba_keeps_the_world_frame_pinned_to_the_seed_camera(orch):
    """The two oldest cameras in each window are held constant, so the seed camera
    is never written back and the gauge cannot drift. If it could, every downstream
    consumer that assumes the first registered camera is the origin would be wrong
    in a way no metric reports."""
    poses = build(orch, n=16, upto="poses")["poses"]
    P = poses.load("poses", "cam_from_world")[poses.load("poses", "valid")]

    identity = np.hstack([np.eye(3), np.zeros((3, 1))])
    assert sum(np.allclose(pose, identity, atol=1e-9) for pose in P) == 1


# --------------------------------------------------------------------------- #
# Structure
# --------------------------------------------------------------------------- #


def test_triangulation_produces_a_consistent_sparse_model(orch):
    sparse = build(orch)["sparse"]

    assert sparse.type == "sparse_model/v1"
    assert sparse.metric("point_count") > 100
    assert sparse.metric("mean_reprojection_error") < 2.0
    assert sparse.metric("rejected_cheirality") == 0.0


def test_every_observation_points_at_a_real_point_and_a_registered_frame(orch):
    built = build(orch)
    sparse = built["sparse"]

    obs = sparse.load("observations", "obs")
    xyz = sparse.load("points", "xyz")
    valid = sparse.load("poses", "valid")

    assert obs[:, 1].max() < len(xyz)
    assert obs[:, 1].min() >= 0
    for frame in np.unique(obs[:, 0]).astype(int):
        assert valid[frame], f"frame {frame} has observations but no pose"


def test_points_reproject_where_the_observations_say_they_do(orch):
    """The end-to-end geometric check. If any convention is wrong -- cam-from-world
    versus world-from-camera, distorted versus undistorted, resized versus
    original -- this is what catches it."""
    built = build(orch)
    scene, sparse = built["scene"], built["sparse"]

    xyz = sparse.load("points", "xyz")
    obs = sparse.load("observations", "obs")
    P = sparse.load("poses", "cam_from_world")

    # DTU ships ONE camera matrix for the whole set and no camera_index, which is
    # the "all images share camera 0" case scene/v1 documents. Broadcasting it the
    # way the modules do is part of what this test is checking.
    K = scene.load("calibration", "intrinsics")
    per_image = (lambda f: K[f]) if len(K) > 1 else (lambda f: K[0])

    sample = obs[:: max(1, len(obs) // 500)]
    errors = []
    for frame, point_index, x, y in sample:
        pose, Kf = P[int(frame)], per_image(int(frame))
        cam = pose[:, :3] @ xyz[int(point_index)] + pose[:, 3]
        assert cam[2] > 0, "point behind the camera"
        pixel = (cam[:2] / cam[2]) @ Kf[:2, :2].T + Kf[:2, 2]
        errors.append(np.linalg.norm(pixel - np.array([x, y])))

    assert np.mean(errors) < 2.0
    assert np.max(errors) < 10.0


def test_a_stricter_angle_filter_trades_points_for_accuracy(orch):
    """The documented gradient, pinned."""
    loose = build(orch, sparse={"min_triangulation_angle_deg": 1.0})["sparse"]
    strict = build(orch, sparse={"min_triangulation_angle_deg": 8.0})["sparse"]

    assert strict.metric("point_count") < loose.metric("point_count")
    assert strict.metric("median_triangulation_angle") > loose.metric(
        "median_triangulation_angle"
    )


def test_colour_is_sampled_from_the_images(orch):
    sparse = build(orch)["sparse"]
    rgb = sparse.load("points", "rgb")

    assert rgb.dtype == np.uint8
    assert len(rgb) == len(sparse.load("points", "xyz"))
    assert len(np.unique(rgb, axis=0)) > 50, "a real scene is not one colour"


# --------------------------------------------------------------------------- #
# Bundle adjustment
# --------------------------------------------------------------------------- #


@needs_pycolmap
def test_global_bundle_adjustment_lowers_reprojection_error(orch):
    built = build(orch)
    ba = orch.run("BundleAdjustmentGlobal", run_id="rc",
                  inputs={"scene": built["scene"].id, "sparse": built["sparse"].id}).primary

    assert ba.metric("reprojection_error_after") < ba.metric("reprojection_error_before")
    assert ba.metric("error_reduction") > 0.0
    assert ba.metric("converged") == 1
    assert ba.metric("escaped_points") == 0


def _adapter(module_dir):
    """Import a module's adapter directly, for its pure functions."""
    import importlib.util

    from dataset_paths import MODULES

    path = MODULES / module_dir / "adapter.py"
    spec = importlib.util.spec_from_file_location(f"{module_dir}_adapter_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@needs_pycolmap
@pytest.mark.parametrize("module_dir", ["ba_global", "ba_local"])
def test_one_escaped_point_is_counted_not_called_a_divergence(module_dir):
    """Measured: one point in tens of thousands, left behind along near-parallel
    rays, put the MEAN at 1e149 with the median and p95 untouched, and the old
    guard called the most accurate of three models unusable. Judged per point,
    it is one escapee on a sound solve, and the means describe the rest."""
    ad = _adapter(module_dir)
    before = np.random.default_rng(0).gamma(2.0, 0.18, 60000)
    after = before * 0.6
    after[123] = 1.3e154
    r = ad.error_readings(before, after, extent=1024.0)

    assert not r["diverged"]
    assert r["escaped"] == 1
    assert r["mean_after"] == pytest.approx(np.delete(after, 123).mean())


@needs_pycolmap
@pytest.mark.parametrize("module_dir", ["ba_global", "ba_local"])
def test_a_solve_whose_escapees_reach_the_tail_is_still_diverged(module_dir):
    """The guard exists for a real failure -- 1e151px from a solve that lost its
    trust region -- and the fix must not stop it firing on one."""
    ad = _adapter(module_dir)
    before = np.full(1000, 0.4)
    after = np.full(1000, 0.3)
    after[:80] = 1e151
    assert ad.error_readings(before, after, extent=1024.0)["diverged"]
    assert ad.error_readings(before, np.full(1000, np.nan), extent=1024.0)["diverged"]


@needs_pycolmap
@pytest.mark.parametrize("module_dir", ["ba_global", "ba_local"])
def test_a_tail_grown_by_orders_of_magnitude_is_diverged_inside_the_image(module_dir):
    ad = _adapter(module_dir)
    before = np.full(1000, 0.2)
    after = np.full(1000, 0.2)
    after[900:] = 500.0
    r = ad.error_readings(before, after, extent=1024.0)
    assert r["escaped"] == 0
    assert r["diverged"]


@needs_pycolmap
@pytest.mark.parametrize("module_dir", ["ba_global", "ba_local"])
def test_the_escape_bound_is_the_image_not_a_pixel_constant(module_dir):
    """A fixed constant is loose on a small image and tight on a large one."""
    ad = _adapter(module_dir)
    before = np.full(1000, 0.3)
    after = np.full(1000, 0.3)
    after[0] = 800.0
    assert ad.error_readings(before, after, extent=640.0)["escaped"] == 1
    assert ad.error_readings(before, after, extent=1600.0)["escaped"] == 0


# --------------------------------------------------------------------------- #
# SparseVerification -- the fixed end step
# --------------------------------------------------------------------------- #


def _two_views(rotation_error_deg=0.0):
    """500 points seen by two calibrated cameras; optionally a wrong second pose."""
    rng = np.random.default_rng(1)
    K = np.array([[800.0, 0.0, 512.0], [0.0, 800.0, 384.0], [0.0, 0.0, 1.0]])
    X = rng.uniform([-1, -1, 4], [1, 1, 6], (500, 3))

    def rot(axis, deg):
        a = np.radians(deg)
        c, s = np.cos(a), np.sin(a)
        return {"x": np.array([[1, 0, 0], [0, c, -s], [0, s, c]]),
                "y": np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])}[axis]

    cam_i = np.hstack([np.eye(3), np.zeros((3, 1))])
    cam_j = np.hstack([rot("y", 10.0), np.array([[-0.5], [0.0], [0.0]])])

    def project(cam):
        x = (K @ (cam[:, :3] @ X.T + cam[:, 3:])).T
        return x[:, :2] / x[:, 2:]

    xy = np.c_[project(cam_i), project(cam_j)]
    believed = cam_j.copy()
    believed[:, :3] = rot("x", rotation_error_deg) @ cam_j[:, :3]
    return K, cam_i, believed, xy


@needs_pycolmap
def test_a_wrong_relative_pose_is_contradicted_by_the_correspondences():
    ad = _adapter("sparse_verification")
    K, ci, cj, xy = _two_views()
    assert np.median(ad.sampson(ad.fundamental(K, K, ci, cj), xy)) < 1e-6
    K, ci, cj, xy = _two_views(rotation_error_deg=3.0)
    assert np.median(ad.sampson(ad.fundamental(K, K, ci, cj), xy)) > 3.0


@needs_pycolmap
def test_a_match_is_used_only_when_both_ends_land_on_one_model_point():
    """Used means the model was fit on it; everything else is the test set."""
    ad = _adapter("sparse_verification")

    class Model:
        def load(self, file, array):
            return np.array([[0, 7, 100.0, 100.0], [1, 7, 300.0, 120.0],
                             [1, 9, 500.0, 500.0]])

    index = ad.observation_index(Model())
    left = ad.nearest_point(index.get(0), np.array([[100.5, 100.4], [100.5, 100.4]]))
    right = ad.nearest_point(index.get(1), np.array([[300.3, 119.8], [310.0, 120.0]]))
    assert list(left) == [7, 7]
    assert list(right) == [7, -1]  # ten pixels away is a different correspondence


@needs_pycolmap
def test_a_refined_model_is_consistent_with_matches_it_never_used(orch):
    built = build(orch)
    ba = orch.run("BundleAdjustmentGlobal", run_id="rc",
                  inputs={"scene": built["scene"].id, "sparse": built["sparse"].id}).primary
    v = orch.run("SparseVerification", run_id="rc",
                 inputs={"scene": built["scene"].id, "sparse": ba.id,
                         "matches": built["matches"].id}).primary

    assert v.type == "custom/verification/v1"
    assert v.metric("pairs_verified") > 0
    assert 0.0 < v.metric("held_out_share") < 1.0
    assert v.metric("heldout_residual_px") < 3.0
    assert not [d for d in v.manifest.diagnostics if d.severity == "error"]


@needs_pycolmap
def test_the_service_verifies_every_refined_model_without_being_asked(tmp_path, registry):
    """The fixed step: an optimization module's run comes back already verified,
    against the matches in the model's own lineage, and the model stays a leaf."""
    from dataset_paths import REPO

    from sfmkit import ArtifactStore
    from sfmorch import Orchestrator
    from sfmorch.service import ServiceConfig, SfmService

    store = ArtifactStore(tmp_path / "store")
    orch = Orchestrator(store=store, registry=registry)
    svc = SfmService(
        config=ServiceConfig(modules_dir=REPO / "modules", store_root=store.root,
                             skills_dir=REPO / "skills", inline_wait_s=600.0),
        orchestrator=orch, registry=registry,
    )
    try:
        built = build(orch)
        out = svc.run("BundleAdjustmentGlobal", run_id="rc", wait_s=600.0,
                      inputs={"scene": built["scene"].id, "sparse": built["sparse"].id})
        v = out["verification"]
        assert v["status"] == "ran"
        assert v["evidence"] == built["matches"].id
        assert v["metrics"]["heldout_residual_px"] < 3.0

        summary = svc.run_summary("rc")
        model = out["outputs"]["sparse"]
        assert model in summary["leaves"]
        assert summary["verification"][model]["status"] == "ran"
    finally:
        svc.jobs.shutdown()


@needs_pycolmap
def test_colmaps_error_agrees_with_our_own_triangulator(orch):
    """Two independent implementations measuring the same thing. A disagreement
    means a convention bug in the array-to-Reconstruction translation, not a bad
    model -- which is a completely different thing to go and fix."""
    built = build(orch)
    ba = orch.run("BundleAdjustmentGlobal", run_id="rc",
                  inputs={"scene": built["scene"].id, "sparse": built["sparse"].id}).primary

    ours = built["sparse"].metric("mean_reprojection_error")
    colmaps = ba.metric("reprojection_error_before")
    assert abs(ours - colmaps) < 0.05, f"{ours} vs {colmaps}"


@needs_pycolmap
def test_a_colmap_sidecar_is_written_and_opens(orch):
    built = build(orch)
    ba = orch.run("BundleAdjustmentGlobal", run_id="rc",
                  inputs={"scene": built["scene"].id, "sparse": built["sparse"].id}).primary

    assert ba.sidecars() == ["colmap"]
    path = ba.sidecar("colmap")
    assert path is not None and path.exists()

    import pycolmap

    rec = pycolmap.Reconstruction(str(path))
    assert rec.num_points3D() == ba.metric("points_optimized")
    assert rec.num_reg_images() == int(built["poses"].load("poses", "valid").sum())


@needs_pycolmap
def test_convergence_is_reported_honestly_when_the_cap_bites(orch):
    """`"CONVERGENCE" in "NO_CONVERGENCE"` is True, so a substring test reported
    success on exactly the solves that ran out of iterations."""
    built = build(orch)
    starved = orch.run("BundleAdjustmentGlobal", run_id="rc",
                       inputs={"scene": built["scene"].id, "sparse": built["sparse"].id},
                       params={"max_iterations": 3}).primary

    assert starved.metric("converged") == 0
    assert "did_not_converge" in [d.code for d in starved.manifest.diagnostics]


@needs_pycolmap
def test_bundle_adjustment_is_idempotent_in_shape_and_chains(orch):
    built = build(orch)
    once = orch.run("BundleAdjustmentGlobal", run_id="rc",
                    inputs={"scene": built["scene"].id, "sparse": built["sparse"].id}).primary
    twice = orch.run("BundleAdjustmentGlobal", run_id="rc",
                     inputs={"scene": built["scene"].id, "sparse": once.id}).primary

    assert twice.type == "sparse_model/v1"
    # Already at a minimum, so the second pass should find nothing worth moving.
    assert abs(twice.metric("error_reduction")) < 0.05


@needs_pycolmap
def test_local_bundle_adjustment_leaves_the_fixed_cameras_untouched(orch):
    """The defining property. If fixed cameras move, `local` means nothing."""
    built = build(orch, n=12)
    ba = orch.run("BundleAdjustmentLocal", run_id="rc",
                  inputs={"scene": built["scene"].id, "sparse": built["sparse"].id},
                  params={"anchor": "last", "window_size": 4}).primary

    before = built["sparse"].load("poses", "cam_from_world")
    after = ba.load("poses", "cam_from_world")
    moved = [i for i in range(len(before)) if not np.allclose(before[i], after[i])]

    assert len(moved) == ba.metric("cameras_refined")
    assert ba.metric("cameras_fixed") >= 2  # the gauge needs two


@needs_pycolmap
def test_largest_error_anchors_on_the_worst_part_of_the_model(orch):
    built = build(orch, n=12)
    common = {"scene": built["scene"].id, "sparse": built["sparse"].id}
    last = orch.run("BundleAdjustmentLocal", run_id="rc", inputs=common,
                    params={"anchor": "last", "window_size": 5}).primary
    worst = orch.run("BundleAdjustmentLocal", run_id="rc", inputs=common,
                     params={"anchor": "largest_error", "window_size": 5}).primary

    assert worst.metric("window_error_before") > last.metric("window_error_before")


@needs_pycolmap
def test_a_local_window_improves_its_window_more_than_the_whole_model(orch):
    built = build(orch, n=12)
    ba = orch.run("BundleAdjustmentLocal", run_id="rc",
                  inputs={"scene": built["scene"].id, "sparse": built["sparse"].id},
                  params={"anchor": "last", "window_size": 5}).primary

    window_gain = ba.metric("window_error_before") - ba.metric("window_error_after")
    model_gain = ba.metric("reprojection_error_before") - ba.metric("reprojection_error_after")
    assert window_gain > model_gain


# --------------------------------------------------------------------------- #
# The two alternatives to the classical chain
# --------------------------------------------------------------------------- #


needs_gtsam = needs("gtsam")


@needs_pycolmap
def test_global_reconstruction_needs_no_pose_module(orch):
    """The point of SparseGlobalCOLMAP: it consumes pairs and estimates poses
    itself, so the chain is scene -> detect -> match -> reconstruct, with no
    tracker and no pose estimator in it at all."""
    built = build(orch, n=12, upto="tracks")
    sparse = orch.run(
        "SparseGlobalCOLMAP", run_id="rc",
        inputs={"scene": built["scene"].id, "matches": built["matches"].id},
    ).primary

    assert sparse.type == "sparse_model/v1"
    assert sparse.metric("registered_fraction") == 1.0
    assert sparse.metric("mean_reprojection_error") < 1.0
    assert sparse.load("poses", "valid").all()


@needs_pycolmap
def test_bundle_adjustment_accepts_a_model_that_carries_no_track_ids(orch):
    """`points.track_id` is OPTIONAL in sparse_model/v1 and four of the five
    producers omit it. Bundle adjustment read it as
    `np.asarray(points.get("track_id"))`, and `np.asarray(None)` is a 0-d object
    array rather than None -- so the "is not None" guard passed and the indexing
    raised. Every BA-after-anything-but-SparseTriangulation chain was broken.
    """
    built = build(orch, n=12, upto="tracks")
    sparse = orch.run(
        "SparseGlobalCOLMAP", run_id="rc",
        inputs={"scene": built["scene"].id, "matches": built["matches"].id},
    ).primary
    assert "track_id" not in sparse.load("points"), "this test needs a producer that omits it"

    ba = orch.run("BundleAdjustmentGlobal", run_id="rc",
                  inputs={"scene": built["scene"].id, "sparse": sparse.id}).primary

    assert ba.metric("point_count") > 0
    # Absent upstream means -1 here, not a crash and not a wrong id.
    assert (ba.load("points", "track_id") == -1).all()


@needs_pycolmap
def test_the_global_mapper_writes_its_own_intrinsics(orch):
    """It may refine focal length, so a downstream module reading the scene's
    calibration would disagree with these poses."""
    built = build(orch, n=12, upto="tracks")
    sparse = orch.run(
        "SparseGlobalCOLMAP", run_id="rc",
        inputs={"scene": built["scene"].id, "matches": built["matches"].id},
    ).primary

    assert sparse.has("intrinsics")
    assert sparse.load("intrinsics", "K").shape == (12, 3, 3)


@needs_pycolmap
def test_the_global_mapper_colours_points_from_the_pixels(orch):
    """COLMAP reads the images itself, and a scene artifact stores resized copies
    under sequential filenames. Passing it the scene's display names produces a
    uniformly grey cloud with nothing to indicate anything went wrong."""
    built = build(orch, n=12, upto="tracks")
    sparse = orch.run(
        "SparseGlobalCOLMAP", run_id="rc",
        inputs={"scene": built["scene"].id, "matches": built["matches"].id},
    ).primary

    rgb = sparse.load("points", "rgb")
    assert len(np.unique(rgb, axis=0)) > 100


@needs_gtsam
def test_gtsam_triangulation_is_a_drop_in_for_the_opencv_one(orch):
    """Same inputs, same output type, same filter defaults. Swapping them changes
    the estimator and nothing else, which is what makes the comparison meaningful."""
    built = build(orch, n=12, upto="poses")
    common = {"scene": built["scene"].id, "tracks": built["tracks"].id,
              "poses": built["poses"].id}

    opencv = orch.run("SparseTriangulation", run_id="rc", inputs=common).primary
    gtsam_out = orch.run("SparseTriangulationGTSAM", run_id="rc", inputs=common).primary

    assert gtsam_out.type == opencv.type
    # Poses pass through untouched in both, which is what "pure structure stage"
    # means and what lets the two clouds be compared at all.
    assert np.array_equal(
        opencv.load("poses", "cam_from_world"), gtsam_out.load("poses", "cam_from_world")
    )
    # Measured on 12 DTU frames: 6900 points at 0.365px vs 6949 at 0.391px. The
    # multi-view estimator keeps tracks whose widest PAIR alone could not support
    # a point, and those harder points raise the mean -- so more points with
    # slightly worse error is the expected direction, not a regression.
    assert gtsam_out.metric("point_count") >= opencv.metric("point_count")
    assert gtsam_out.metric("mean_reprojection_error") < 2.0


@needs_gtsam
def test_the_landmark_distance_bound_only_removes_points(orch):
    """The filter with no counterpart in the pairwise path. Its threshold is in
    the reconstruction's arbitrary scale unit, so the test asserts the direction
    rather than a number."""
    built = build(orch, n=8, upto="poses")
    common = {"scene": built["scene"].id, "tracks": built["tracks"].id,
              "poses": built["poses"].id}

    unbounded = orch.run("SparseTriangulationGTSAM", run_id="rc", inputs=common).primary

    # The bound is DERIVED from the cloud rather than hardcoded, because the unit
    # is the seed pair's baseline and the seed pair differs between reconstructions:
    # 3.0 keeps everything on 12 DTU frames and rejects everything on 8. That is a
    # property of the parameter worth encoding in the test rather than working
    # around with a magic number.
    xyz = unbounded.load("points", "xyz")
    P = unbounded.load("poses", "cam_from_world")[unbounded.load("poses", "valid")]
    centers = np.array([-pose[:, :3].T @ pose[:, 3] for pose in P])
    furthest = np.linalg.norm(xyz[:, None, :] - centers[None], axis=2).max(axis=1)
    median = float(np.median(furthest))

    bounded = orch.run(
        "SparseTriangulationGTSAM", run_id="rc", inputs=common,
        params={"max_landmark_distance": median},
    ).primary

    assert bounded.metric("point_count") < unbounded.metric("point_count")
    assert bounded.metric("rejected_distance") > 0
    assert unbounded.metric("rejected_distance") == 0
