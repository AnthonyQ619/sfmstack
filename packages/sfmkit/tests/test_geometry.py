"""`trifocal_transfer` -- the only tracker metric that measures position.

Tested against synthetic scenes with known noise, because that is the only way to
know a *metric* is calibrated: on real data there is nothing to compare it to, which
is the whole reason the metric exists.
"""

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2", reason="trifocal_transfer needs OpenCV")

from sfmkit import scene_intrinsics, trifocal_transfer  # noqa: E402

K = np.array([[900.0, 0.0, 512.0], [0.0, 900.0, 384.0], [0.0, 0.0, 1.0]])


def arc_scene(n_points=800, n_frames=8, sigma=0.0, seed=0, outlier_fraction=0.0):
    """Cameras on an arc looking at a point cloud. Returns (obs, K_all)."""
    rng = np.random.default_rng(seed)
    X = rng.normal(0, 1, (n_points, 3))
    X[:, 2] += 6.0

    rows = []
    for f in range(n_frames):
        a = 0.25 * f
        R = np.array([[np.cos(a), 0, np.sin(a)], [0, 1, 0], [-np.sin(a), 0, np.cos(a)]])
        C = np.array([2.5 * np.sin(a), 0.0, 6 - 6 * np.cos(a)])
        cam = (R @ X.T).T - R @ C
        uv = np.stack([cam[:, 0] / cam[:, 2] * K[0, 0] + K[0, 2],
                       cam[:, 1] / cam[:, 2] * K[1, 1] + K[1, 2]], axis=1)
        if sigma:
            uv = uv + rng.normal(0, sigma, uv.shape)
        for n in range(n_points):
            rows.append([n, f, uv[n, 0], uv[n, 1]])

    obs = np.array(rows, dtype=np.float64)

    if outlier_fraction:
        # Displace a share of observations far enough that no geometry explains
        # them -- the failure the metric exists to see.
        pick = rng.choice(len(obs), int(outlier_fraction * len(obs)), replace=False)
        obs[pick, 2:4] += rng.normal(0, 40.0, (len(pick), 2))

    return obs, np.repeat(K[None], n_frames, axis=0)


def test_perfect_observations_measure_essentially_zero(tmp_path):
    obs, K_all = arc_scene(sigma=0.0)
    median, n, triples = trifocal_transfer(obs, K_all)

    assert median < 0.02
    assert n > 0 and triples > 0


@pytest.mark.parametrize("sigma", [0.3, 1.0, 3.0])
def test_it_grows_with_observation_noise(sigma):
    clean, K_all = arc_scene(sigma=0.0)
    noisy, _ = arc_scene(sigma=sigma)

    assert trifocal_transfer(noisy, K_all)[0] > trifocal_transfer(clean, K_all)[0]


def test_it_is_monotonic_in_noise():
    """A metric that is merely nonzero on bad data cannot rank two trackers. This
    is the property that lets it."""
    K_all = arc_scene()[1]
    readings = [trifocal_transfer(arc_scene(sigma=s)[0], K_all)[0]
                for s in (0.0, 0.5, 1.0, 2.0, 4.0)]
    assert readings == sorted(readings)


def test_outliers_move_it_even_at_low_noise():
    """The failure it exists for: correspondences that are individually plausible
    and do not correspond to one 3D point."""
    K_all = arc_scene()[1]
    clean = trifocal_transfer(arc_scene(sigma=0.2)[0], K_all)[0]
    dirty = trifocal_transfer(arc_scene(sigma=0.2, outlier_fraction=0.25)[0], K_all)[0]
    assert dirty > clean * 2


def test_it_is_deterministic():
    """The triples are sampled. A metric that moves between two runs of the same
    recipe is not a metric, and artifact ids do not capture random state."""
    obs, K_all = arc_scene(sigma=1.0)
    assert trifocal_transfer(obs, K_all) == trifocal_transfer(obs, K_all)


def test_fewer_than_three_frames_is_null_not_an_error():
    obs, K_all = arc_scene(n_frames=2)
    assert trifocal_transfer(obs, K_all[:2]) == (None, 0, 0)


def test_an_empty_table_is_null():
    assert trifocal_transfer(np.zeros((0, 4)), np.repeat(K[None], 3, 0)) == (None, 0, 0)


def test_too_few_shared_tracks_is_null_and_says_so():
    """Null because the table has no three-view structure to check -- which is a
    statement about the tracker, not a failure of the metric."""
    obs, K_all = arc_scene(n_points=10)
    median, n, triples = trifocal_transfer(obs, K_all)
    assert median is None and triples == 0


def test_it_holds_out_the_measured_observations():
    """If the third view's observations were used to place the camera, corrupting
    only the held-out half would not move the number. It does."""
    obs, K_all = arc_scene(sigma=0.0, n_points=400)
    baseline = trifocal_transfer(obs, K_all)[0]

    corrupted = obs.copy()
    # Every observation of the second half of the tracks, in every frame.
    mask = corrupted[:, 0] >= 200
    rng = np.random.default_rng(1)
    corrupted[mask, 2:4] += rng.normal(0, 5.0, (int(mask.sum()), 2))

    assert trifocal_transfer(corrupted, K_all)[0] > baseline * 20


def test_scene_intrinsics_expands_a_single_shared_camera():
    class FakeScene:
        def has(self, name):
            return name == "calibration"

        def load(self, name):
            return {"intrinsics": K[None], "camera_index": None}

    K_all = scene_intrinsics(FakeScene(), 5)
    assert K_all.shape == (5, 3, 3)
    assert np.allclose(K_all[3], K)


def test_scene_intrinsics_is_none_on_an_uncalibrated_scene():
    class FakeScene:
        def has(self, name):
            return False

    assert scene_intrinsics(FakeScene(), 5) is None
