"""The error rung is an angle, and the comparison helpers split error by support."""
import numpy as np

from sfmorch.health import (components, error_by_support, paired_error_by_support,
                            rotation_agreement)


class Art:
    def __init__(self, groups):
        self.groups = groups

    def load(self, group, name=None):
        return self.groups[group] if name is None else self.groups[group][name]


def _model(point_error, track_id=None, yaw_deg=0.0):
    """Three cameras, four points each seen by all three."""
    def R(deg):
        t = np.radians(deg)
        return np.array([[np.cos(t), 0, np.sin(t)], [0, 1, 0], [-np.sin(t), 0, np.cos(t)]])
    cams = np.stack([np.hstack([R(a), np.array([[a / 10.0], [0], [5.0]])])
                     for a in (0.0, 10.0 + yaw_deg, 20.0)])
    xyz = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0]], dtype=float)
    obs = np.array([[f, p, 800.0 + p, 600.0] for f in range(3) for p in range(4)])
    points = {"xyz": xyz, "error": np.asarray(point_error, dtype=float)}
    if track_id is not None:
        points["track_id"] = np.asarray(track_id)
    return Art({"points": points, "observations": {"obs": obs},
                "poses": {"cam_from_world": cams, "valid": np.ones(3, bool),
                          "image_index": np.arange(3)}})


def _scene(f):
    K = np.array([[f, 0, 800], [0, f, 600], [0, 0, 1]], dtype=float)
    return Art({"calibration": {"intrinsics": np.stack([K] * 3)},
                "images": {"size_current": np.array([[1600, 1200]] * 3)}})


def test_the_error_rung_is_pixels_over_focal_length_in_milliradians():
    c = components(_model([0.5, 0.5, 0.5, 0.5]), scene=_scene(1000.0))
    assert c["error_px"] == 0.5
    assert abs(c["error"] - 0.5) < 1e-9          # 0.5 px at f=1000 px is 0.5 mrad
    c = components(_model([0.5, 0.5, 0.5, 0.5]), scene=_scene(500.0))
    assert abs(c["error"] - 1.0) < 1e-9          # the same pixels at half the focal


def test_the_error_rung_is_unevaluable_without_calibration():
    c = components(_model([0.5] * 4), scene=None)
    assert c["error"] is None and c["error_px"] == 0.5


def test_error_is_split_by_how_many_views_see_each_point():
    split = error_by_support(_model([0.1, 0.2, 0.3, 0.4]))
    assert split["3"] == {"points": 4, "median_px": 0.25}
    assert split["2"]["points"] == 0 and split["5+"]["points"] == 0


def test_a_paired_difference_joins_on_track_id():
    a = _model([0.5, 0.5, 0.5, 0.5], track_id=[10, 11, 12, 13])
    b = _model([0.25, 0.25, 0.25, 9.9], track_id=[10, 11, 12, 99])
    paired = paired_error_by_support(a, b)
    assert paired["shared_points"] == 3
    assert paired["3"] == {"points": 3, "median_diff_px": 0.25}


def test_rotation_agreement_is_zero_for_one_model_and_sees_a_turned_camera():
    a = _model([0.1] * 4)
    assert rotation_agreement(a, a)["median_deg"] == 0.0
    turned = rotation_agreement(a, _model([0.1] * 4, yaw_deg=2.0))
    assert turned["shared_cameras"] == 3 and abs(turned["median_deg"] - 2.0) < 1e-6
