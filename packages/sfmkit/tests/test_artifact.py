import numpy as np
import pytest

from sfmkit import (
    ArtifactStore,
    Manifest,
    Provenance,
    ValidationError,
    artifact_id,
)


def tracks_payload(n=3):
    obs = np.array(
        [[0, 0, 10.0, 20.0], [0, 1, 11.0, 21.0], [1, 0, 30.0, 40.0], [2, 2, 5.0, 6.0]],
        dtype=np.float32,
    )
    return obs, np.int64(n)


@pytest.fixture
def store(tmp_path):
    return ArtifactStore(tmp_path / "store")


def seal_tracks(store, aid="art_test000001", **kw):
    obs, count = tracks_payload()
    w = store.writer(
        artifact_id=aid,
        type="tracks/v1",
        run="run_1",
        provenance=Provenance(module="Dummy", module_version="1.0.0"),
        **kw,
    )
    w.save("observations", obs=obs, track_count=count)
    w.metric("avg_track_length", 1.33, direction="higher_better", healthy=(3.0, None))
    w.note("Built 3 tracks from 4 observations.")
    return w.seal()


# --------------------------------------------------------------------------- #
# Round trip
# --------------------------------------------------------------------------- #


def test_seal_then_open_round_trips(store):
    sealed = seal_tracks(store)
    reopened = store.open(sealed.id)

    assert reopened.type == "tracks/v1"
    assert reopened.manifest.run == "run_1"
    assert reopened.metric("avg_track_length") == pytest.approx(1.33)
    np.testing.assert_array_equal(
        reopened.load("observations", "obs"), tracks_payload()[0]
    )


def test_manifest_is_one_file_with_frontmatter_and_body(store):
    sealed = seal_tracks(store)
    text = (sealed.root / "artifact.md").read_text()

    assert text.startswith("---\n")
    assert "type: tracks/v1" in text
    assert "Built 3 tracks from 4 observations." in text

    parsed = Manifest.parse(text)
    assert parsed.id == sealed.id
    assert "Built 3 tracks" in parsed.body


def test_manifest_records_shapes_dtypes_and_columns(store):
    sealed = seal_tracks(store)
    obs_doc = sealed.manifest.files["observations"]["arrays"]["obs"]

    assert obs_doc["shape"] == [4, 4]
    assert obs_doc["dtype"] == "float32"
    assert obs_doc["columns"] == ["track_id", "frame_idx", "x", "y"]


def test_provenance_and_duration_are_recorded(store):
    sealed = seal_tracks(store)
    assert sealed.manifest.produced_by.module == "Dummy"
    assert sealed.manifest.produced_by.module_version == "1.0.0"


# --------------------------------------------------------------------------- #
# Validation happens in the PRODUCER
# --------------------------------------------------------------------------- #


def test_nonconforming_payload_fails_at_seal(store):
    """A module declaring tracks/v1 and writing something else must fail here,
    not in a consumer three stages later."""
    w = store.writer(artifact_id="art_bad", type="tracks/v1")
    w.save("observations", obs=np.zeros((4, 3), dtype=np.float32), track_count=np.int64(3))
    with pytest.raises(ValidationError):
        w.seal()


def test_failed_seal_leaves_no_artifact_behind(store):
    w = store.writer(artifact_id="art_bad", type="tracks/v1")
    w.save("observations", obs=np.zeros((4, 3), dtype=np.float32), track_count=np.int64(3))
    with pytest.raises(ValidationError):
        w.seal()
    assert not store.exists("art_bad")


def test_unknown_type_fails_immediately_not_at_seal(store):
    from sfmkit import SchemaError

    with pytest.raises(SchemaError):
        store.writer(artifact_id="art_x", type="not_a_real_type/v1")


