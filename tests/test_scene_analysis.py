"""SceneTriage and SceneMotion.

The two degeneracy tests get synthetic coverage rather than dataset coverage, and
deliberately: none of the scenes on this machine is planar or rotational, so a
test against real data would confirm the detectors stay silent and say nothing
about whether they fire. A homography built from a known R and a known plane is
the only place their sensitivity is checkable at all.
"""

import importlib.util
from pathlib import Path

import numpy as np
import pytest

from dataset_paths import (
    DTU_CALIB,
    DTU_SCAN1,
    MODULES,
    RAFT_CHECKPOINT,
    needs_cv2,
    needs_dtu,
    needs_pil,
    needs_raft,
    needs_torch,
)

pytestmark = [needs_pil]


def _adapter(module_dir: str):
    """Import a module's adapter directly, without the container.

    Adapters are not importable as packages -- they live at modules/<x>/adapter.py
    and are loaded by path in the container too.
    """
    path = MODULES / module_dir / "adapter.py"
    spec = importlib.util.spec_from_file_location(f"{module_dir}_adapter", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_dtu(orch, **overrides):
    params = {
        "image_dir": str(DTU_SCAN1),
        "calibration_path": str(DTU_CALIB),
        "max_images": 6,
        "sampling": "head",
        "resize": "auto",
        "max_edge": 640,
    }
    params.update(overrides)
    # An optional parameter is dropped, not passed as null: `resolve` refuses an
    # explicit None because omission is how "not supplied" is expressed.
    params = {k: v for k, v in params.items() if v is not None}
    return orch.run("SceneLoader", run_id="analysis", params=params).primary


def rotation_about_y(deg: float) -> np.ndarray:
    t = np.radians(deg)
    c, s = np.cos(t), np.sin(t)
    return np.array([[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]])


K = np.array([[800.0, 0.0, 320.0], [0.0, 800.0, 240.0], [0.0, 0.0, 1.0]])


# --------------------------------------------------------------------------- #
# The degeneracy discriminator
# --------------------------------------------------------------------------- #


@needs_torch
@pytest.mark.parametrize("degrees", [2.0, 8.0, 20.0])
def test_a_pure_rotation_homography_conjugates_to_a_rotation(degrees):
    """`K^-1 H K` is exactly a rotation when the camera only turned.

    This is the entire basis on which a pure rotation is told apart from a planar
    scene, and both look identical to every other measurement in the module.
    """
    motion = _adapter("scene_motion")
    H = K @ rotation_about_y(degrees) @ np.linalg.inv(K)
    assert motion.rotation_residual(H, K, K) < 1e-9


@needs_torch
def test_a_translating_camera_over_a_plane_does_not():
    """The same homography form with a baseline, which must NOT read as rotation.

    The residual grows with the baseline-to-depth ratio, which is what makes
    `rotation_only_tol` interpretable as a ratio rather than as an arbitrary
    number -- see the module's limitations.md.
    """
    motion = _adapter("scene_motion")
    normal = np.array([[0.0, 0.0, 1.0]]).T
    R = rotation_about_y(8.0)

    residuals = []
    for baseline in (0.02, 0.10, 0.50):
        t = np.array([[baseline, 0.0, 0.0]]).T
        H = K @ (R + t @ normal.T) @ np.linalg.inv(K)
        residuals.append(motion.rotation_residual(H, K, K))

    # Monotone in the baseline, and past the default tolerance once the
    # translation is a tenth of the scene depth.
    assert residuals == sorted(residuals)
    assert residuals[0] < 0.15  # 2% baseline: correctly indistinguishable
    assert residuals[1] >= 0.10  # 10% baseline: at the default cut
    assert residuals[2] > 0.5  # 50% baseline: unambiguous


@needs_torch
def test_gric_prefers_a_homography_on_a_plane_and_a_fundamental_otherwise():
    """The model-selection half of the same question.

    A fundamental matrix fits everything a homography fits and more, so on
    residuals alone it never loses. GRIC charges it for the extra dimension, and
    this is the test that the charge is enough to matter.
    """
    motion = _adapter("scene_motion")
    rng = np.random.default_rng(0)
    n = 400

    # Points on a plane, mapped exactly by one homography.
    p1 = rng.uniform([0, 0], [640, 480], size=(n, 2))
    H = K @ (rotation_about_y(5.0) + np.array([[0.1, 0.0, 0.0]]).T
             @ np.array([[0.0, 0.0, 1.0]])) @ np.linalg.inv(K)
    homogeneous = np.concatenate([p1, np.ones((n, 1))], axis=1) @ H.T
    p2 = homogeneous[:, :2] / homogeneous[:, 2:3]

    planar_h = motion.gric(motion.homography_errors_sq(H, p1, p2), 1.5, d=2, k=8)

    # The same points with depth-dependent parallax added, which no single
    # homography can absorb.
    depth = rng.uniform(1.0, 6.0, size=(n, 1))
    p2_general = p2 + 40.0 / depth * rng.normal(size=(n, 2)).clip(-1, 1)
    general_h = motion.gric(
        motion.homography_errors_sq(H, p1, p2_general), 1.5, d=2, k=8
    )

    assert planar_h < general_h


# --------------------------------------------------------------------------- #
# SceneTriage
# --------------------------------------------------------------------------- #


@needs_cv2
def test_filename_ordering_is_a_heuristic_that_knows_its_own_limits():
    triage = _adapter("scene_triage")
    assert triage.filenames_are_ordered(["0001.jpg", "0002.jpg", "0003.jpg"])
    assert triage.filenames_are_ordered(["DSC_0287.JPG", "DSC_0288.JPG"])
    # No digits at all: the one answer the heuristic is confident about.
    assert not triage.filenames_are_ordered(["eiffel_by_jane.jpg", "tower_dusk.jpg"])
    # Numbered but implausibly sparse -- an id, not a capture index.
    assert not triage.filenames_are_ordered(["img_1.jpg", "img_900.jpg", "img_9001.jpg"])


@needs_dtu
@needs_cv2
def test_scene_triage_fills_three_groups_of_the_analysis_type(orch):
    scene = load_dtu(orch)
    art = orch.run("SceneTriage", run_id="analysis", inputs={"scene": scene.id}).primary

    assert art.type == "scene_analysis/v1"
    assert {"metadata", "photometric", "texture"} <= set(art.manifest.files)
    # The two groups the flow module owns; a partial producer leaves them absent
    # rather than writing zeros.
    assert "motion" not in art.manifest.files
    assert "degeneracy" not in art.manifest.files

    assert int(art.load("metadata", "n_images")) == 6
    assert 0.0 <= float(art.load("photometric", "combined_change")) <= 1.0
    assert art.load("texture", "sharpness").shape == (6,)


@needs_dtu
@needs_cv2
def test_the_per_pair_series_rides_along_as_a_recorded_extra(orch):
    """Arrays outside the schema are legal and must be discoverable, not silent."""
    scene = load_dtu(orch)
    art = orch.run("SceneTriage", run_id="analysis", inputs={"scene": scene.id}).primary

    assert art.manifest.extras["photometric"] == ["pair_combined", "pair_index"]
    assert len(art.load("photometric", "pair_combined")) == 5  # consecutive pairs


@needs_dtu
@needs_cv2
def test_exhaustive_pairing_compares_more_pairs_and_is_a_separate_artifact(orch):
    scene = load_dtu(orch)
    consecutive = orch.run(
        "SceneTriage", run_id="analysis", inputs={"scene": scene.id}
    ).primary
    exhaustive = orch.run(
        "SceneTriage", run_id="analysis", inputs={"scene": scene.id},
        params={"pairing": "all"},
    ).primary

    assert consecutive.id != exhaustive.id
    assert len(exhaustive.load("photometric", "pair_combined")) == 15  # 6 choose 2
    assert len(consecutive.load("photometric", "pair_combined")) == 5


# --------------------------------------------------------------------------- #
# SceneMotion
# --------------------------------------------------------------------------- #


@needs_dtu
@needs_cv2
@needs_torch
@needs_raft
def test_scene_motion_fills_the_other_two_groups(orch, monkeypatch):
    monkeypatch.setenv("RAFT_CHECKPOINT", str(RAFT_CHECKPOINT))
    scene = load_dtu(orch)
    art = orch.run("SceneMotion", run_id="analysis", inputs={"scene": scene.id}).primary

    assert art.type == "scene_analysis/v1"
    assert {"motion", "degeneracy"} <= set(art.manifest.files)
    assert "photometric" not in art.manifest.files

    assert art.metric("n_pairs") == 5
    assert 0.0 < art.metric("overall_magnitude") < 1.0
    # DTU is an object on a turntable: real depth, real translation.
    assert art.metric("planar_dominance") == 0.0
    assert art.metric("pure_rotation_risk") == 0.0


@needs_dtu
@needs_cv2
@needs_torch
@needs_raft
def test_an_uncalibrated_scene_omits_the_angular_cues_rather_than_zeroing_them(
    orch, monkeypatch
):
    """Null and zero are opposite conclusions here: "not measurable" versus "no
    rotation". A zero would read as the second."""
    monkeypatch.setenv("RAFT_CHECKPOINT", str(RAFT_CHECKPOINT))
    scene = load_dtu(orch, calibration_path=None)
    art = orch.run("SceneMotion", run_id="analysis", inputs={"scene": scene.id}).primary

    assert art.metric("rotation_median_deg") is None
    assert art.metric("pure_rotation_risk") is None
    assert "uncalibrated_scene" in [d.code for d in art.manifest.diagnostics]

    # The cues that need no K are unaffected.
    assert art.metric("overall_magnitude") > 0.0
    assert art.metric("planar_dominance") is not None


@needs_dtu
@needs_cv2
@needs_torch
@needs_raft
def test_stride_changes_which_pairs_are_measured(orch, monkeypatch):
    """The knob the module's guidance is built around: a motion score is a
    statement about the pairs it chose."""
    monkeypatch.setenv("RAFT_CHECKPOINT", str(RAFT_CHECKPOINT))
    scene = load_dtu(orch)
    near = orch.run("SceneMotion", run_id="analysis", inputs={"scene": scene.id}).primary
    far = orch.run(
        "SceneMotion", run_id="analysis", inputs={"scene": scene.id},
        params={"stride": 3},
    ).primary

    assert near.id != far.id
    assert near.metric("n_pairs") == 5
    assert far.metric("n_pairs") == 3
    assert far.metric("overall_magnitude") > near.metric("overall_magnitude")


@needs_dtu
@needs_cv2
@needs_torch
@needs_raft
def test_a_stride_wider_than_the_scene_is_refused_before_the_gpu_is_touched(
    orch, monkeypatch
):
    monkeypatch.setenv("RAFT_CHECKPOINT", str(RAFT_CHECKPOINT))
    scene = load_dtu(orch)
    with pytest.raises(Exception, match="leaves no pairs"):
        orch.run(
            "SceneMotion", run_id="analysis", inputs={"scene": scene.id},
            params={"stride": 6},
        )


# --------------------------------------------------------------------------- #
# The composition claim
# --------------------------------------------------------------------------- #


@needs_dtu
@needs_cv2
@needs_torch
@needs_raft
def test_the_two_producers_cover_the_type_without_a_merge_step(orch, monkeypatch):
    """Every group of scene_analysis/v1 is optional so that partial producers
    compose. This is the test of that claim: two artifacts, one type, disjoint
    groups, and between them the whole vocabulary the schema declares."""
    monkeypatch.setenv("RAFT_CHECKPOINT", str(RAFT_CHECKPOINT))
    scene = load_dtu(orch)
    triage = orch.run("SceneTriage", run_id="analysis", inputs={"scene": scene.id}).primary
    motion = orch.run("SceneMotion", run_id="analysis", inputs={"scene": scene.id}).primary

    a = set(triage.manifest.files) - {"__sidecars__"}
    b = set(motion.manifest.files) - {"__sidecars__"}

    assert triage.type == motion.type == "scene_analysis/v1"
    assert not (a & b), f"the two producers overlap on {a & b}"
    # `traits` is the one declared group neither fills: it is derived by the
    # orchestrator from thresholds in skills/judgment/, not computed here.
    assert a | b == {"metadata", "photometric", "texture", "motion", "degeneracy"}


def test_neither_analysis_module_derives_traits(registry):
    """Traits are the retrieval key and their cut points are a practitioner call.
    A module that wrote them would freeze a judgement into a cached artifact and
    charge a re-run to revise it."""
    for name, directory in (("SceneTriage", "scene_triage"),
                            ("SceneMotion", "scene_motion")):
        source = (MODULES / directory / "adapter.py").read_text()
        assert 'out.save("traits"' not in source
        assert "traits" not in registry.get(name).metrics
