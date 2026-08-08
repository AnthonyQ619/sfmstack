import numpy as np
import pytest

from dataset_paths import (
    DTU_CALIB,
    DTU_SCAN1,
    ETH_CALIB,
    ETH_COURTYARD,
    needs_cv2,
    needs_dtu,
    needs_eth,
    needs_pil,
)

pytestmark = [needs_pil]


def load_dtu(orch, **overrides):
    params = {
        "image_dir": str(DTU_SCAN1),
        "calibration_path": str(DTU_CALIB),
        "max_images": 6,
        "resize": "auto",
        "max_edge": 1024,
    }
    params.update(overrides)
    return orch.run("SceneLoader", run_id="it", params=params).primary


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #


def test_real_modules_register(registry):
    assert {"SceneLoader", "FeatureDetectionSIFT"} <= set(registry.names())


def test_every_metric_named_in_a_manifest_is_documented(registry):
    """A metric declared without a meaning is a metric the agent cannot act on."""
    for name in registry.names():
        spec = registry.get(name)
        for metric, m in spec.metrics.items():
            assert m.meaning, f"{name}.{metric} has no meaning"
            assert m.direction != "unknown", f"{name}.{metric} has no direction"


def test_every_diagnostic_points_into_the_skills(registry):
    for name in registry.names():
        spec = registry.get(name)
        for code, d in spec.diagnostics.items():
            assert d.see_also, f"{name}.{code} has no see_also"
            doc, _, _ = d.see_also.partition("#")
            assert (spec.root / "skills" / doc).exists(), (
                f"{name}.{code} points at skills/{doc}, which does not exist"
            )


def test_curated_skills_are_present(registry):
    for name in ("SceneLoader", "FeatureDetectionSIFT"):
        spec = registry.get(name)
        assert set(spec.describe()["available_skills"]) >= {
            "SKILL",
            "artifact",
            "limitations",
            "sources",
            "tuning",
        }
        assert spec.skill("SKILL")


# --------------------------------------------------------------------------- #
# SceneLoader
# --------------------------------------------------------------------------- #


@needs_dtu
def test_scene_loader_reads_dtu(orch):
    scene = load_dtu(orch)

    assert scene.type == "scene/v1"
    assert scene.metric("n_images") == 6
    assert scene.has("calibration")
    assert scene.load("images", "paths").shape == (6,)


@needs_dtu
def test_the_scene_is_self_contained_when_resized(orch):
    """Downstream containers should need only the artifact mounted."""
    scene = load_dtu(orch)
    for rel in scene.load("images", "paths"):
        resolved = scene.resolve(str(rel))
        assert resolved.exists()
        assert scene.root in resolved.parents


@needs_dtu
def test_resize_none_references_the_dataset_instead(orch):
    scene = load_dtu(orch, resize="none")
    first = scene.resolve(str(scene.load("images", "paths")[0]))
    assert first.is_absolute()
    assert DTU_SCAN1 in first.parents


@needs_dtu
def test_intrinsics_are_scaled_to_the_working_resolution(orch):
    """Scaled exactly once. The predecessor mutated calibration in place, so a
    second call squared the factor."""
    scene = load_dtu(orch, max_edge=800)
    K = scene.load("calibration", "intrinsics")[0]
    scale = scene.load("images", "scale")[0]

    raw = np.load(DTU_CALIB, allow_pickle=True)["k_mats"][0]
    assert K[0, 0] == pytest.approx(raw[0, 0] * scale[0], rel=1e-6)
    assert K[1, 2] == pytest.approx(raw[1, 2] * scale[1], rel=1e-6)


@needs_dtu
def test_uniform_sampling_spans_the_set(orch):
    uniform = load_dtu(orch, max_images=4, sampling="uniform")
    head = load_dtu(orch, max_images=4, sampling="head")

    assert list(head.load("images", "names")) != list(uniform.load("images", "names"))
    assert str(uniform.load("images", "names")[-1]) > str(head.load("images", "names")[-1])


@needs_dtu
def test_omitting_calibration_is_a_legitimate_uncalibrated_scene(orch):
    scene = orch.run(
        "SceneLoader",
        run_id="it",
        params={"image_dir": str(DTU_SCAN1), "max_images": 4, "resize": "auto"},
    ).primary

    assert not scene.has("calibration")
    assert "uncalibrated" in [d.code for d in scene.manifest.diagnostics]


@needs_dtu
def test_a_directory_with_no_images_is_refused(orch, tmp_path):
    from sfmorch import ExecutionError

    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(ExecutionError):
        orch.run("SceneLoader", run_id="it", params={"image_dir": str(empty)})


