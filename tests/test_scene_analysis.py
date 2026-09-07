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

    n_images, n_pairs = 6, 5  # consecutive pairing over the fixture scene

    assert art.manifest.extras["photometric"] == [
        "highlight_clipped", "pair_combined", "pair_index", "shadow_clipped",
    ]
    assert art.manifest.extras["texture"] == [
        "density_per_image", "sharpness_median", "textureless_per_image",
    ]

    # `texture` mixes one scalar with three per-image series. The scalar is the
    # scale `sharpness` is read against; the other two answer "which frame will
    # starve the detector", which the set median cannot.
    assert art.load("texture", "density_per_image").shape == (n_images,)
    assert art.load("texture", "textureless_per_image").shape == (n_images,)

    # The scene metric is the MEDIAN of the series it summarises, and pinning that
    # is what makes the series usable: a reader comparing one frame against the
    # scene number needs to know which statistic they are comparing against.
    assert art.metric("texture_density") == pytest.approx(
        float(np.median(art.load("texture", "density_per_image"))), rel=1e-3
    )
    assert art.metric("textureless_fraction") == pytest.approx(
        float(np.median(art.load("texture", "textureless_per_image"))), rel=1e-3
    )

    # `photometric` holds two DIFFERENT indices, which is the trap this asserts
    # against: everything named `pair_*` is per pair, and the clipping arrays are
    # per IMAGE, in scene order. They live in the same group because that is where
    # the measurement comes from, not because they share an axis.
    assert len(art.load("photometric", "pair_combined")) == n_pairs
    assert len(art.load("photometric", "shadow_clipped")) == n_images
    assert len(art.load("photometric", "highlight_clipped")) == n_images

    # The scale `sharpness` is read against. Without it a raw Laplacian variance
    # is uninterpretable, because `sharpness_ratio` divides by it and drops it.
    assert art.load("texture", "sharpness_median") == pytest.approx(
        float(np.median(art.load("texture", "sharpness")))
    )


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
def test_the_degeneracy_fractions_ship_the_series_they_are_means_of(orch, monkeypatch):
    """A fraction cannot say WHICH pair, and every action attached to these two
    metrics needs to know -- keep the pair out of the seed, re-run SceneLoader
    over the translating subset. Every non-zero reading measured so far has been
    one or two pairs of eleven, below the diagnostic band, where the fraction
    alone does not distinguish a local fact from a global one."""
    monkeypatch.setenv("RAFT_CHECKPOINT", str(RAFT_CHECKPOINT))
    scene = load_dtu(orch)
    art = orch.run("SceneMotion", run_id="analysis", inputs={"scene": scene.id}).primary

    planar = art.load("degeneracy", "pair_planar")
    rotation_only = art.load("degeneracy", "pair_pure_rotation")

    # The metric is the mean of the series, exactly -- so a caller wanting the
    # fraction over a subset of the capture computes it rather than re-running.
    assert art.metric("planar_dominance") == pytest.approx(float(np.mean(planar)))
    assert art.metric("pure_rotation_risk") == pytest.approx(
        float(np.mean(rotation_only))
    )

    # Each series against ITS OWN index, never a shared one. On a clean scene the
    # subsets coincide and it is tempting to assume they always do; a pair can
    # admit a homography and no rotation estimate, and an uncalibrated scene
    # fills the first and neither of the others.
    assert len(art.load("degeneracy", "pair_index")) == len(planar)
    assert len(art.load("degeneracy", "rotation_pair_index")) == len(rotation_only)
    assert len(art.load("motion", "rotation_pair_index")) == len(
        art.load("motion", "pair_rotation_deg")
    )


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

    # And the series follow the same rule as the metrics: the planar one is
    # written, the rotation one is absent rather than empty. This is the case
    # that makes a single shared pair index wrong -- here the two subsets are not
    # merely different sizes, one of them does not exist.
    groups = art.load("degeneracy")
    assert {"pair_planar", "pair_index"} <= set(groups)
    assert "pair_pure_rotation" not in groups
    assert "rotation_pair_index" not in groups


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
    # orchestrator from thresholds held outside the modules, not computed here
    # -- and those thresholds deliberately do not exist yet (see evidence/INDEX).
    assert a | b == {"metadata", "photometric", "texture", "motion", "degeneracy"}


# --------------------------------------------------------------------------- #
# SceneDescription -- the asserted one
# --------------------------------------------------------------------------- #


