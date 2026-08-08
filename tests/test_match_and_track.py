"""FeatureMatchNN and FeatureTrackUnionFind.

Split from test_real_modules because half of this needs no dataset and no
Pillow: the tracker consumes only a scene and a match set, both of which are
cheap to hand-build, and the cases worth pinning hardest -- contradictory tracks,
the detector-free merge path -- are ones real data produces too rarely to rely on.
"""

import numpy as np
import pytest

from dataset_paths import DTU_CALIB, DTU_SCAN1, needs_cv2, needs_dtu, needs_pil
from sfmorch import ExecutionError


# --------------------------------------------------------------------------- #
# Hand-built artifacts
# --------------------------------------------------------------------------- #


def fake_scene(store, n_images: int, size: int = 640):
    """A scene with no images behind it. Enough for anything that only needs
    frame count and names."""
    w = store.writer(artifact_id=f"scene-{n_images}", type="scene/v1", run="t")
    w.save(
        "images",
        paths=np.array([f"/nowhere/{i:03d}.png" for i in range(n_images)]),
        names=np.array([f"{i:03d}.png" for i in range(n_images)]),
        size_original=np.full((n_images, 2), size, np.int32),
        size_current=np.full((n_images, 2), size, np.int32),
        scale=np.ones((n_images, 2), np.float32),
        content_hash=np.array("fake"),
    )
    return w.seal()


def fake_matches(store, scene, pairs, rows, *, with_feature_index=True, aid="m"):
    """`rows` is (pair_row, xa, ya, xb, yb, feat_a, feat_b) per correspondence."""
    w = store.writer(
        artifact_id=aid, type="pairwise_matches/v1", run="t", scene=scene.id
    )
    w.save("pairs", image_pair=np.array(pairs, np.int32))
    arrays = {
        "xy": np.array([r[1:5] for r in rows], np.float32),
        "pair_index": np.array([r[0] for r in rows], np.int32),
    }
    if with_feature_index:
        arrays["feature_index"] = np.array([r[5:7] for r in rows], np.int32)
    w.save("matches", **arrays)
    return w.seal()


def tracks_by_id(art):
    obs = art.load("observations", "obs")
    return {
        int(t): obs[obs[:, 0] == t][:, 1:] for t in np.unique(obs[:, 0])
    }


# --------------------------------------------------------------------------- #
# Tracker: contradictory tracks
# --------------------------------------------------------------------------- #
#
# Three images. Features 0 and 1 both live in image 0, feature 10 in image 1,
# feature 20 in image 2. The chain 0-10, 10-20, 1-20 merges all four into one
# group, which therefore claims image 0 twice -- a scene point that projects to
# two places in one view. At least one of those three matches is wrong.
#
# Features 2, 11, 22 form a clean three-view track alongside it.

CONFLICT_PAIRS = [(0, 1), (1, 2), (0, 2)]
CONFLICT_ROWS = [
    (0, 10.0, 10.0, 50.0, 50.0, 0, 10),    # img0 f0  <-> img1 f10
    (1, 50.0, 50.0, 90.0, 90.0, 10, 20),   # img1 f10 <-> img2 f20
    (2, 11.0, 99.0, 90.0, 90.0, 1, 20),    # img0 f1  <-> img2 f20   << contradiction
    (0, 20.0, 20.0, 60.0, 60.0, 2, 11),    # clean track
    (1, 60.0, 60.0, 80.0, 80.0, 11, 22),
]


@pytest.fixture
def conflict_setup(orch):
    scene = fake_scene(orch.store, 3)
    matches = fake_matches(orch.store, scene, CONFLICT_PAIRS, CONFLICT_ROWS)
    return scene, matches


def run_tracker(orch, scene, matches, **params):
    return orch.run(
        "FeatureTrackUnionFind",
        run_id="t",
        inputs={"scene": scene.id, "matches": matches.id},
        params=params,
    ).primary


def test_a_contradictory_track_is_detected(conflict_setup, orch):
    scene, matches = conflict_setup
    tracks = run_tracker(orch, scene, matches)
    # Two groups merged, one of them self-contradictory.
    assert tracks.metric("inconsistent_rate") == 0.5


def test_drop_discards_the_whole_contradictory_track(conflict_setup, orch):
    scene, matches = conflict_setup
    tracks = run_tracker(orch, scene, matches, on_conflict="drop")

    assert tracks.metric("track_count") == 1
    only = tracks_by_id(tracks)[0]
    assert sorted(only[:, 0].tolist()) == [0.0, 1.0, 2.0]


