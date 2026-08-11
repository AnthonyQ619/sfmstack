"""The HTML report, against a real store built from the hermetic fixture modules.

No dataset and no Docker: what is under test is the arrangement of what artifacts
and run records already say, not any reconstruction.
"""

import importlib.util
import re
import sys
from pathlib import Path

import pytest
from sfmkit import ArtifactStore

from dataset_paths import REPO
from sfmorch import ModuleRegistry, Orchestrator
from sfmorch.run_record import Step

FIXTURES = REPO / "packages" / "sfmorch" / "tests" / "fixtures" / "modules"


def _load_report_module():
    spec = importlib.util.spec_from_file_location(
        "sfm_report", REPO / "tools" / "sfm_report.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["sfm_report"] = mod
    spec.loader.exec_module(mod)
    return mod


report = _load_report_module()


@pytest.fixture
def built(tmp_path):
    """A session with a superseded attempt, a varied parameter, and a failure."""
    registry = ModuleRegistry()
    registry.load_dir(FIXTURES)
    store = ArtifactStore(tmp_path / "store")
    orch = Orchestrator(store=store, registry=registry)

    scene = orch.run("MakeScene", run_id="r1", params={"n_images": 4}).primary
    features = orch.run(
        "FakeDetector", run_id="r1", inputs={"scene": scene.id},
        params={"max_keypoints": 16},
    ).primary

    # Two matcher attempts: the first is superseded by the second.
    orch.run("FakeMatcher", run_id="r1", inputs={"scene": scene.id, "features": features.id},
             params={"keep_ratio": 0.25})
    pairs = orch.run("FakeMatcher", run_id="r1", inputs={"scene": scene.id, "features": features.id},
                     params={"keep_ratio": 1.0}).primary
    tracks = orch.run("FakeTracker", run_id="r1", inputs={"scene": scene.id, "pairs": pairs.id}).primary
    sparse = orch.run(
        "FakeReconstructor", run_id="r1",
        inputs={"scene": scene.id, "tracks": tracks.id},
    ).primary

    # A failed step, written exactly as the orchestrator writes one: no outputs,
    # the inputs it was given, and the error. Provoking a genuine failure out of a
    # fixture module would test the fixture rather than the report.
    run = orch.open_run("r1")
    run.add(Step(
        index=-1,
        module="FakeReconstructor",
        module_version="1.0.0",
        params={"min_observe": 99},
        inputs={"scene": scene.id, "tracks": tracks.id},
        status="failed",
        duration_s=0.2,
        error="RuntimeError: ValueError: only 0 points triangulated at min_observe=99",
    ))
    return store, sparse.id


def collected(built):
    store, final = built
    steps = report.collect(store, final)
    return report.attempts(store, final, {s["id"] for s in steps})


# --------------------------------------------------------------------------- #
# What the lineage cannot say
# --------------------------------------------------------------------------- #


def test_a_failed_attempt_appears_even_though_it_produced_no_artifact(built):
    """The reason this section reads run.md instead of the store. A module that
    failed leaves nothing to walk lineage back through, so a report built from
    artifacts alone shows a pipeline that went right the first time."""
    tried = collected(built)
    failed = [e for e in tried["entries"] if e["status"] == "failed"]

    assert len(failed) == 1
    assert failed[0]["module"] == "FakeReconstructor"
    assert tried["counts"]["failed"] == 1


def test_the_error_shown_is_the_modules_own_not_the_transports(built):
    """Crossing a container boundary re-raises the module's exception inside the
    transport's, and each hop prepends a class name. Only the innermost describes
    what went wrong; 'RuntimeError' describes nothing."""
    tried = collected(built)
    error = next(e["error"] for e in tried["entries"] if e["status"] == "failed")

    assert error.startswith("ValueError:")
    assert "RuntimeError" not in error


def test_a_long_error_is_cut_at_a_word_boundary():
    long = "ValueError: " + "wordy " * 60 + "end."
    cut = report._innermost(long)
    assert cut.endswith("…")
    assert not cut.endswith(" …")


def test_an_attempt_that_worked_but_lost_is_marked_superseded(built):
    """The other thing lineage cannot say: an artifact nothing points at. It was
    produced successfully and then not used, which is a different fact from a
    failure and has to read differently."""
    tried = collected(built)
    matchers = [e for e in tried["entries"] if e["module"] == "FakeMatcher"]

    assert len(matchers) == 2
    assert {e["used"] for e in matchers} == {True, False}
    assert tried["counts"]["superseded"] >= 1


def test_only_the_parameters_that_actually_differ_are_surfaced(built):
    """A fifteen-key parameter block in a summary row is unreadable, and the part
    that explains why two attempts differed is the part that differed."""
    tried = collected(built)
    matchers = [e for e in tried["entries"] if e["module"] == "FakeMatcher"]

    assert all(set(e["differs"]) == {"keep_ratio"} for e in matchers)
    assert {e["differs"]["keep_ratio"] for e in matchers} == {0.25, 1.0}

    # A module attempted once has nothing to compare against, so nothing varied.
    detector = next(e for e in tried["entries"] if e["module"] == "FakeDetector")
    assert detector["differs"] == {}


def test_attempts_are_ordered_by_stage_then_by_when_they_were_run(built):
    """Alphabetical within a stage would put a bundle adjuster above the
    triangulator that fed it, which reads as a pipeline nobody ran."""
    tried = collected(built)
    stages = [e["stage"] for e in tried["entries"]]

    order = [report.STAGE_ORDER.index(s) for s in stages if s in report.STAGE_ORDER]
    assert order == sorted(order)


def test_a_failed_step_is_placed_by_what_it_consumed(built):
    """It produced no artifact to take a stage from, but it recorded its inputs,
    and those pin it as precisely as an output would have."""
    tried = collected(built)
    failed = next(e for e in tried["entries"] if e["status"] == "failed")
    assert failed["stage"] == "sparse"


def test_headline_numbers_are_the_ones_the_type_requires(built):
    """Two attempts at one stage have to be compared on the same numbers.
    Declaration order is per-module, so it cannot supply that."""
    tried = collected(built)
    entry = next(e for e in tried["entries"] if e["module"] == "FakeReconstructor"
                 and e["status"] == "ok")

    from sfmkit.schema import registry as core_types
    required = list(core_types().get("sparse_model/v1").metrics)
    assert [m["name"] for m in entry["metrics"]] == required[:3]


# --------------------------------------------------------------------------- #
# The page
# --------------------------------------------------------------------------- #


def test_the_page_is_self_contained(built, tmp_path):
    """A report that needs the network is a blank page exactly when you most want
    to look at a result -- on a cluster node, offline, after the run finished."""
    store, final = built
    steps = report.collect(store, final)
    html = report.render(steps, None, collected(built), "test")

    assert not re.search(r'(src|href)\s*=\s*["\']https?://', html)
    assert "cdn" not in html.lower()
    assert "What was tried" in html


def test_a_store_with_no_run_record_still_renders(built, tmp_path):
    """The section is additive. Pointed at a store whose runs directory is absent
    -- an artifact set copied off a machine, say -- the report drops it rather
    than failing."""
    store, final = built
    for child in Path(store.runs_dir).iterdir():
        for f in child.rglob("*"):
            f.unlink()
        child.rmdir()
    Path(store.runs_dir).rmdir()

    assert report.attempts(store, final, set()) is None
    assert report.render(report.collect(store, final), None, None, "test")
