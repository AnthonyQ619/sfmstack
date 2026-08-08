"""Replay and lineage.

Together these are what let the driving agent go back upstream freely. Tuning a
tracker for three runs and only then concluding the matcher was at fault is a
legitimate path -- so changing something upstream must be one call, and comparing
the two branches must show where they actually parted company.
"""

import pytest

from sfmorch import WiringError, diverge


def build(orch, scene, *, keep_ratio=1.0, run_id="run_test"):
    feats = orch.run(
        "FakeDetector", run_id=run_id, inputs={"scene": scene.id}
    ).primary
    pairs = orch.run(
        "FakeMatcher",
        run_id=run_id,
        inputs={"scene": scene.id, "features": feats.id},
        params={"keep_ratio": keep_ratio},
    ).primary
    tracks = orch.run(
        "FakeTracker", run_id=run_id, inputs={"scene": scene.id, "pairs": pairs.id}
    ).primary
    sparse = orch.run(
        "FakeReconstructor",
        run_id=run_id,
        inputs={"scene": scene.id, "tracks": tracks.id},
    ).primary
    return feats, pairs, tracks, sparse


# --------------------------------------------------------------------------- #
# Replay
# --------------------------------------------------------------------------- #


def test_replay_reruns_the_step_and_everything_downstream(orch, scene):
    feats, pairs, tracks, sparse = build(orch, scene, keep_ratio=0.2)

    results = orch.replay(
        run_id="run_test", from_artifact=pairs.id, overrides={"keep_ratio": 1.0}
    )

    assert [r.step.module for r in results] == [
        "FakeMatcher",
        "FakeTracker",
        "FakeReconstructor",
    ]


def test_replay_rewires_downstream_inputs_to_the_new_artifacts(orch, scene):
    _, pairs, tracks, _ = build(orch, scene, keep_ratio=0.2)

    results = orch.replay(
        run_id="run_test", from_artifact=pairs.id, overrides={"keep_ratio": 1.0}
    )
    new_pairs = results[0].primary
    new_tracks = results[1].primary

    assert new_pairs.id != pairs.id
    assert new_tracks.manifest.inputs and new_pairs.id in new_tracks.manifest.inputs
    assert tracks.id not in [r.primary.id for r in results]


def test_replay_leaves_the_original_branch_intact(orch, scene):
    """Nothing is superseded. Both branches stay comparable."""
    _, pairs, tracks, sparse = build(orch, scene, keep_ratio=0.2)

    results = orch.replay(
        run_id="run_test", from_artifact=pairs.id, overrides={"keep_ratio": 1.0}
    )

    for original in (pairs, tracks, sparse):
        assert orch.store.exists(original.id)
    for r in results:
        assert orch.store.exists(r.primary.id)


def test_replay_improves_the_downstream_result(orch, scene):
    """The point of going upstream: a better matcher yields better tracks."""
    _, pairs, tracks, _ = build(orch, scene, keep_ratio=0.2)
    before = tracks.metric("track_count")

    results = orch.replay(
        run_id="run_test", from_artifact=pairs.id, overrides={"keep_ratio": 1.0}
    )
    after = results[1].primary.metric("track_count")

    assert after > before


def test_replayed_steps_reference_what_they_replaced(orch, scene):
    _, pairs, _, _ = build(orch, scene, keep_ratio=0.2)
    origin_index = orch.open_run("run_test").producer_of(pairs.id).index

    results = orch.replay(
        run_id="run_test", from_artifact=pairs.id, overrides={"keep_ratio": 1.0}
    )
    assert results[0].step.replay_of == origin_index
    assert all(r.step.replay_of is not None for r in results)


def test_replaying_the_last_step_reruns_only_it(orch, scene):
    _, _, _, sparse = build(orch, scene)
    results = orch.replay(
        run_id="run_test", from_artifact=sparse.id, overrides={"min_observe": 3}
    )
    assert [r.step.module for r in results] == ["FakeReconstructor"]


def test_replaying_an_unknown_artifact_is_refused(orch, scene):
    build(orch, scene)
    with pytest.raises(WiringError, match="no step producing"):
        orch.replay(run_id="run_test", from_artifact="art_nope")


# --------------------------------------------------------------------------- #
# Lineage -- divergence, never staleness
# --------------------------------------------------------------------------- #


def test_identical_lineages_do_not_diverge(orch, scene):
    _, _, _, sparse = build(orch, scene)
    assert diverge(orch.store, sparse.id, sparse.id) == []


def test_divergence_names_the_module_and_the_parameter_that_changed(orch, scene):
    _, pairs, _, sparse_a = build(orch, scene, keep_ratio=0.2)
    results = orch.replay(
        run_id="run_test", from_artifact=pairs.id, overrides={"keep_ratio": 1.0}
    )
    sparse_b = results[-1].primary

    found = diverge(orch.store, sparse_a.id, sparse_b.id)
    matcher = [d for d in found if d.module == "FakeMatcher"]

    assert matcher, f"expected a FakeMatcher divergence, got {found}"
    assert matcher[0].param_diff["keep_ratio"] == (0.2, 1.0)
    assert "keep_ratio 0.2 -> 1.0" in matcher[0].describe()


def test_divergence_marks_inherited_differences_as_such(orch, scene):
    """A downstream artifact differs even though its own parameters did not.
    Saying so is the whole point -- otherwise the agent credits the wrong knob."""
    _, pairs, _, sparse_a = build(orch, scene, keep_ratio=0.2)
    results = orch.replay(
        run_id="run_test", from_artifact=pairs.id, overrides={"keep_ratio": 1.0}
    )
    sparse_b = results[-1].primary

    found = {d.module: d for d in diverge(orch.store, sparse_a.id, sparse_b.id)}
    tracker = found["FakeTracker"]

    assert tracker.param_diff == {}
    assert "inherited from further upstream" in tracker.describe()


def test_shared_ancestors_are_not_reported(orch, scene):
    _, pairs, _, sparse_a = build(orch, scene, keep_ratio=0.2)
    results = orch.replay(
        run_id="run_test", from_artifact=pairs.id, overrides={"keep_ratio": 1.0}
    )
    found = {d.module for d in diverge(orch.store, sparse_a.id, results[-1].primary.id)}

    assert "MakeScene" not in found
    assert "FakeDetector" not in found


def test_compare_puts_metrics_and_divergence_together(orch, scene):
    _, pairs, _, sparse_a = build(orch, scene, keep_ratio=0.2)
    results = orch.replay(
        run_id="run_test", from_artifact=pairs.id, overrides={"keep_ratio": 1.0}
    )
    sparse_b = results[-1].primary

    report = orch.compare([sparse_a.id, sparse_b.id])

    assert "num_points3d" in report["metrics"]
    assert report["artifacts"][sparse_a.id]["module"] == "FakeReconstructor"

    key = f"{sparse_a.id} vs {sparse_b.id}"
    assert any("keep_ratio" in line for line in report["lineage_divergence"][key])
