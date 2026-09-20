"""The cloud renderer.

Two kinds of assertion here, and the split is deliberate. The PNG assertions are
about the FORMAT, because the file is decoded by things outside this framework -- a
browser, the MCP image tool, whatever the agent is looking through -- and a malformed
chunk is invisible until one of them refuses it. The geometry assertions are about
the one thing a picture cannot check itself: that the three viewpoints really are
three, and that the third is off the camera ring.
"""

import struct
import zlib

import numpy as np
import pytest

from sfmkit import camera_centres, render_points, write_png
from sfmkit.render import _frame


def decode(path):
    """A PNG back to an (H, W, 3) array, without PIL -- which is the point."""
    raw = path.read_bytes()
    assert raw[:8] == b"\x89PNG\r\n\x1a\n"
    pos, chunks = 8, {}
    while pos < len(raw):
        (length,) = struct.unpack(">I", raw[pos:pos + 4])
        kind = raw[pos + 4:pos + 8]
        payload = raw[pos + 8:pos + 8 + length]
        (crc,) = struct.unpack(">I", raw[pos + 8 + length:pos + 12 + length])
        assert crc == zlib.crc32(kind + payload) & 0xFFFFFFFF, f"bad CRC on {kind}"
        chunks.setdefault(kind, b"")
        chunks[kind] += payload
        pos += 12 + length
    width, height, depth, colour = struct.unpack(">IIBB", chunks[b"IHDR"][:10])
    assert (depth, colour) == (8, 2)
    data = zlib.decompress(chunks[b"IDAT"])
    stride = width * 3 + 1
    rows = []
    for y in range(height):
        row = data[y * stride:(y + 1) * stride]
        assert row[0] == 0, "only the None filter is written"
        rows.append(np.frombuffer(row[1:], np.uint8).reshape(width, 3))
    return np.stack(rows)


def shell(n=4000, seed=0):
    """A hollow sphere: distinct from every direction, so a collapsed view shows."""
    rng = np.random.default_rng(seed)
    v = rng.normal(size=(n, 3))
    xyz = v / np.linalg.norm(v, axis=1, keepdims=True)
    rgb = ((xyz + 1) * 127).astype(np.uint8)
    return xyz, rgb


def ring(n=24, radius=4.0):
    """Camera centres on a circle in the z = 0 plane, looking inward."""
    a = np.linspace(0, 2 * np.pi, n, endpoint=False)
    return np.stack([radius * np.cos(a), radius * np.sin(a), np.zeros(n)], 1)


# ---------------------------------------------------------------- the format
def test_png_decodes_with_correct_dimensions(tmp_path):
    xyz, rgb = shell()
    path, _ = render_points(tmp_path / "c.png", xyz, rgb, size=64, gap=4)
    image = decode(path)
    assert image.shape == (64, 64 * 3 + 4 * 2, 3)


def test_write_png_round_trips_exact_pixels(tmp_path):
    rng = np.random.default_rng(1)
    image = rng.integers(0, 256, (7, 11, 3), dtype=np.uint8)
    assert np.array_equal(decode(write_png(tmp_path / "x.png", image)), image)


def test_write_png_rejects_the_wrong_shape_or_dtype(tmp_path):
    with pytest.raises(ValueError):
        write_png(tmp_path / "a.png", np.zeros((4, 4), np.uint8))
    with pytest.raises(ValueError):
        write_png(tmp_path / "b.png", np.zeros((4, 4, 3), np.float32))


# ---------------------------------------------------------------- the picture
def test_every_panel_draws_something(tmp_path):
    xyz, rgb = shell()
    path, _ = render_points(tmp_path / "c.png", xyz, rgb, size=64, gap=4,
                            centres=ring(), background=(0, 0, 0))
    image = decode(path)
    for i in range(3):
        panel = image[:, i * 68:i * 68 + 64]
        assert (panel > 0).any(), f"panel {i} is empty"


