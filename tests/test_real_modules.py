import re

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
    assert {
        "SceneLoader",
        "FeatureDetectionSIFT",
        "FeatureMatchNN",
        "FeatureTrackUnionFind",
    } <= set(registry.names())


def test_every_metric_named_in_a_manifest_is_documented(registry):
    """A metric declared without a meaning is a metric the agent cannot act on."""
    for name in registry.names():
        spec = registry.get(name)
        for metric, m in spec.metrics.items():
            assert m.meaning, f"{name}.{metric} has no meaning"
            assert m.direction != "unknown", f"{name}.{metric} has no direction"


def _band(text):
    """`healthy=(0.5, None)` -> (0.5, None).

    Literal arguments only, which is what every adapter writes. A computed band
    would raise here, and should: a band a reader cannot see in the source is a
    band the manifest cannot state either.
    """
    return tuple(None if t.strip() == "None" else float(t) for t in text.split(","))


def test_the_manifest_and_the_adapter_agree_about_healthy_bands(registry):
    """Two sources of truth, and the one the agent sees is the adapter's.

    A band lives in the manifest (which `sfm_describe_module` serves) and again in
    the adapter's `out.metric(...)` call (which is what lands on the artifact and
    is therefore what a reader is actually judging against). They drifted apart on
    `weak_pairs` across all six matchers -- manifest silent, adapter publishing an
    unreachable ceiling of zero -- and every reader in a ten-capture sweep judged
    against the adapter's version while the manifest said there was no band to
    judge against. Nothing caught it because nothing compared them.

    THIS COMPARES THE VALUES, NOT MERELY THAT BOTH SIDES DECLARE SOMETHING. The
    presence-only version of this test passed while a tracker published a floor of
    0.5 on the artifact and 0.3 in the manifest, and readers spent a whole sweep
    judging against a number `sfm_describe_module` never served. "Both sides say
    something" is not agreement, and the weaker check is the one that let a live
    divergence through.
    """
    import re

    def metric_calls(src):
        for m in re.finditer(r"out\.metric\(", src):
            i, depth = m.end(), 1
            while depth and i < len(src):
                depth += (src[i] == "(") - (src[i] == ")")
                i += 1
            yield src[m.start():i]

    for name in registry.names():
        spec = registry.get(name)
        adapter = spec.root / "adapter.py"
        if not adapter.exists():
            continue
        emits = {}
        for call in metric_calls(adapter.read_text(encoding="utf-8")):
            named = re.match(r'out\.metric\(\s*"([^"]+)"', call)
            if named:
                band = re.search(r"healthy=\(([^)]*)\)", call)
                emits[named.group(1)] = _band(band.group(1)) if band else None
        for metric, m in spec.metrics.items():
            if metric not in emits:
                continue
            declared = tuple(m.healthy) if m.healthy is not None else None
            assert emits[metric] == declared, (
                f"{name}.{metric}: manifest declares {declared}, adapter emits "
                f"{emits[metric]}. The artifact carries the adapter's version, so "
                f"that is what a reader judges against -- they must agree, and "
                f"agreeing means the same NUMBERS, not merely that both sides "
                f"declare a band."
            )


def test_skill_frontmatter_records_the_module_version_it_was_curated_against(registry):
    """A skill file stamped with an old version is a silent staleness signal.

    The stamp is the only thing telling a reader whether the prose beside a
    parameter was written against the module they are running. Fifteen of
    twenty-eight modules had drifted -- several by five minor versions, one across
    a change that inverted the advice in the file -- and nothing compared them,
    because the stamp is read by humans and never by code. It is now.

    This does NOT assert the prose is current; it asserts that whoever last
    changed the module said so. Bumping a version without touching its skills is
    the case this catches, and the fix is to read them and re-stamp.
    """
    import re

    stale = []
    for name in registry.names():
        spec = registry.get(name)
        for doc in sorted((spec.root / "skills").glob("*.md")):
            stamp = re.search(
                r"^module_version: ([\d.]+)$", doc.read_text(encoding="utf-8"), re.M
            )
            if stamp and stamp.group(1) != spec.version:
                stale.append(
                    f"{name}/skills/{doc.name} says {stamp.group(1)}, "
                    f"module is {spec.version}"
                )
    assert not stale, (
        "skill frontmatter is behind its module:\n  " + "\n  ".join(stale)
    )


def test_every_diagnostic_points_into_the_skills(registry):
    for name in registry.names():
        spec = registry.get(name)
        for code, d in spec.diagnostics.items():
            assert d.see_also, f"{name}.{code} has no see_also"
            doc, _, _ = d.see_also.partition("#")
            assert (spec.root / "skills" / doc).exists(), (
                f"{name}.{code} points at skills/{doc}, which does not exist"
            )


def _heading_slug(heading: str) -> str:
    """GitHub's anchor rule: lowercase, drop punctuation, each space to a hyphen.

    Each space, not each run of spaces: "a — b" loses its dash and becomes "a--b".
    Collapsing the run would pass anchors GitHub cannot resolve and fail ones it can.
    """
    return re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")


def test_every_diagnostic_anchor_resolves_to_a_real_heading(registry):
    """The file existing is not enough. A diagnostic whose anchor is wrong lands the
    agent at the top of a long tuning document with no indication that it missed --
    which is worse than no pointer, because it looks like it worked. Eight of these
    were wrong when this test was written."""
    missing = []
    for name in registry.names():
        spec = registry.get(name)
        for code, d in spec.diagnostics.items():
            doc, _, anchor = d.see_also.partition("#")
            if not anchor:
                continue
            text = (spec.root / "skills" / doc).read_text()
            headings = {
                _heading_slug(line.lstrip("#").strip())
                for line in text.splitlines()
                if line.startswith("#")
            }
            if anchor not in headings:
                missing.append(f"{name}.{code} -> {d.see_also}")
    assert not missing, "diagnostics point at headings that do not exist: " + \
        ", ".join(missing)


def test_curated_skills_are_present(registry):
    """Every module, not a hardcoded list -- a new module with stub skills is
    exactly what this is meant to catch."""
    for name in registry.names():
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