def test_first_salvages_it_by_keeping_one_observation_per_frame(conflict_setup, orch):
    scene, matches = conflict_setup
    tracks = run_tracker(orch, scene, matches, on_conflict="first")

    assert tracks.metric("track_count") == 2
    for obs in tracks_by_id(tracks).values():
        frames = obs[:, 0]
        assert len(np.unique(frames)) == len(frames)


@needs_dtu
@needs_cv2
@needs_pil
def test_no_surviving_track_ever_claims_a_frame_twice(orch):
    """The invariant the predecessor violated silently by letting the last write
    win. Checked on real data, where the merge is deep enough to matter."""
    _, _, _, tracks = dtu_pipeline(orch, matcher={"pairing": "exhaustive"})
    obs = tracks.load("observations", "obs")

    pairs = obs[:, :2]
    assert len(np.unique(pairs, axis=0)) == len(pairs)


# --------------------------------------------------------------------------- #
# Tracker: the detector-free merge path
# --------------------------------------------------------------------------- #


def test_matches_without_feature_index_merge_by_proximity(orch):
    """LoFTR and RoMa cite no keypoint table. Endpoints within merge_eps_px of
    each other in the same frame have to be treated as the same feature, or
    nothing chains past a single pair."""
    scene = fake_scene(orch.store, 3)
    rows = [
        (0, 10.0, 10.0, 50.0, 50.0, -1, -1),
        # 50.4,50.3 is the same physical point as 50.0,50.0 seen by a second pair
        (1, 50.4, 50.3, 90.0, 90.0, -1, -1),
    ]
    matches = fake_matches(orch.store, scene, [(0, 1), (1, 2)], rows,
                           with_feature_index=False)

    merged = run_tracker(orch, scene, matches, merge_eps_px=1.5)
    assert merged.metric("track_count") == 1
    assert merged.metric("max_track_length") == 3

    # Below the endpoint separation, the two pairs stay unrelated.
    split = run_tracker(orch, scene, matches, merge_eps_px=0.1)
    assert split.metric("track_count") == 2
    assert split.metric("max_track_length") == 2


def test_detector_free_input_with_no_merge_tolerance_is_refused(orch):
    scene = fake_scene(orch.store, 2)
    matches = fake_matches(
        orch.store, scene, [(0, 1)], [(0, 1.0, 1.0, 2.0, 2.0, -1, -1)],
        with_feature_index=False,
    )
    with pytest.raises(ExecutionError, match="merge_eps_px"):
        run_tracker(orch, scene, matches, merge_eps_px=0.0)


def test_min_track_len_filters_and_says_so_when_nothing_survives(orch):
    scene = fake_scene(orch.store, 3)
    matches = fake_matches(orch.store, scene, CONFLICT_PAIRS, CONFLICT_ROWS)

    assert run_tracker(orch, scene, matches, min_track_len=3).metric("track_count") == 1
    with pytest.raises(ExecutionError, match="min_track_len"):
        run_tracker(orch, scene, matches, min_track_len=4)


# --------------------------------------------------------------------------- #
# Matcher and tracker on real images
# --------------------------------------------------------------------------- #


def dtu_pipeline(orch, *, n=12, matcher=None, tracker=None):
    scene = orch.run(
        "SceneLoader",
        run_id="mt",
        params={
            "image_dir": str(DTU_SCAN1),
            "calibration_path": str(DTU_CALIB),
            "max_images": n,
            "resize": "auto",
            "max_edge": 1024,
        },
    ).primary
    features = orch.run(
        "FeatureDetectionSIFT", run_id="mt", inputs={"scene": scene.id}
    ).primary
    matches = orch.run(
        "FeatureMatchNN",
        run_id="mt",
        inputs={"scene": scene.id, "features": features.id},
        params=matcher or {"pairing": "sequential", "window": 4},
    ).primary
    tracks = orch.run(
        "FeatureTrackUnionFind",
        run_id="mt",
        inputs={"scene": scene.id, "matches": matches.id},
        params=tracker or {},
    ).primary
    return scene, features, matches, tracks


pytestmark_real = [needs_dtu, needs_cv2, needs_pil]


@needs_dtu
@needs_cv2
@needs_pil
def test_the_whole_chain_runs_end_to_end(orch):
    scene, features, matches, tracks = dtu_pipeline(orch)

    assert matches.type == "pairwise_matches/v1"
    assert tracks.type == "tracks/v1"
    assert matches.metric("pairs_matched") > 0
    assert tracks.metric("track_count") > 200


