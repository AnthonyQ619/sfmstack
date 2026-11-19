"""Withholding scene-analysis signals for an experiment (harness/withhold.py).

The fixture is a real plan brief's analysis section from a corpus capture: SceneDescription,
SceneMotion and SceneTriage as the agent saw them, plus the brief's module lists.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

HARNESS = Path(__file__).resolve().parents[1] / "harness"
sys.path.insert(0, str(HARNESS))
import withhold  # noqa: E402

BRIEF = json.loads((Path(__file__).parent / "fixtures" / "brief_analysis_corpus.json").read_text())
PHOTO_NAMES = ("illumination_change", "color_shift", "exposure_shift", "combined_change",
               "highlight_clipped", "shadow_clipped", "illumination_unstable", "Photometric:", "Clipping:")


def text(obj) -> str:
    return json.dumps(obj)


def test_nothing_is_withheld_unless_asked():
    assert withhold.parse(None) == set() and withhold.parse("") == set()
    assert withhold.scrub(BRIEF, set()) == BRIEF


def test_an_unknown_signal_is_refused():
    with pytest.raises(SystemExit):
        withhold.parse("visual,depth")


def test_motion_illumination_removes_scene_motion_and_the_photometric_group():
    out = withhold.scrub(BRIEF, {"motion_illumination"})
    s = text(out)
    assert not any(n in s for n in PHOTO_NAMES)
    assert "SceneMotion" not in s
    tri = next(a for a in out["analysis"] if a["module"] == "SceneTriage")
    # texture and sharpness stay; ordering is a motion reading since P11, so it goes too
    assert {"texture_density", "repetitiveness", "textureless_fraction", "sharpness_ratio"} <= set(tri["metrics"])
    assert "ordered" not in tri["metrics"]
    assert "texture" in tri["series"] and "photometric" not in tri["groups"]
    assert "Texture:" in tri["notes"] and "UNORDERED" not in tri["notes"]
    # the visual signal is untouched
    assert any(a["module"] == "SceneDescription" for a in out["analysis"])


def test_visual_removes_scene_description_only():
    out = withhold.scrub(BRIEF, {"visual"})
    s = text(out)
    assert "SceneDescription" not in s
    assert "illumination_change" in s and any(a["module"] == "SceneMotion" for a in out["analysis"])


def test_neither_removes_both():
    s = text(withhold.scrub(BRIEF, {"visual", "motion_illumination"}))
    assert "SceneDescription" not in s and "SceneMotion" not in s
    assert not any(n in s for n in PHOTO_NAMES)
    assert "texture_density" in s and "SceneTriage" in s


def test_the_full_brief_carries_every_signal_the_others_remove():
    # Negative control: if the fixture lacked these, the removal tests above would pass vacuously.
    s = text(BRIEF)
    assert all(n in s for n in ("SceneDescription", "SceneMotion", "illumination_change",
                                "highlight_clipped_fraction", "Photometric:", "Clipping:"))


def test_a_withheld_module_is_refused_by_name_and_others_are_not():
    assert withhold.refusal("SceneMotion", {"motion_illumination"})
    assert withhold.refusal("SceneDescription", {"visual"})
    assert withhold.refusal("SceneTriage", {"visual", "motion_illumination"}) is None
    assert withhold.refusal("SceneMotion", {"visual"}) is None
    assert withhold.refusal("SceneMotion", set()) is None


MANIFEST = """---
id: art_000000000000
type: analysis/v1
files:
  photometric:
    path: data/photometric.npz
    arrays:
      illumination_change: {shape: [], dtype: float64}
      highlight_clipped: {shape: [10], dtype: float64}
  texture:
    path: data/texture.npz
    arrays:
      density: {shape: [], dtype: float64}
metrics:
  illumination_change: {value: 0.0597, direction: lower_better}
  combined_change: {value: 0.07, direction: lower_better}
  texture_density: {value: 460.3, direction: higher_better}
diagnostics:
- {code: illumination_unstable, severity: warn}
- {code: textureless, severity: warn}
---
Triage over 10 images (9 pairs, consecutive). Photometric: combined 0.070 (illumination 0.060, colour 0.079, exposure 0.071). Texture: 460 corners/MP. Clipping: 3.10% highlight, 0.20% shadow in the median frame.
"""


def test_an_artifact_manifest_is_filtered_inside_its_text():
    # `sfmx artifact` returns the manifest as one YAML text block, which a key filter cannot see into.
    out = withhold.scrub({"manifest": MANIFEST}, {"motion_illumination"})["manifest"]
    assert not any(n in out for n in PHOTO_NAMES)
    assert "texture_density" in out and "textureless" in out and "Texture: 460" in out
    assert withhold.scrub({"manifest": MANIFEST}, set())["manifest"] == MANIFEST  # control
