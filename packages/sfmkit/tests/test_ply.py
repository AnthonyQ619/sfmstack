"""The PLY writer, which is the one artifact file read outside this framework.

Every assertion here is about the FORMAT rather than about the numbers, because
the numbers come from the caller and the format is what a foreign reader --
MeshLab, CloudCompare, Open3D, an evaluation script -- has to agree with.
"""

import numpy as np
import pytest

from sfmkit import read_ply_header, write_ply


def read_body(path, count, itemsize):
    header = read_ply_header(path)
    raw = path.read_bytes()[header["header_bytes"]:]
    assert len(raw) == count * itemsize
    return raw


def test_header_declares_binary_little_endian(tmp_path):
    path = write_ply(tmp_path / "c.ply", np.zeros((3, 3)))
    assert read_ply_header(path)["format"] == "binary_little_endian 1.0"


def test_xyz_only_writes_three_properties(tmp_path):
    path = write_ply(tmp_path / "c.ply", np.zeros((5, 3)))
    header = read_ply_header(path)
    assert header["properties"] == ["x", "y", "z"]
    assert header["count"] == 5
    read_body(path, 5, 12)


def test_colour_is_uchar_after_the_coordinates(tmp_path):
    """Property ORDER is part of the format: a reader maps by position."""
    xyz = np.zeros((2, 3))
    rgb = np.array([[1, 2, 3], [4, 5, 6]], dtype=np.uint8)
    path = write_ply(tmp_path / "c.ply", xyz, rgb)
    assert read_ply_header(path)["properties"] == [
        "x", "y", "z", "red", "green", "blue"]
    read_body(path, 2, 15)


def test_normals_come_between_position_and_colour(tmp_path):
    path = write_ply(
        tmp_path / "c.ply", np.zeros((2, 3)),
        rgb=np.zeros((2, 3), np.uint8), normals=np.zeros((2, 3)),
    )
    assert read_ply_header(path)["properties"] == [
        "x", "y", "z", "nx", "ny", "nz", "red", "green", "blue"]


def test_values_round_trip_bit_exact(tmp_path):
    xyz = np.array([[1.5, -2.25, 3.125], [0.0, 1e6, -1e-6]])
    rgb = np.array([[255, 0, 128], [7, 8, 9]], dtype=np.uint8)
    path = write_ply(tmp_path / "c.ply", xyz, rgb)

    header = read_ply_header(path)
    dtype = np.dtype([("x", "<f4"), ("y", "<f4"), ("z", "<f4"),
                      ("red", "u1"), ("green", "u1"), ("blue", "u1")])
    table = np.frombuffer(path.read_bytes()[header["header_bytes"]:], dtype=dtype)

    assert np.allclose(np.stack([table["x"], table["y"], table["z"]], axis=1), xyz)
    assert np.array_equal(
        np.stack([table["red"], table["green"], table["blue"]], axis=1), rgb)


def test_non_finite_points_are_dropped_not_written(tmp_path):
    """A NaN in a PLY makes readers fail or silently place a vertex at the origin.

    Dropping is the only behaviour that is not a lie about where the surface is.
    """
    xyz = np.array([[0, 0, 0], [np.nan, 1, 2], [1, 1, 1], [np.inf, 0, 0]])
    path = write_ply(tmp_path / "c.ply", xyz)
    assert read_ply_header(path)["count"] == 2


def test_dropping_keeps_colour_aligned(tmp_path):
    """The filter has to apply to every array or the colours shift by one."""
    xyz = np.array([[0, 0, 0], [np.nan, 0, 0], [2, 2, 2]])
    rgb = np.array([[10, 10, 10], [20, 20, 20], [30, 30, 30]], dtype=np.uint8)
    path = write_ply(tmp_path / "c.ply", xyz, rgb)

    header = read_ply_header(path)
    dtype = np.dtype([("x", "<f4"), ("y", "<f4"), ("z", "<f4"),
                      ("red", "u1"), ("green", "u1"), ("blue", "u1")])
    table = np.frombuffer(path.read_bytes()[header["header_bytes"]:], dtype=dtype)
    assert list(table["red"]) == [10, 30]


def test_a_comment_containing_a_newline_cannot_end_the_header(tmp_path):
    """Comments carry provenance, so they are producer-controlled text in a
    position where a stray newline would truncate the header and corrupt the
    file."""
    path = write_ply(tmp_path / "c.ply", np.zeros((1, 3)),
                     comments=["line one\nelement vertex 999", "ok"])
    header = read_ply_header(path)
    assert header["count"] == 1
    read_body(path, 1, 12)


def test_mismatched_colour_length_is_refused(tmp_path):
    with pytest.raises(ValueError):
        write_ply(tmp_path / "c.ply", np.zeros((3, 3)), np.zeros((2, 3), np.uint8))


def test_wrong_shape_is_refused(tmp_path):
    with pytest.raises(ValueError):
        write_ply(tmp_path / "c.ply", np.zeros((3, 2)))


def test_an_empty_cloud_writes_a_valid_file(tmp_path):
    """Rare but reachable -- a dense module whose filters kept nothing still has
    to leave a file a reader can open rather than a truncated one."""
    path = write_ply(tmp_path / "c.ply", np.zeros((0, 3)), np.zeros((0, 3), np.uint8))
    assert read_ply_header(path)["count"] == 0
    read_body(path, 0, 15)


def test_parent_directories_are_created(tmp_path):
    path = write_ply(tmp_path / "a" / "b" / "c.ply", np.zeros((1, 3)))
    assert path.exists()
