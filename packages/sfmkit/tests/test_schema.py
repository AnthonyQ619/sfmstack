import numpy as np
import pytest

from sfmkit import SchemaError, ValidationError, parse_schema, registry

# --------------------------------------------------------------------------- #
# Core registry
# --------------------------------------------------------------------------- #

CORE_TYPES = [
    "scene/v1",
    "scene_analysis/v1",
    "features/v1",
    "pairwise_matches/v1",
    "tracks/v1",
    "poses/v1",
    "sparse_model/v1",
    "dense_model/v1",
]


def test_core_types_load():
    reg = registry()
    assert set(CORE_TYPES) <= set(reg.names())


def test_unknown_type_names_the_alternatives():
    with pytest.raises(SchemaError, match="unknown payload type"):
        registry().get("tracks/v99")


def test_bad_type_name_rejected():
    with pytest.raises(SchemaError, match="must look like"):
        parse_schema({"type": "Tracks"})


def test_custom_type_name_accepted():
    schema = parse_schema({"type": "custom/gaussians/v1"})
    assert schema.is_custom


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #


def good_tracks(n_tracks=3):
    obs = np.array(
        [[0, 0, 10.0, 20.0], [0, 1, 11.0, 21.0], [1, 0, 30.0, 40.0], [2, 2, 5.0, 6.0]],
        dtype=np.float32,
    )
    obs[:, 0] = np.array([0, 0, 1, 2], dtype=np.float32)
    return {"observations": {"obs": obs, "track_count": np.int64(n_tracks)}}


def test_conforming_payload_passes():
    registry().get("tracks/v1").validate(good_tracks())


def test_missing_required_file():
    with pytest.raises(ValidationError) as e:
        registry().get("tracks/v1").validate({})
    assert "missing required file 'observations'" in str(e.value)


def test_missing_required_array():
    payload = {"observations": {"obs": good_tracks()["observations"]["obs"]}}
    with pytest.raises(ValidationError, match="missing required array 'track_count'"):
        registry().get("tracks/v1").validate(payload)


def test_wrong_column_count_is_caught():
    payload = good_tracks()
    payload["observations"]["obs"] = np.zeros((4, 3), dtype=np.float32)
    with pytest.raises(ValidationError) as e:
        registry().get("tracks/v1").validate(payload)
    assert "expected 4" in str(e.value)


def test_wrong_dtype_is_caught():
    payload = good_tracks()
    payload["observations"]["obs"] = payload["observations"]["obs"].astype(np.int32)
    with pytest.raises(ValidationError, match="dtype int32"):
        registry().get("tracks/v1").validate(payload)


def test_wrong_rank_is_caught():
    payload = good_tracks()
    payload["observations"]["obs"] = np.zeros((4,), dtype=np.float32)
    with pytest.raises(ValidationError, match="rank 1"):
        registry().get("tracks/v1").validate(payload)


def test_every_problem_is_reported_not_just_the_first():
    payload = {"observations": {"obs": np.zeros((4, 3), dtype=np.int32)}}
    with pytest.raises(ValidationError) as e:
        registry().get("tracks/v1").validate(payload)
    assert len(e.value.problems) >= 3  # dtype, columns, missing track_count


# --------------------------------------------------------------------------- #
# Invariants
# --------------------------------------------------------------------------- #


def test_track_count_off_by_one_is_caught():
    """The classic producer bug: the count disagrees with the id column.

    Without this check it surfaces as an index error two stages downstream.
    """
    payload = good_tracks(n_tracks=99)
    with pytest.raises(ValidationError, match="implies 3 distinct ids"):
        registry().get("tracks/v1").validate(payload)


def test_nan_is_caught():
    payload = good_tracks()
    payload["observations"]["obs"][0, 2] = np.nan
    with pytest.raises(ValidationError, match="non-finite"):
        registry().get("tracks/v1").validate(payload)


def test_negative_frame_index_is_caught():
    payload = good_tracks()
    payload["observations"]["obs"][0, 1] = -1
    with pytest.raises(ValidationError, match="below the allowed"):
        registry().get("tracks/v1").validate(payload)


def test_unknown_invariant_is_a_schema_error_not_a_validation_error():
    schema = parse_schema(
        {
            "type": "custom/thing/v1",
            "files": {"f": {"arrays": {"a": {"shape": [None]}}}},
            "invariants": [{"check": "does_not_exist", "args": {}}],
        }
    )
    with pytest.raises(SchemaError, match="unknown invariant"):
        schema.validate({"f": {"a": np.zeros(3)}})


# --------------------------------------------------------------------------- #
# Additive extension -- the rule that keeps the type set from fragmenting
# --------------------------------------------------------------------------- #


def test_extra_arrays_are_allowed():
    """A module adding a field must extend the type, not fork it."""
    payload = good_tracks()
    payload["observations"]["my_new_signal"] = np.ones(4, dtype=np.float32)
    registry().get("tracks/v1").validate(payload)  # must not raise


def test_extra_arrays_are_reported_so_consumers_can_discover_them():
    payload = good_tracks()
    payload["observations"]["my_new_signal"] = np.ones(4, dtype=np.float32)
    extras = registry().get("tracks/v1").extras(payload)
    assert extras == {"observations": ["my_new_signal"]}


def test_extra_files_are_allowed():
    payload = good_tracks()
    payload["side_channel"] = {"whatever": np.zeros(2)}
    registry().get("tracks/v1").validate(payload)


def test_optional_file_may_be_absent():
    """An uncalibrated scene is a first-class state, not an error."""
    scene = {
        "images": {
            "paths": np.array(["/a.png"]),
            "names": np.array(["a.png"]),
            "size_original": np.array([[640, 480]], dtype=np.int32),
            "size_current": np.array([[640, 480]], dtype=np.int32),
            "scale": np.array([[1.0, 1.0]], dtype=np.float64),
            "content_hash": np.array("abc123"),
        }
    }
    registry().get("scene/v1").validate(scene)


def test_string_dtype_matches_by_kind_not_width():
    """'<U6' and '<U73' are both str; a schema must not pin the width."""
    scene = {
        "images": {
            "paths": np.array(["/a/very/long/path/to/an/image/file/name.png"]),
            "names": np.array(["a.png"]),
            "size_original": np.array([[640, 480]], dtype=np.int32),
            "size_current": np.array([[640, 480]], dtype=np.int32),
            "scale": np.array([[1.0, 1.0]], dtype=np.float64),
            "content_hash": np.array("abc"),
        }
    }
    registry().get("scene/v1").validate(scene)
