"""SparseVerification says when its veto fires by construction.

A model built on a correspondence-free estimator's poses alone has no camera that rests
on correspondences, so the pixel veto measures the estimator's error and fires on it by
construction. `plan/pose.md` says to read that as unverified; the module's message said
"contradicted, solve again". The module now reads the model's lineage and says which.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

MODULES = Path(__file__).resolve().parents[1] / "modules"


def _adapter():
    spec = importlib.util.spec_from_file_location(
        "sv_adapter", MODULES / "sparse_verification" / "adapter.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["sv_adapter"] = mod
    spec.loader.exec_module(mod)
    return mod


class _Store:
    """Artifacts as {id: (module, [input ids])}; only what the lineage walk reads."""

    def __init__(self, graph):
        self.graph = graph

    def open(self, aid):
        module, inputs = self.graph[aid]
        return SimpleNamespace(id=aid, manifest=SimpleNamespace(
            inputs=inputs, produced_by=SimpleNamespace(module=module) if module else None))


SCENE = {"scene": ("SceneLoader", []), "feat": ("FeatureDetectionSIFT", ["scene"]),
         "match": ("FeatureMatchLightGlue", ["feat"]), "tracks": ("FeatureTrackUnionFind", ["match"])}


def _walk(graph, top):
    store = _Store({**SCENE, **graph})
    return _adapter().placed_by_estimator(store, store.open(top))


def test_an_estimator_only_model_is_recognised():
    graph = {"poses": ("PoseVGGT", ["scene"]),
             "tri": ("SparseTriangulation", ["poses", "tracks"]),
             "ba": ("BundleAdjustmentGlobal", ["tri"])}
    assert _walk(graph, "ba") == "PoseVGGT"


def test_a_registered_model_is_not():
    """The control: the same chain on geometric poses keeps the veto's ordinary reading."""
    graph = {"poses": ("PoseEssentialToPnP", ["tracks"]),
             "tri": ("SparseTriangulation", ["poses", "tracks"]),
             "ba": ("BundleAdjustmentGlobal", ["tri"])}
    assert _walk(graph, "ba") is None


def test_a_fill_is_not_estimator_only():
    """A fill's core was registered; its placed cameras are excluded elsewhere."""
    graph = {"core": ("SparseGlobalCOLMAP", ["match"]),
             "est": ("PoseMapAnything", ["scene"]),
             "fill": ("PoseFill", ["core", "est"]),
             "tri": ("SparseTriangulation", ["fill", "tracks"]),
             "ba": ("BundleAdjustmentGlobal", ["tri"])}
    assert _walk(graph, "ba") is None


def test_the_message_says_by_construction_and_names_the_estimator():
    text = _adapter().by_construction("PoseMapAnything")
    assert "PoseMapAnything" in text and "by construction" in text
    assert "unverified" in text