@needs_eth
def test_mixed_source_resolutions_get_per_image_scale(orch):
    """ETH3D courtyard genuinely mixes resolutions within one scene. The
    predecessor applied one scalar scale computed from a single image."""
    params = {
        "image_dir": str(ETH_COURTYARD),
        "max_images": 6,
        "resize": "auto",
        "max_edge": 1024,
    }
    if ETH_CALIB.exists():
        params["calibration_path"] = str(ETH_CALIB)
    scene = orch.run("SceneLoader", run_id="it_eth", params=params).primary

    assert scene.metric("mixed_resolution") == 1
    assert "mixed_resolution" in [d.code for d in scene.manifest.diagnostics]

    originals = scene.load("images", "size_original")
    scales = scene.load("images", "scale")
    assert len(np.unique(originals, axis=0)) > 1
    assert len(np.unique(scales, axis=0)) > 1, "per-image scales must differ"


# --------------------------------------------------------------------------- #
# SIFT
# --------------------------------------------------------------------------- #


@needs_dtu
@needs_cv2
def test_sift_runs_on_a_real_scene(orch):
    scene = load_dtu(orch)
    feats = orch.run(
        "FeatureDetectionSIFT",
        run_id="it",
        inputs={"scene": scene.id},
        params={"max_keypoints": 2048},
    ).primary

    xy = feats.load("keypoints", "xy")
    desc = feats.load("descriptors", "desc")

    assert feats.type == "features/v1"
    assert len(xy) == len(desc)
    assert desc.shape[1] == 128
    assert feats.metric("keypoints_per_image") > 500


@needs_dtu
@needs_cv2
def test_every_image_is_represented(orch):
    """A gap means a frame produced zero keypoints, which breaks every track
    passing through it."""
    scene = load_dtu(orch)
    feats = orch.run(
        "FeatureDetectionSIFT", run_id="it", inputs={"scene": scene.id}
    ).primary

    idx = feats.load("keypoints", "image_index")
    assert set(np.unique(idx)) == set(range(int(scene.metric("n_images"))))


@needs_dtu
@needs_cv2
def test_root_sift_descriptors_are_nonnegative(orch):
    scene = load_dtu(orch)
    feats = orch.run(
        "FeatureDetectionSIFT",
        run_id="it",
        inputs={"scene": scene.id},
        params={"root_sift": True},
    ).primary
    assert feats.load("descriptors", "desc").min() >= 0.0


@needs_dtu
@needs_cv2
def test_keypoints_lie_inside_the_working_frame(orch):
    scene = load_dtu(orch)
    feats = orch.run(
        "FeatureDetectionSIFT", run_id="it", inputs={"scene": scene.id}
    ).primary

    xy = feats.load("keypoints", "xy")
    idx = feats.load("keypoints", "image_index")
    sizes = scene.load("images", "size_current")

    assert (xy >= 0).all()
    assert (xy[:, 0] <= sizes[idx, 0]).all()
    assert (xy[:, 1] <= sizes[idx, 1]).all()


@needs_dtu
@needs_cv2
def test_raising_the_cap_when_saturated_yields_more_keypoints(orch):
    """The first gradient step in tuning.md, pinned as a test."""
    scene = load_dtu(orch)
    low = orch.run(
        "FeatureDetectionSIFT",
        run_id="it",
        inputs={"scene": scene.id},
        params={"max_keypoints": 512},
    ).primary
    high = orch.run(
        "FeatureDetectionSIFT",
        run_id="it",
        inputs={"scene": scene.id},
        params={"max_keypoints": 4096},
    ).primary

    assert low.metric("saturation") == 1.0
    assert low.metric("keypoints_per_image") < high.metric("keypoints_per_image")
    assert "cap_binding" in [d.code for d in low.manifest.diagnostics]


@needs_dtu
@needs_cv2
def test_the_two_settings_are_separate_comparable_artifacts(orch):
    scene = load_dtu(orch)
    a = orch.run(
        "FeatureDetectionSIFT",
        run_id="it",
        inputs={"scene": scene.id},
        params={"max_keypoints": 512},
    ).primary
    b = orch.run(
        "FeatureDetectionSIFT",
        run_id="it",
        inputs={"scene": scene.id},
        params={"max_keypoints": 4096},
    ).primary

    report = orch.compare([a.id, b.id])
    assert a.id != b.id
    assert "keypoints_per_image" in report["metrics"]

    lines = report["lineage_divergence"][f"{a.id} vs {b.id}"]
    assert any("max_keypoints" in line for line in lines)


@needs_dtu
@needs_cv2
def test_wrong_input_type_is_refused_for_real_modules(orch):
    from sfmorch import WiringError

    scene = load_dtu(orch)
    feats = orch.run(
        "FeatureDetectionSIFT", run_id="it", inputs={"scene": scene.id}
    ).primary
    with pytest.raises(WiringError, match="expects 'scene/v1'"):
        orch.run("FeatureDetectionSIFT", run_id="it", inputs={"scene": feats.id})
