"""PLY writing, shared so every module's sidecar is byte-compatible.

`dense_model/v1` and `sparse_model/v1` both say a `.ply` sidecar is conventional
for viewing and for external evaluation tooling. This is that writer.

It lives in sfmkit rather than in each module for one reason that matters more
than the duplication: the report tool and any external consumer parse this, so the
format has to be identical whatever produced it. Two modules each rolling their own
header is how a reader ends up special-casing which module wrote the file.

Binary little-endian, not ASCII. A 400k-point dense cloud is 6 MB binary and about
20 MB as text, and every reader that exists -- Open3D, MeshLab, CloudCompare,
plyfile -- handles binary. The predecessor wrote ASCII with a Python loop per
point, which on a cloud this size is minutes rather than milliseconds.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

__all__ = ["write_ply", "read_ply_header"]


def write_ply(
    path: str | Path,
    xyz: np.ndarray,
    rgb: np.ndarray | None = None,
    normals: np.ndarray | None = None,
    comments: list[str] | None = None,
) -> Path:
    """Write (N, 3) points, optional uint8 colours and optional normals.

    Non-finite points are dropped rather than written: a NaN in a PLY makes most
    readers either fail or silently place a vertex at the origin, and neither is
    what the producer meant.

    Returns the path written, so a caller can stat it for a size metric.
    """
    path = Path(path)
    xyz = np.asarray(xyz, dtype=np.float32)
    if xyz.ndim != 2 or xyz.shape[1] != 3:
        raise ValueError(f"xyz must be (N, 3), got {xyz.shape}")

    # Shapes are checked BEFORE the finite mask is applied: masking a shorter
    # array with a longer boolean is an IndexError from numpy rather than an
    # explanation, and a same-length-but-wrong-width array would pass silently.
    if rgb is not None:
        rgb = np.asarray(rgb, dtype=np.uint8)
        if rgb.shape != xyz.shape:
            raise ValueError(f"rgb must match xyz, got {rgb.shape} and {xyz.shape}")
    if normals is not None:
        normals = np.asarray(normals, dtype=np.float32)
        if normals.shape != xyz.shape:
            raise ValueError(
                f"normals must match xyz, got {normals.shape} and {xyz.shape}"
            )

    finite = np.isfinite(xyz).all(axis=1)
    if normals is not None:
        finite &= np.isfinite(normals).all(axis=1)

    xyz = xyz[finite]
    if rgb is not None:
        rgb = rgb[finite]
    if normals is not None:
        normals = normals[finite]

    fields = [("x", "<f4"), ("y", "<f4"), ("z", "<f4")]
    if normals is not None:
        fields += [("nx", "<f4"), ("ny", "<f4"), ("nz", "<f4")]
    if rgb is not None:
        fields += [("red", "u1"), ("green", "u1"), ("blue", "u1")]

    header = ["ply", "format binary_little_endian 1.0"]
    for line in comments or ():
        # A comment containing a newline would end the header early and corrupt
        # the file, so they are flattened rather than trusted.
        header.append("comment " + " ".join(str(line).split()))
    header.append(f"element vertex {len(xyz)}")
    property_type = {"<f4": "float", "u1": "uchar"}
    header += [f"property {property_type[dt]} {name}" for name, dt in fields]
    header.append("end_header")

    table = np.empty(len(xyz), dtype=fields)
    table["x"], table["y"], table["z"] = xyz[:, 0], xyz[:, 1], xyz[:, 2]
    if normals is not None:
        table["nx"], table["ny"], table["nz"] = normals.T
    if rgb is not None:
        table["red"], table["green"], table["blue"] = rgb.T

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(("\n".join(header) + "\n").encode("ascii"))
        handle.write(table.tobytes())
    return path


def read_ply_header(path: str | Path) -> dict:
    """Vertex count and property names, without reading the body.

    Enough for a consumer to report what a sidecar holds -- or for a test to
    assert what was written -- without loading several million points.
    """
    with open(path, "rb") as handle:
        lines = []
        while True:
            line = handle.readline()
            if not line:
                raise ValueError(f"{path}: end of file before end_header")
            text = line.decode("ascii", "replace").strip()
            lines.append(text)
            if text == "end_header":
                break

    count, properties, fmt = 0, [], ""
    for text in lines:
        if text.startswith("format "):
            fmt = text.split(None, 1)[1]
        elif text.startswith("element vertex "):
            count = int(text.split()[2])
        elif text.startswith("property "):
            properties.append(text.split()[-1])
    return {"count": count, "properties": properties, "format": fmt,
            "header_bytes": sum(len(x) + 1 for x in lines)}
