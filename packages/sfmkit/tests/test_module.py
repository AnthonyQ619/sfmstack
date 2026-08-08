"""The module contract, exercised end to end in-process.

This is build-order step 3: prove a module author can write one function against
sfmkit and get a valid, provenance-carrying artifact out -- before any container
or orchestrator exists.
"""

import numpy as np
import pytest

from sfmkit import ArtifactStore, Ctx, InputError, Params, module, run_module


@pytest.fixture
def store(tmp_path):
    return ArtifactStore(tmp_path / "store")


@pytest.fixture
def scene(store):
    w = store.writer(artifact_id="art_scene01", type="scene/v1", run="run_1")
    w.save(
        "images",
        paths=np.array(["/data/a.png", "/data/b.png", "/data/c.png"]),
        names=np.array(["a.png", "b.png", "c.png"]),
        size_original=np.array([[1600, 1200]] * 3, dtype=np.int32),
        size_current=np.array([[800, 600]] * 3, dtype=np.int32),
        scale=np.array([[0.5, 0.5]] * 3, dtype=np.float64),
        content_hash=np.array("deadbeef"),
    )
    return w.seal()


# A module author writes exactly this much.
@module
def build_tracks(ctx: Ctx):
    n_images = int(ctx.inputs["scene"].load("images", "size_current").shape[0])
    min_len = ctx.params.min_track_len

    rows = [
        [tid, frame, 10.0 * tid, 20.0 * frame]
        for tid in range(4)
        for frame in range(n_images)
    ]
    obs = np.array(rows, dtype=np.float32)

    out = ctx.output("tracks")
    out.save("observations", obs=obs, track_count=np.int64(4))
    out.metric(
        "avg_track_length",
        float(n_images),
        direction="higher_better",
        healthy=(3.0, None),
    )
    if n_images < min_len:
        out.diagnostic(
            "too_few_views",
            severity="warn",
            message="Fewer views than the minimum track length.",
            see_also="tuning.md#avg_track_length-below-30",
        )
    out.note(f"Built 4 tracks across {n_images} images.")


def make_ctx(store, scene, **params):
    return Ctx(
        store=store,
        module="BuildTracks",
        module_version="1.0.0",
        run="run_1",
        inputs={"scene": scene},
        params=Params({"min_track_len": 2, **params}),
        output_types={"tracks": "tracks/v1"},
    )


def test_module_produces_a_valid_artifact(store, scene):
    out = run_module(build_tracks, make_ctx(store, scene))["tracks"]

    assert out.type == "tracks/v1"
    assert out.load("observations", "obs").shape == (12, 4)
    assert out.metric("avg_track_length") == 3.0


def test_provenance_is_filled_in_without_the_author_doing_anything(store, scene):
    out = run_module(build_tracks, make_ctx(store, scene))["tracks"]
    prov = out.manifest.produced_by

    assert prov.module == "BuildTracks"
    assert prov.module_version == "1.0.0"
    assert prov.params == {"min_track_len": 2}
    assert prov.duration_s is not None
    assert prov.started_at


def test_inputs_are_recorded_so_lineage_is_free(store, scene):
    out = run_module(build_tracks, make_ctx(store, scene))["tracks"]
    assert out.manifest.inputs == [scene.id]
    assert out.manifest.scene == scene.id


def test_diagnostics_carry_a_pointer_into_the_module_skills(store, scene):
    out = run_module(build_tracks, make_ctx(store, scene, min_track_len=99))["tracks"]

    assert [d.code for d in out.manifest.diagnostics] == ["too_few_views"]
    assert out.manifest.diagnostics[0].see_also.startswith("tuning.md#")


def test_metric_metadata_replaces_the_external_interpretation_corpus(store, scene):
    out = run_module(build_tracks, make_ctx(store, scene))["tracks"]
    metric = out.manifest.metrics["avg_track_length"]

    assert metric.direction == "higher_better"
    assert metric.healthy == (3.0, None)


def test_same_params_dedup_to_the_same_artifact(store, scene):
    a = run_module(build_tracks, make_ctx(store, scene))["tracks"]
    b = run_module(build_tracks, make_ctx(store, scene))["tracks"]
    assert a.id == b.id


def test_different_params_produce_a_second_artifact_and_keep_the_first(store, scene):
    """Re-running with new parameters must not overwrite the earlier attempt --
    comparing attempts is the whole point."""
    a = run_module(build_tracks, make_ctx(store, scene, min_track_len=2))["tracks"]
    b = run_module(build_tracks, make_ctx(store, scene, min_track_len=5))["tracks"]

    assert a.id != b.id
    assert store.exists(a.id) and store.exists(b.id)


def test_a_raising_module_seals_nothing(store, scene):
    @module
    def broken(ctx: Ctx):
        ctx.output("tracks").save("observations", obs=np.zeros((1, 4), dtype=np.float32))
        raise RuntimeError("upstream library blew up")

    ctx = make_ctx(store, scene)
    with pytest.raises(RuntimeError, match="blew up"):
        run_module(broken, ctx)
    assert store.list(type="tracks/v1") == []


def test_undeclared_output_slot_is_rejected(store, scene):
    ctx = make_ctx(store, scene)
    with pytest.raises(InputError, match="no declared output"):
        ctx.output("not_declared")


def test_missing_input_names_what_was_given(store, scene):
    ctx = make_ctx(store, scene)
    with pytest.raises(InputError, match="Given: \\['scene'\\]"):
        ctx.input("pairs")


def test_input_type_mismatch_is_caught(store, scene):
    ctx = make_ctx(store, scene)
    with pytest.raises(InputError, match="expected tracks/v1"):
        ctx.input("scene", expect="tracks/v1")


def test_missing_param_error_points_at_the_manifest(store, scene):
    ctx = Ctx(store=store, module="M", params=Params({}), output_types={})
    with pytest.raises(AttributeError, match="module.yaml"):
        _ = ctx.params.nope