def test_the_three_panels_differ(tmp_path):
    """A frame bug that reuses one direction three times renders three identical
    panels and looks entirely plausible."""
    xyz, rgb = shell()
    path, _ = render_points(tmp_path / "c.png", xyz, rgb, size=64, gap=4,
                            centres=ring())
    image = decode(path)
    panels = [image[:, i * 68:i * 68 + 64] for i in range(3)]
    for a, b in ((0, 1), (0, 2), (1, 2)):
        assert not np.array_equal(panels[a], panels[b]), f"panels {a} and {b} match"


def test_the_third_view_is_off_the_camera_ring(tmp_path):
    """The reason this module exists: a direction no input image had."""
    xyz, _ = shell()
    centres = ring()
    views = [v for v, _ in _frame(xyz, centres)]
    axis = views[2] / np.linalg.norm(views[2])
    # Every camera sits in the z = 0 plane, so the ring's axis is z and no camera
    # direction may come near it.
    directions = (centres - xyz.mean(0))
    directions /= np.linalg.norm(directions, axis=1, keepdims=True)
    assert np.abs(directions @ axis).max() < 0.1
    # and the first two views ARE in the ring's plane
    for v in views[:2]:
        assert abs(v @ axis / np.linalg.norm(v)) < 1e-6


def test_the_three_views_are_mutually_orthogonal(tmp_path):
    xyz, _ = shell()
    for centres in (ring(), None):
        views = [v / np.linalg.norm(v) for v, _ in _frame(xyz, centres)]
        for a, b in ((0, 1), (0, 2), (1, 2)):
            assert abs(views[a] @ views[b]) < 1e-6, f"{a},{b} not orthogonal"


def test_it_works_without_camera_centres(tmp_path):
    xyz, rgb = shell()
    path, _ = render_points(tmp_path / "c.png", xyz, rgb, size=48, centres=None)
    assert decode(path).shape[0] == 48


def test_a_far_floater_does_not_shrink_the_object(tmp_path):
    """Framing on the extent would put the whole shell inside one pixel."""
    xyz, rgb = shell()
    far = np.concatenate([xyz, [[0.0, 0.0, 5000.0]]])
    far_rgb = np.concatenate([rgb, [[255, 255, 255]]]).astype(np.uint8)
    tight, _ = render_points(tmp_path / "a.png", xyz, rgb, size=64, centres=ring(),
                             background=(0, 0, 0))
    loose, outside = render_points(tmp_path / "b.png", far, far_rgb, size=64,
                                   centres=ring(), background=(0, 0, 0))
    assert outside == 1
    filled = lambda p: int((decode(p) > 0).any(-1).sum())
    # Within a few percent: the floater is reported, not allowed to set the scale.
    assert filled(loose) > 0.9 * filled(tight)


def test_it_rejects_an_empty_or_mismatched_cloud(tmp_path):
    with pytest.raises(ValueError):
        render_points(tmp_path / "a.png", np.zeros((0, 3)), np.zeros((0, 3), np.uint8))
    with pytest.raises(ValueError):
        render_points(tmp_path / "b.png", np.zeros((5, 3)), np.zeros((4, 3), np.uint8))


# ---------------------------------------------------------------- the centres
def test_camera_centres_inverts_the_pose_convention():
    """C = -R^T t. A sign error here picks three plausible-looking wrong views."""
    rng = np.random.default_rng(2)
    R = np.linalg.qr(rng.normal(size=(3, 3)))[0]
    if np.linalg.det(R) < 0:
        R[:, 0] *= -1
    centre = np.array([1.0, -2.0, 3.0])
    cam_from_world = np.hstack([R, (-R @ centre)[:, None]])
    got = camera_centres(cam_from_world[None])
    assert np.allclose(got[0], centre)


def test_camera_centres_honours_the_valid_mask():
    P = np.tile(np.hstack([np.eye(3), np.zeros((3, 1))]), (4, 1, 1))
    assert len(camera_centres(P, [True, False, True, False])) == 2
    assert len(camera_centres(P)) == 4
