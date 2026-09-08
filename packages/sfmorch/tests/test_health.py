"""The health profile's rungs, tested against the properties they are FOR.

Each rung was chosen for a specific reason argued in skills/health/ladder.md --
scene-size invariance, resistance to a particular way of flattering a model.
These tests check those properties directly, because a rung that quietly loses
its property is worse than no rung: it still reports a number.
"""

import numpy as np
import pytest

from sfmorch.health import (
    coverage, pose_agreement, track_lengths, triangulation_angles,
)


def _looking_at_origin(centre):
    """A camera at `centre` looking at the origin, as cam_from_world 3x4."""
    f = -np.asarray(centre, dtype=float)
    f /= np.linalg.norm(f)
    up = np.array([0.0, 0.0, 1.0])
    if abs(f @ up) > 0.9:
        up = np.array([0.0, 1.0, 0.0])
    r = np.cross(up, f)
    r /= np.linalg.norm(r)
    u = np.cross(f, r)
    R = np.vstack([r, u, f])
    return np.hstack([R, (-R @ np.asarray(centre, dtype=float)).reshape(3, 1)])


def test_track_lengths_counts_observations_per_point():
    obs = np.array([[0, 0, 1, 1], [1, 0, 2, 2], [2, 0, 3, 3], [0, 1, 4, 4]],
                   dtype=float)
    assert list(track_lengths(obs, 2)) == [3, 1]


def test_triangulation_angle_is_the_widest_pair_not_the_mean():
    """A point triangulated from a mediocre pair can still be conditioned by a
    third view, so the rung reads the widest angle available."""
    xyz = np.array([[0.0, 0.0, 0.0]])
    centres = [(1.0, 0.0, 0.0), (0.9999, 0.0143, 0.0), (0.0, 1.0, 0.0)]
    cams = np.stack([_looking_at_origin(c) for c in centres])
    obs = np.array([[0, 0, 0, 0], [1, 0, 0, 0], [2, 0, 0, 0]], dtype=float)

    angle = triangulation_angles(xyz, obs, cams, np.ones(3, bool), np.arange(3))
    # Two of the three rays are nearly coincident; the widest pair is ~90 deg,
    # and a mean over pairs would be dragged far below it.
    assert angle[0] == pytest.approx(90.0, abs=1.0)


def test_coverage_measures_evenness_not_totals():
    """A frame can carry many observations in one corner and be the frame the
    next stage fails on. The rung must not reward the pile."""
    sizes = np.array([[80, 80]])
    clustered = np.array([[0, i, 1.0 + i * 0.01, 1.0] for i in range(200)])
    spread = np.array([[0, i, 5.0 + (i % 8) * 10, 5.0 + (i // 8) * 10]
                       for i in range(64)])

    assert coverage(clustered, sizes, {0}, grid=8) < 0.05
    assert coverage(spread, sizes, {0}, grid=8) == pytest.approx(1.0)
    assert len(clustered) > len(spread), "the worse frame has MORE observations"


def test_pose_agreement_sees_drift_that_reprojects_cleanly():
    """The rung exists because a self-consistently wrong pose set produces
    structure that reprojects beautifully. It compares the model's relative
    rotations against the two-view estimates and never touches the points."""
    cams = np.stack([_looking_at_origin(c) for c in
                     [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0)]])
    image_index, valid = np.arange(2), np.ones(2, bool)

    R_true = cams[1][:, :3] @ cams[0][:, :3].T
    t_true = cams[1][:, 3] - R_true @ cams[0][:, 3]

    agreed, _, edges = pose_agreement(cams, valid, image_index,
                                      {(0, 1): (R_true, t_true)})
    assert edges == 1
    assert agreed == pytest.approx(0.0, abs=1e-6)

    # A five-degree error in the two-view estimate reads as five degrees.
    c, s = np.cos(np.radians(5)), np.sin(np.radians(5))
    tilt = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])
    drifted, _, _ = pose_agreement(cams, valid, image_index,
                                   {(0, 1): (tilt @ R_true, t_true)})
    assert drifted == pytest.approx(5.0, abs=1e-6)


def test_pose_agreement_ignores_translation_scale():
    """Translation is compared as a DIRECTION, so a model in different units
    from the two-view estimate is not reported as disagreeing."""
    cams = np.stack([_looking_at_origin(c) for c in
                     [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0)]])
    R = cams[1][:, :3] @ cams[0][:, :3].T
    t = cams[1][:, 3] - R @ cams[0][:, 3]

    _, scaled_deg, _ = pose_agreement(cams, np.ones(2, bool), np.arange(2),
                                      {(0, 1): (R, t * 37.0)})
    # arccos has an infinite derivative at 1, so an exact-agreement reading
    # carries a few millionths of a degree of numerical noise. Anything below a
    # thousandth of a degree is agreement by any standard this rung is read at.
    assert scaled_deg == pytest.approx(0.0, abs=1e-3)


def test_a_rung_reports_nothing_rather_than_guessing_when_it_cannot_be_read():
    """No pairs to compare means no reading. The digest reports that as absent
    rather than as a healthy zero."""
    cams = np.stack([_looking_at_origin((1.0, 0.0, 0.0))])
    rot, trn, edges = pose_agreement(cams, np.ones(1, bool), np.arange(1), {})
    assert edges == 0
    assert np.isnan(rot) and np.isnan(trn)
