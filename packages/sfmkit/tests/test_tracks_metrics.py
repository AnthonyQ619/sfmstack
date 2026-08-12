"""`split_rate` -- the dual of `inconsistent_rate`, shared so it is comparable.

The tolerance and the two-frame rule are fixed by the type rather than by the
module, so what these tests pin down is the DEFINITION: a metric each tracker
tuned for itself would not be comparable to the one beside it, which is the whole
reason it lives in sfmkit.
"""

import numpy as np
import pytest

from sfmkit import SPLIT_TOLERANCE_PX, split_rate


def track(tid, positions):
    """positions: {frame: (x, y)}"""
    return [[tid, f, x, y] for f, (x, y) in positions.items()]


def test_distinct_tracks_do_not_count_as_split():
    obs = np.array(
        track(0, {0: (10, 10), 1: (11, 11)})
        + track(1, {0: (90, 90), 1: (91, 91)})
    )
    assert split_rate(obs) == 0.0


def test_one_point_left_in_two_tracks_is_caught():
    obs = np.array(
        track(0, {0: (10, 10), 1: (20, 20)})
        + track(1, {0: (10.5, 10.2), 1: (20.4, 20.3)})
    )
    assert split_rate(obs) == pytest.approx(0.5)


def test_coincidence_in_a_single_frame_is_not_evidence():
    """On a dense detector two distinct keypoints within two pixels in ONE view is
    ordinary. The same pair landing together in two views is not."""
    obs = np.array(
        track(0, {0: (10, 10), 1: (20, 20), 2: (30, 30)})
        + track(1, {0: (10.5, 10.2), 1: (80, 80), 2: (90, 90)})
    )
    assert split_rate(obs) == 0.0


def test_a_track_seen_twice_in_one_frame_is_not_this_metrics_business():
    """That is inconsistent_rate. A self-contradictory track must not also be
    reported as split, or the two metrics stop being independent."""
    obs = np.array([[0, 0, 10.0, 10.0], [0, 0, 10.4, 10.1], [0, 1, 20.0, 20.0]])
    assert split_rate(obs) == 0.0


def test_the_tolerance_is_a_real_boundary():
    inside = np.array(
        track(0, {0: (10, 10), 1: (20, 20)})
        + track(1, {0: (10 + SPLIT_TOLERANCE_PX * 0.5, 10), 1: (20, 20)})
    )
    outside = np.array(
        track(0, {0: (10, 10), 1: (20, 20)})
        + track(1, {0: (10 + SPLIT_TOLERANCE_PX * 2, 10),
                    1: (20 + SPLIT_TOLERANCE_PX * 2, 20)})
    )
    assert split_rate(inside) > 0
    assert split_rate(outside) == 0.0


def test_three_way_split_counts_two_merges_not_three():
    """Union-find semantics: N tracks that are one point cost N-1 merges, so the
    rate is (N-1)/total rather than N/total."""
    positions = {0: (10, 10), 1: (20, 20)}
    obs = np.array(
        track(0, positions)
        + track(1, {f: (x + 0.3, y) for f, (x, y) in positions.items()})
        + track(2, {f: (x + 0.6, y) for f, (x, y) in positions.items()})
        + track(3, {0: (90, 90), 1: (91, 91)})
    )
    assert split_rate(obs) == pytest.approx(0.5)  # 2 merges over 4 tracks


def test_an_empty_table_is_zero_not_an_error():
    assert split_rate(np.zeros((0, 4))) == 0.0


def test_a_single_track_is_zero():
    assert split_rate(np.array(track(0, {0: (1, 1), 1: (2, 2)}))) == 0.0


def test_track_count_is_taken_from_the_caller_when_given():
    """tracks/v1 carries track_count separately, and a table whose highest id is
    unused would otherwise report a rate against the wrong denominator."""
    obs = np.array(track(0, {0: (1, 1), 1: (2, 2)}) + track(1, {0: (1.2, 1), 1: (2.1, 2)}))
    assert split_rate(obs, track_count=4) == pytest.approx(0.25)
    assert split_rate(obs) == pytest.approx(0.5)


def test_a_malformed_table_is_refused():
    with pytest.raises(ValueError):
        split_rate(np.zeros((5, 2)))