GOOD_REPORT = {
    "environment": "studio",
    "main_subject": "a cardboard box",
    "subject_completeness": "cropped",
    "subject": "One object filling the right half against a plain backdrop.",
    "empty_regions": "Uniform background surrounding the object; not wanted.",
    "repetition_notes": {"texture": "none - the backdrop is plain and the object "
                                    "carries no periodic pattern",
                         "objects": "none - a single object, nothing repeated"},
    "dynamic_content": "none",
    "third_frame": "[3] - the only cell showing the far side of the object",
    "material_hazards": "none",
    "overall": "Controlled capture of a single object. Nothing hazardous.",
}


@needs_dtu
@needs_pil
def test_the_first_call_renders_a_browse_set_and_says_it_is_waiting(orch):
    scene = load_dtu(orch)
    art = orch.run(
        "SceneDescription", run_id="analysis", inputs={"scene": scene.id}
    ).primary

    assert art.metric("described") == 0
    assert art.metric("browse_images") == 6
    # Null, not zero, on every report-derived metric. Zero is a claim.
    for name in ("dynamic_content", "material_hazards", "hazard_position",
                 "third_frame", "has_main_subject", "subject_complete"):
        assert art.metric(name) is None, name

    assert "awaiting_description" in [d.code for d in art.manifest.diagnostics]
    assert (art.root / "data" / "browse" / "contact_sheet.jpg").is_file()
    assert "description" not in art.manifest.files


@needs_dtu
@needs_pil
def test_the_sheet_is_the_only_image_so_it_needs_no_name(orch):
    """`sfm_artifact_image(<id>)` resolves without a name only when the artifact
    carries exactly one image, and this is the case that convenience exists for.
    Per-frame thumbnails would break it, and are redundant anyway -- the scene
    holds every working image at full resolution."""
    from sfmorch.service import IMAGE_SUFFIXES

    scene = load_dtu(orch)
    art = orch.run(
        "SceneDescription", run_id="analysis", inputs={"scene": scene.id}
    ).primary

    images = [
        p for p in (art.root / "data").rglob("*")
        if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES
    ]
    assert [p.name for p in images] == ["contact_sheet.jpg"]

    # ...and the single-frame route, which is better than a thumbnail would be.
    assert (scene.root / "data" / "images" / "000003.png").is_file()


@needs_dtu
@needs_pil
def test_the_second_call_records_the_report_beside_the_first(orch):
    scene = load_dtu(orch)
    first = orch.run(
        "SceneDescription", run_id="analysis", inputs={"scene": scene.id}
    ).primary
    described = orch.run(
        "SceneDescription", run_id="analysis", inputs={"scene": scene.id},
        params={"report": GOOD_REPORT},
    ).primary

    assert first.id != described.id  # the report is part of the recipe
    assert described.metric("described") == 1
    assert described.metric("dynamic_content") == 0
    assert str(described.load("description", "environment")) == "studio"

    # Three arrays are declared in the type; the rest ride as recorded extras, so
    # revising the rubric does not mean revising scene_analysis/v1.
    assert set(described.manifest.extras["description"]) == {
        "browsed", "full_res_frames", "third_frame", "main_subject",
        "subject_completeness", "subject", "empty_regions", "dynamic_content",
        "material_hazards", "repetition_texture", "repetition_objects",
    }
    # Two prescribed and one chosen, in that order, as the scene wants them.
    assert list(described.load("description", "full_res_frames")) == [
        "images/000000.png", "images/000005.png", "images/000003.png"
    ]
    assert described.metric("third_frame") == 3
    # `overall` leads the body: it is the field a reader acts on, and the enums
    # are its machine-readable shadow rather than a summary of it.
    body = (described.root / "artifact.md").read_text().split("---", 2)[-1].strip()
    assert body.startswith(GOOD_REPORT["overall"])
    assert described.metric("has_main_subject") == 1
    assert described.metric("subject_complete") == 0  # cropped
    assert "incomplete_subject" in [d.code for d in described.manifest.diagnostics]
    assert len(described.load("description", "browsed")) == 6


