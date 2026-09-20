"""Three orthographic views of a point cloud, side by side, as one PNG.

Why this exists: every reading a dense module publishes is a scalar, and a scalar
cannot distinguish a clean surface from a clean surface wrapped in floaters. Readers
driving the dense stage asked for a look at the cloud repeatedly, and the answer until
now was that there was nothing to look at.

Why it is written by hand rather than with an imaging library: two of the three
containers that produce `dense_model/v1` (dense-mvs, dense-fusion) have no PIL, and
adding one to both for three thumbnails is a poor trade. numpy and `zlib` from the
standard library are enough, and both are already present everywhere.

**Orthographic, not perspective.** No intrinsics are needed, and scale is uniform
across the frame, so a reader can compare extents between panels. The point is to see
the shape and what is floating around it, not to simulate a camera.

**At least one panel is off the camera ring.** Given the camera centres, the third
panel looks down the ring's own axis -- a direction no input image had. That is where
a backdrop plane, a floater shell or a duplicated surface shows up, and it is the
panel worth adding to a report.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

import numpy as np

__all__ = ["camera_centres", "render_points", "write_png"]


def camera_centres(cam_from_world, valid=None) -> np.ndarray:
    """Camera centres from world-to-camera 3x4 matrices: C = -R^T t.

    Shared because all three producers of `dense_model/v1` need the same three lines
    to give `render_points` its ring, and a sign error here is invisible in the output
    -- it would simply pick three plausible-looking wrong viewpoints.
    """
    P = np.asarray(cam_from_world, dtype=np.float64)
    keep = np.ones(len(P), bool) if valid is None else np.asarray(valid, dtype=bool)
    return np.array([-P[i][:, :3].T @ P[i][:, 3] for i in range(len(P)) if keep[i]])


def write_png(path: Path, image: np.ndarray) -> Path:
    """An (H, W, 3) uint8 array to a PNG. Standard library only."""
    if image.ndim != 3 or image.shape[2] != 3 or image.dtype != np.uint8:
        raise ValueError(f"expected (H, W, 3) uint8, got {image.shape} {image.dtype}")
    height, width = image.shape[:2]
    # Filter byte 0 (None) per scanline, which is what the spec calls for when the
    # encoder does not filter.
    raw = b"".join(b"\x00" + image[y].tobytes() for y in range(height))

    def chunk(kind: bytes, payload: bytes) -> bytes:
        return (struct.pack(">I", len(payload)) + kind + payload
                + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF))

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 6))
        + chunk(b"IEND", b"")
    )
    return path


def _frame(xyz: np.ndarray, centres: np.ndarray | None):
    """Three view directions, and the up vector to pair with each.

    With camera centres, the ring they lie on defines the frame: two views from the
    ring's own plane and one down its axis. Without them, the cloud's principal axes
    do, which still guarantees three mutually orthogonal directions.
    """
    if centres is not None and len(centres) >= 3:
        c = centres - centres.mean(0)
        # Smallest singular direction of the centres is the ring's axis.
        axis = np.linalg.svd(c, full_matrices=False)[2][-1]
        # A direction in the ring's plane: the mean viewing direction, flattened.
        mean_dir = centres.mean(0) - xyz.mean(0)
        flat = mean_dir - axis * float(mean_dir @ axis)
        if np.linalg.norm(flat) < 1e-9:
            flat = np.linalg.svd(c, full_matrices=False)[2][0]
        a = flat / np.linalg.norm(flat)
        b = np.cross(axis, a)
        return [(a, axis), (b, axis), (axis, a)]
    # Eigenvectors of the 3x3 covariance, not an SVD of the cloud: the cloud can be
    # millions of points and only the 3x3 is needed.
    d = xyz - xyz.mean(0)
    e = np.linalg.eigh(np.cov(d.T))[1].T[::-1]   # descending variance
    return [(e[2], e[1]), (e[0], e[1]), (e[1], e[0])]


def _panel(xyz, rgb, view, up, size, lo, hi, radius, background):
    forward = view / np.linalg.norm(view)
    up = up - forward * float(up @ forward)
    if np.linalg.norm(up) < 1e-9:
        up = np.cross(forward, [0.0, 0.0, 1.0])
        if np.linalg.norm(up) < 1e-9:
            up = np.cross(forward, [0.0, 1.0, 0.0])
    up = up / np.linalg.norm(up)
    right = np.cross(up, forward)

    centre = (lo + hi) / 2.0
    rel = xyz - centre
    u = rel @ right
    v = rel @ up
    depth = rel @ forward            # larger is nearer the viewer

    # One scale for both axes and every panel, so extents stay comparable.
    span = float(np.max(hi - lo))
    if span <= 0:
        span = 1.0
    scale = (size - 2 * (radius + 3)) / span
    px = np.round(u * scale + size / 2.0).astype(np.int64)
    py = np.round(-v * scale + size / 2.0).astype(np.int64)

    image = np.empty((size, size, 3), np.uint8)
    image[:] = background
    zbuf = np.full(size * size, -np.inf)

    # Gentle depth shading: without it an orthographic dump of a shell reads flat.
    d0, d1 = np.percentile(depth, [2, 98]) if len(depth) > 50 else (depth.min(), depth.max())
    shade = np.clip((depth - d0) / (d1 - d0) if d1 > d0 else np.ones_like(depth), 0, 1)
    shade = 0.55 + 0.45 * shade
    shaded = np.clip(rgb.astype(np.float64) * shade[:, None], 0, 255).astype(np.uint8)

    flat_img = image.reshape(-1, 3)
    for dv in range(-radius, radius + 1):
        for du in range(-radius, radius + 1):
            x, y = px + du, py + dv
            ok = (x >= 0) & (x < size) & (y >= 0) & (y < size)
            if not ok.any():
                continue
            idx = (y[ok] * size + x[ok])
            z = depth[ok]
            # Painter's order: draw far first, let nearer points overwrite.
            order = np.argsort(z, kind="stable")
            idx, z = idx[order], z[order]
            keep = z > zbuf[idx]
            # np.maximum.at resolves duplicate pixels within this pass correctly.
            np.maximum.at(zbuf, idx, z)
            flat_img[idx[keep]] = shaded[ok][order][keep]
    return image


def render_points(path, xyz, rgb, *, centres=None, size=420, radius=None,
                  background=(16, 17, 20), gap=6, clip_percentile=0.5) -> tuple[Path, int]:
    """Write three orthographic views of the cloud to one PNG.

    Returns the path and the number of points that fell outside the framing box.

    Framing uses percentiles rather than the extent, so one distant floater cannot
    shrink the object to a dot. Every point is still drawn; those outside the box land
    at the edge or are clipped, and the count comes back so the caller can say so.
    """
    xyz = np.asarray(xyz, dtype=np.float64)
    rgb = np.asarray(rgb, dtype=np.uint8)
    if xyz.ndim != 2 or xyz.shape[1] != 3 or len(xyz) == 0:
        raise ValueError(f"expected a non-empty (N, 3) cloud, got {xyz.shape}")
    if len(rgb) != len(xyz):
        raise ValueError(f"{len(rgb)} colours for {len(xyz)} points")
    if radius is None:
        radius = 1 if len(xyz) < 300_000 else 0

    lo = np.percentile(xyz, clip_percentile, axis=0)
    hi = np.percentile(xyz, 100 - clip_percentile, axis=0)
    pad = 0.08 * np.max(hi - lo)
    lo, hi = lo - pad, hi + pad
    outside = int((~((xyz >= lo) & (xyz <= hi)).all(1)).sum())

    centres = None if centres is None else np.asarray(centres, dtype=np.float64)
    panels = [_panel(xyz, rgb, view, up, size, lo, hi, radius, background)
              for view, up in _frame(xyz, centres)]

    sheet = np.empty((size, size * 3 + gap * 2, 3), np.uint8)
    sheet[:] = background
    # A slightly lighter seam so the three panels read as three, not as one wide image.
    for i, panel in enumerate(panels):
        x = i * (size + gap)
        sheet[:, x:x + size] = panel
        if i:
            sheet[:, x - gap:x] = np.clip(np.array(background) + 26, 0, 255).astype(np.uint8)
    return write_png(path, sheet), outside