@needs_dtu
@needs_cv2
@needs_pil
def test_feature_index_points_at_the_keypoint_that_was_matched(orch):
    """The tracker merges on feature_index alone, so if it disagreed with xy the
    tracks would be built from correct-looking coordinates on wrong features."""
    _, features, matches, _ = dtu_pipeline(orch)

    kp = features.load("keypoints", "xy")
    xy = matches.load("matches", "xy")
    fi = matches.load("matches", "feature_index")

    assert np.allclose(kp[fi[:, 0]], xy[:, :2])
    assert np.allclose(kp[fi[:, 1]], xy[:, 2:])


@needs_dtu
@needs_cv2
@needs_pil
def test_matched_features_belong_to_the_pair_they_are_filed_under(orch):
    _, features, matches, _ = dtu_pipeline(orch)

    image_index = features.load("keypoints", "image_index")
    image_pair = matches.load("pairs", "image_pair")
    fi = matches.load("matches", "feature_index")
    pi = matches.load("matches", "pair_index")

    assert (image_index[fi[:, 0]] == image_pair[pi, 0]).all()
    assert (image_index[fi[:, 1]] == image_pair[pi, 1]).all()


@needs_dtu
@needs_cv2
@needs_pil
def test_widening_the_window_repairs_a_broken_view_graph(orch):
    """The first gradient step in tuning.md, pinned. Uniformly sampling 12 of
    DTU scan1's 49 images spreads the baseline far enough that window 2 leaves
    the set in two halves."""
    _, _, narrow, narrow_tracks = dtu_pipeline(orch, matcher={"window": 2})
    _, _, wide, wide_tracks = dtu_pipeline(orch, matcher={"window": 4})

    assert narrow.metric("graph_components") > 1
    assert "broken_chain" in [d.code for d in narrow.manifest.diagnostics]

    assert wide.metric("graph_components") == 1
    assert wide.metric("largest_component_fraction") == 1.0
    assert "broken_chain" not in [d.code for d in wide.manifest.diagnostics]

    # And the point of repairing it: tracks reach further.
    assert wide_tracks.metric("long_track_fraction") > narrow_tracks.metric(
        "long_track_fraction"
    )


@needs_dtu
@needs_cv2
@needs_pil
def test_exhaustive_pairing_attempts_every_pair(orch):
    _, _, matches, _ = dtu_pipeline(orch, n=8, matcher={"pairing": "exhaustive"})
    kept = matches.metric("pairs_matched") + matches.metric("weak_pairs")
    assert kept == 8 * 7 // 2


@needs_dtu
@needs_cv2
@needs_pil
def test_geometric_verification_is_what_rejects_the_bad_matches(orch):
    """The diagnostic move documented under `geometric_model: none` -- it tells
    you whether verification is discarding good matches or the matcher never
    produced any.

    Compared on TOTAL correspondences, not on matches_per_pair. Turning
    verification off also lets thin pairs clear min_matches, so the pair set
    grows and the mean per pair can fall even as the total rises."""
    common = {"pairing": "sequential", "window": 4}
    _, _, verified, _ = dtu_pipeline(orch, matcher={**common, "geometric_model": "fundamental"})
    _, _, raw, _ = dtu_pipeline(orch, matcher={**common, "geometric_model": "none"})

    assert len(raw.load("matches", "xy")) > len(verified.load("matches", "xy"))
    assert raw.metric("pairs_matched") >= verified.metric("pairs_matched")
    assert raw.metric("inlier_ratio") == 1.0


@needs_dtu
@needs_cv2
@needs_pil
def test_the_mutual_check_removes_matches_the_ratio_test_admitted(orch):
    _, _, both, _ = dtu_pipeline(orch, matcher={"mutual": True})
    _, _, one_way, _ = dtu_pipeline(orch, matcher={"mutual": False})

    assert one_way.metric("matches_per_pair") > both.metric("matches_per_pair")


@needs_dtu
@needs_cv2
@needs_pil
def test_an_impossible_min_matches_fails_with_the_numbers_needed_to_fix_it(orch):
    with pytest.raises(ExecutionError, match="best raw match count"):
        dtu_pipeline(orch, n=6, matcher={"min_matches": 1000})


@needs_dtu
@needs_cv2
@needs_pil
def test_track_observations_are_the_coordinates_the_matcher_produced(orch):
    _, _, matches, tracks = dtu_pipeline(orch)

    xy = matches.load("matches", "xy")
    endpoints = {(round(float(x), 3), round(float(y), 3))
                 for x, y in np.vstack([xy[:, :2], xy[:, 2:]])}
    obs = tracks.load("observations", "obs")
    sample = obs[:: max(1, len(obs) // 200)]

    for row in sample:
        assert (round(float(row[2]), 3), round(float(row[3]), 3)) in endpoints