@needs_dtu
@needs_pil
@pytest.mark.parametrize("mutation, expected", [
    ({"overall": ""}, "empty"),
    ({"environment": "probably outdoor"}, "expected one of"),
    ({"material_hazards": "coherent", "hazard_position": "background"},
     "hazard_notes"),
    # The hazard split, v6. Coherence and position are independent, and the
    # position is contingent both ways round.
    ({"material_hazards": "coherent", "hazard_notes": "a mirrored shopfront"},
     "hazard_position. is empty"),
    ({"hazard_position": "background"}, "nothing to place"),
    ({"material_hazards": "a bit shiny"}, "expected one of"),
    ({"material_hazards": "coherent", "hazard_notes": "x",
      "hazard_position": "somewhere behind"}, "expected one of"),
    # The repetition note: unconditional since v7, both halves demanded, capped.
    ({"repetition_notes": None}, "must be a mapping"),
    ({"repetition_notes": "lots of identical windows"}, "must be a mapping"),
    ({"repetition_notes": {"texture": "brick coursing"}},
     r"repetition_notes\[objects\]. is empty"),
    ({"repetition_notes": {"texture": "brick " * 60, "objects": "windows"}},
     "the cap is 260"),
    # The third full-resolution view, v5. Four ways to get it wrong.
    ({"third_frame": "the one with the mirror"}, "does not name a cell"),
    ({"third_frame": "[99] - out beyond the end of the set"}, "browse set has"),
    ({"third_frame": "[0] - the first one, which is already prescribed"},
     "already prescribed"),
    ({"third_frame": "[3]"}, "no reason attached"),
    # The subject contingency, both ways round.
    ({"subject_completeness": ""}, "subject_completeness. is empty"),
    ({"main_subject": "none", "subject_completeness": "complete"},
     "nothing for it to describe"),
])
def test_a_report_that_misses_the_rubric_is_refused(orch, mutation, expected):
    """Shape only -- nothing here can tell whether the answers are TRUE. What it
    buys is that a half-filled report is not recorded as a description."""
    scene = load_dtu(orch)
    with pytest.raises(Exception, match=expected):
        orch.run(
            "SceneDescription", run_id="analysis", inputs={"scene": scene.id},
            params={"report": GOOD_REPORT | mutation},
        )


@needs_dtu
@needs_pil
def test_an_answer_beyond_the_rubric_rides_in_rather_than_being_dropped(orch):
    """The rubric is expected to grow. A field that keeps appearing here is a
    candidate for promotion into the required set."""
    scene = load_dtu(orch)
    art = orch.run(
        "SceneDescription", run_id="analysis", inputs={"scene": scene.id},
        params={"report": GOOD_REPORT | {"lighting": "flat and even"}},
    ).primary

    assert str(art.load("description", "lighting")) == "flat and even"


@needs_pil
def test_the_rubric_doc_and_the_adapter_agree():
    """The closed vocabularies live in two places -- the adapter enforces them and
    rubric.md explains them. They must not drift apart silently."""
    description = _adapter("scene_description")
    doc = (MODULES / "scene_description" / "skills" / "rubric.md").read_text()

    for field, allowed in description.ENUMS.items():
        assert f"### `{field}` — enum" in doc, f"{field} is not in the rubric"
        for value in allowed:
            assert f"`{value}`" in doc, f"{field}: '{value}' is undocumented"

    for field in description.FREE_TEXT:
        assert f"### `{field}` — free text" in doc, f"{field} is not in the rubric"


def test_neither_analysis_module_derives_traits(registry):
    """Traits are the retrieval key and their cut points are a practitioner call.
    A module that wrote them would freeze a judgement into a cached artifact and
    charge a re-run to revise it."""
    for name, directory in (("SceneTriage", "scene_triage"),
                            ("SceneMotion", "scene_motion")):
        source = (MODULES / directory / "adapter.py").read_text()
        assert 'out.save("traits"' not in source
        assert "traits" not in registry.get(name).metrics


@needs_dtu
@needs_pil
def test_a_scene_with_no_main_subject_leaves_completeness_unanswered(orch):
    """`none` is a real answer -- a street or a landscape has no main subject --
    and then `subject_complete` is null rather than 0. "There is nothing to be
    incomplete" and "it is incomplete" are opposite claims."""
    scene = load_dtu(orch)
    art = orch.run(
        "SceneDescription", run_id="analysis", inputs={"scene": scene.id},
        params={"report": {k: v for k, v in GOOD_REPORT.items()
                           if k != "subject_completeness"}
                | {"main_subject": "none"}},
    ).primary

    assert art.metric("has_main_subject") == 0
    assert art.metric("subject_complete") is None
    assert "incomplete_subject" not in [d.code for d in art.manifest.diagnostics]