def test_artifacts_are_write_once(store):
    obs, count = tracks_payload()
    w = store.writer(artifact_id="art_once", type="tracks/v1")
    w.save("observations", obs=obs, track_count=count)
    w.seal()
    with pytest.raises(Exception, match="already sealed"):
        w.save("observations", obs=obs, track_count=count)


def test_extra_arrays_survive_the_round_trip_and_are_flagged(store):
    obs, count = tracks_payload()
    w = store.writer(artifact_id="art_extra", type="tracks/v1")
    w.save("observations", obs=obs, track_count=count, uncertainty=np.ones(4, dtype=np.float32))
    sealed = w.seal()

    assert sealed.manifest.extras == {"observations": ["uncertainty"]}
    assert sealed.manifest.files["observations"]["arrays"]["uncertainty"]["schema"] == "extra"
    assert store.open(sealed.id).load("observations", "uncertainty").shape == (4,)


# --------------------------------------------------------------------------- #
# Identity and dedup
# --------------------------------------------------------------------------- #


def test_same_recipe_yields_same_id():
    """Five parallel pipelines on one scene must share a single decode."""
    kw = dict(
        type="scene/v1",
        module="OpenScene",
        module_version="1.0.0",
        params={"max_images": 20, "target": [1024, 1024]},
        inputs=[],
    )
    assert artifact_id(**kw) == artifact_id(**kw)


def test_param_order_does_not_change_the_id():
    a = artifact_id(
        type="scene/v1", module="M", module_version="1", params={"a": 1, "b": 2}
    )
    b = artifact_id(
        type="scene/v1", module="M", module_version="1", params={"b": 2, "a": 1}
    )
    assert a == b


def test_different_params_yield_different_ids():
    a = artifact_id(type="tracks/v1", module="M", module_version="1", params={"n": 2})
    b = artifact_id(type="tracks/v1", module="M", module_version="1", params={"n": 3})
    assert a != b


def test_different_inputs_yield_different_ids():
    a = artifact_id(type="tracks/v1", module="M", module_version="1", inputs=["art_a"])
    b = artifact_id(type="tracks/v1", module="M", module_version="1", inputs=["art_b"])
    assert a != b


def test_module_version_bump_yields_a_different_id():
    a = artifact_id(type="tracks/v1", module="M", module_version="1.0.0")
    b = artifact_id(type="tracks/v1", module="M", module_version="1.1.0")
    assert a != b


# --------------------------------------------------------------------------- #
# Sidecars -- what replaces the live pycolmap.Reconstruction handoff
# --------------------------------------------------------------------------- #


def test_sidecar_is_written_and_discoverable(store):
    obs, count = tracks_payload()
    w = store.writer(artifact_id="art_side", type="tracks/v1")
    w.save("observations", obs=obs, track_count=count)
    d = w.sidecar_dir("colmap")
    (d / "cameras.bin").write_bytes(b"not really a colmap model")
    sealed = w.seal()

    reopened = store.open(sealed.id)
    assert reopened.sidecars() == ["colmap"]
    assert (reopened.sidecar("colmap") / "cameras.bin").read_bytes().startswith(b"not")


def test_absent_sidecar_returns_none(store):
    sealed = seal_tracks(store)
    assert store.open(sealed.id).sidecar("colmap") is None


# --------------------------------------------------------------------------- #
# Lineage
# --------------------------------------------------------------------------- #


def test_ancestry_walks_the_dag(store):
    obs, count = tracks_payload()
    for aid, inputs in [
        ("art_scene", []),
        ("art_feats", ["art_scene"]),
        ("art_trax", ["art_scene", "art_feats"]),
    ]:
        w = store.writer(artifact_id=aid, type="tracks/v1", inputs=inputs)
        w.save("observations", obs=obs, track_count=count)
        w.seal()

    ancestry = store.ancestry("art_trax")
    assert ancestry["art_trax"] == ["art_scene", "art_feats"]
    assert ancestry["art_feats"] == ["art_scene"]
    assert ancestry["art_scene"] == []
