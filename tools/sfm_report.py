#!/usr/bin/env python3
"""Render a reconstruction run as a single self-contained HTML file.

    python tools/sfm_report.py <store> <final_artifact_id> -o report.html

Walks the artifact lineage backwards from whatever you point it at, so it works
for any chain -- classical, learned, detector-free -- without being told what the
pipeline was. The artifacts already record their own inputs, parameters, metrics
and diagnostics; this only arranges them.

Self-contained by construction: no CDN, no external fonts, no runtime fetch. The
point cloud is base64 inside the page. That matters because the alternative is a
report that renders correctly today and is a blank page when you open it on a
machine without network, which is exactly when you want to look at a result.
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "packages" / "sfmkit" / "src"))
sys.path.insert(0, str(_ROOT / "packages" / "sfmorch" / "src"))

from sfmkit import ArtifactStore  # noqa: E402
from sfmkit.schema import registry as core_types  # noqa: E402

try:
    from sfmorch.run_record import Run  # noqa: E402
except ImportError:  # the attempts section is omitted rather than the report failing
    Run = None

# The dataviz reference palette. Categorical slots in their validated order;
# status colours are reserved and never reused for a series.
PALETTE = {
    "series": ["#2a78d6", "#eb6834", "#1baf7a", "#eda100",
               "#e87ba4", "#008300", "#4a3aa7", "#e34948"],
    "series_dark": ["#3987e5", "#d95926", "#199e70", "#c98500",
                    "#d55181", "#008300", "#9085e9", "#e66767"],
    "status": {"good": "#0ca30c", "warning": "#fab219",
               "serious": "#ec835a", "critical": "#d03b3b"},
}

STAGE_SLOT = {
    "source": 0, "detection": 1, "matching": 2, "tracking": 3,
    "pose": 4, "sparse": 5, "optimization": 6, "dense": 7,
}

# Payload type -> where it sits in the pipeline. Used to place an ATTEMPT that
# never produced anything: a step that failed still records the inputs it was
# given, and those pin it to a stage as precisely as an output would have.
TYPE_STAGE = [
    ("scene/v1", "source"),
    ("features/v1", "detection"),
    ("pairwise_matches/v1", "matching"),
    ("tracks/v1", "tracking"),
    ("poses/v1", "pose"),
    ("sparse_model/v1", "sparse"),
    ("dense_model/v1", "dense"),
]
STAGE_ORDER = [name for _, name in TYPE_STAGE]
STAGE_OF_TYPE = dict(TYPE_STAGE)


def lineage(store: ArtifactStore, final_id: str) -> list:
    """Every ancestor of `final_id`, in execution order.

    Topological by construction: an artifact's inputs were sealed before it was,
    so ordering by `started_at` and breaking ties on depth gives the run back.
    """
    seen: dict[str, object] = {}

    def walk(artifact_id: str, depth: int = 0):
        if artifact_id in seen:
            return
        try:
            art = store.open(artifact_id)
        except Exception:
            return
        seen[artifact_id] = (depth, art)
        for parent in art.manifest.inputs:
            walk(parent, depth + 1)

    walk(final_id)
    ordered = sorted(seen.values(), key=lambda d: (-d[0], d[1].manifest.produced_by.started_at
                                                   if d[1].manifest.produced_by else ""))
    return [art for _, art in ordered]


def health_of(value, direction: str, healthy) -> str:
    """good / warning / unknown for one metric, from its own declared band.

    The band travels with the metric in the artifact, so nothing here needs a
    table of thresholds -- which is the whole point of `healthy` being part of the
    manifest rather than living in a dashboard.
    """
    if value is None or not healthy:
        return "unknown"
    low, high = healthy
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "unknown"
    if low is not None and v < float(low):
        return "warning"
    if high is not None and v > float(high):
        return "warning"
    return "good"


def collect(store: ArtifactStore, final_id: str):
    steps = []
    for art in lineage(store, final_id):
        prov = art.manifest.produced_by
        steps.append({
            "id": art.id,
            "type": art.type,
            "module": prov.module if prov else "?",
            "version": prov.module_version if prov else "",
            "device": (prov.device if prov else None),
            "seconds": (prov.duration_s if prov else None),
            "params": dict(prov.params) if prov else {},
            "inputs": list(art.manifest.inputs),
            "note": art.manifest.body,
            "metrics": [
                {"name": name, "value": m.value, "direction": m.direction,
                 "healthy": list(m.healthy) if m.healthy else None,
                 "meaning": m.meaning,
                 "health": health_of(m.value, m.direction, m.healthy)}
                for name, m in art.manifest.metrics.items()
            ],
            "diagnostics": [
                {"code": d.code, "severity": d.severity, "message": d.message,
                 "actions": list(d.suggested_actions), "see_also": d.see_also}
                for d in art.manifest.diagnostics
            ],
        })
    return steps



def _innermost(error: str) -> str:
    """'RuntimeError: ValueError: no tracks survived...' -> the ValueError.

    Crossing a container boundary re-raises the module's exception inside the
    transport's own, and each hop prepends a class name. Only the innermost one
    describes what went wrong.
    """
    line = (error or "").strip().splitlines()[0] if error else ""
    while True:
        head, sep, rest = line.partition(": ")
        if sep and head.endswith(("Error", "Exception")) and ": " in rest:
            nxt, _, _ = rest.partition(": ")
            if nxt.endswith(("Error", "Exception")):
                line = rest
                continue
        if len(line) <= 220:
            return line
        cut = line[:220]
        return cut[: cut.rfind(" ")].rstrip(",;:") + "…"


def attempts(store: ArtifactStore, final_id: str, used_ids: set[str]):
    """Everything the run TRIED, not just what ended up in the lineage.

    The lineage answers "what produced this model". It cannot answer "what else
    was tried and why was it abandoned", because a module that failed produced no
    artifact to walk back through, and a module that succeeded but lost a
    comparison leaves an artifact nothing points at.

    `runs/<id>/run.md` has both: it is an append-only record of every attempt,
    including the failures, which is exactly what makes it worth reading here.
    Without this section a report of a five-module chain looks like a pipeline
    somebody knew in advance, when it was usually the third thing tried.
    """
    if Run is None:
        return None

    runs_dir = Path(store.runs_dir)
    if not runs_dir.is_dir():
        return None

    scene_id = ""
    try:
        scene_id = store.open(final_id).manifest.scene
    except Exception:
        pass

    records = []
    for child in sorted(runs_dir.iterdir()):
        if not (child / "run.md").exists():
            continue
        try:
            run = Run.open(child)
        except Exception:
            continue
        # Every run that touched this scene, not only the one that produced the
        # final artifact: a scene is usually worked over several sessions, and
        # the earlier ones are where the abandoned branches are.
        if scene_id and run.scene and run.scene != scene_id:
            continue
        records.append(run)

    if not records:
        return None

    entries: dict[tuple, dict] = {}
    stage_of_module: dict[str, str] = {}
    # Successful steps first, so a module that failed on one attempt and worked on
    # another is placed by where it actually belongs regardless of run order.
    ordered_steps = [
        step for run in records for step in run.steps if step.outputs
    ] + [
        step for run in records for step in run.steps if not step.outputs
    ]
    for step in ordered_steps:
        out_types, out_ids = [], []
        for artifact_id in step.outputs.values():
            out_ids.append(artifact_id)
            try:
                out_types.append(store.open(artifact_id).type)
            except Exception:
                pass

        if out_types:
            stage = STAGE_OF_TYPE.get(out_types[0], "")
            stage_of_module.setdefault(step.module, stage)
        else:
            # No output to take a stage from. If this module succeeded at any
            # point it belongs where that attempt did; otherwise fall back to
            # one stage past the deepest thing it consumed, which is a guess --
            # tracks/v1 feeds both pose and triangulation -- but a bounded one.
            stage = stage_of_module.get(step.module, "")
            if not stage:
                depths = []
                for artifact_id in step.inputs.values():
                    try:
                        in_type = store.open(artifact_id).type
                    except Exception:
                        continue
                    if in_type in STAGE_OF_TYPE:
                        depths.append(STAGE_ORDER.index(STAGE_OF_TYPE[in_type]))
                if depths:
                    stage = STAGE_ORDER[min(max(depths) + 1, len(STAGE_ORDER) - 1)]

        key = (step.module, json.dumps(step.params, sort_keys=True, default=str))
        entry = entries.get(key)
        if entry is None:
            entry = entries[key] = {
                "seq": len(entries),
                "module": step.module,
                "stage": stage,
                "params": dict(step.params),
                "status": "ok",
                "runs": 0,
                "cached": 0,
                "seconds": None,
                "error": "",
                "artifact": out_ids[0] if out_ids else "",
                "used": False,
                "metrics": [],
            }
        entry["runs"] += 1
        if step.cached:
            entry["cached"] += 1
        if step.status == "failed":
            entry["status"] = "failed"
            # First line only. A traceback in a summary table is unreadable,
            # and the message's first line is the part written for a human.
            entry["error"] = _innermost(step.error)
        elif step.duration_s is not None:
            entry["seconds"] = step.duration_s
        if any(a in used_ids for a in out_ids):
            entry["used"] = True

    # Headline numbers come from the artifact rather than the run record: run.md
    # stores whatever the step reported, the artifact stores the metric with its
    # direction and healthy band, and the band is what makes a number readable.
    for entry in entries.values():
        if not entry["artifact"]:
            continue
        try:
            art = store.open(entry["artifact"])
        except Exception:
            continue
        # The type's REQUIRED metrics first. Two attempts at one stage have to be
        # compared on the same numbers, and declaration order is per-module: the
        # bundle adjuster declares its before/after pair first, which says nothing
        # about how its output compares to a triangulator's.
        try:
            required = list(core_types().get(art.type).metrics)
        except Exception:
            required = []
        names = [n for n in required if n in art.manifest.metrics]
        names += [n for n in art.manifest.metrics if n not in names]
        entry["metrics"] = [
            {"name": n, "value": art.manifest.metrics[n].value,
             "health": health_of(art.manifest.metrics[n].value,
                                 art.manifest.metrics[n].direction,
                                 art.manifest.metrics[n].healthy)}
            for n in names[:3]
        ]

    # Which parameters actually differ between two attempts of the same module --
    # the only part of a fifteen-key param block worth putting in a summary row.
    by_module: dict[str, list[dict]] = {}
    for entry in entries.values():
        by_module.setdefault(entry["module"], []).append(entry)
    for group in by_module.values():
        if len(group) < 2:
            for entry in group:
                entry["differs"] = {}
            continue
        keys = {k for entry in group for k in entry["params"]}
        varying = {
            k for k in keys
            if len({json.dumps(e["params"].get(k), default=str) for e in group}) > 1
        }
        for entry in group:
            entry["differs"] = {k: entry["params"].get(k) for k in sorted(varying)}

    # Stage first, then the order they were actually attempted -- alphabetical
    # within a stage would put the bundle adjuster above the triangulator that
    # fed it, which reads as a pipeline nobody ran.
    ordered = sorted(
        entries.values(),
        key=lambda e: (STAGE_ORDER.index(e["stage"]) if e["stage"] in STAGE_ORDER
                       else len(STAGE_ORDER), e["seq"]),
    )
    return {
        "runs": [r.id for r in records],
        "entries": ordered,
        "counts": {
            "total": len(ordered),
            "used": sum(1 for e in ordered if e["used"]),
            "failed": sum(1 for e in ordered if e["status"] == "failed"),
            "superseded": sum(
                1 for e in ordered if e["status"] == "ok" and not e["used"]
            ),
        },
    }


def _pose_source(store: ArtifactStore, art):
    """The artifact whose `poses` file describes this cloud's cameras.

    A sparse model carries its own. A dense one does not -- `dense_model/v1` has
    no pose file -- so the cameras come from the nearest ancestor that has one,
    which is by construction the model the dense stage was run against.
    """
    if art.has("poses"):
        return art
    for ancestor in reversed(lineage(store, art.id)):
        if ancestor.has("poses"):
            return ancestor
    return None


def _b64(a, dtype):
    return base64.b64encode(np.ascontiguousarray(a, dtype=dtype).tobytes()).decode()


def _latest_of_each_kind(store: ArtifactStore, final_id: str):
    """The last sparse model and the last dense model in the lineage.

    The LAST of each kind, not the first: a run that bundle-adjusts produces two
    sparse_model/v1 artifacts and the second is the one anybody wants to look at.
    One per kind rather than all of them, because the viewer's job is to show the
    reconstruction, not to be a diff tool.
    """
    latest: dict[str, object] = {}
    for art in lineage(store, final_id):
        if art.type == "sparse_model/v1":
            latest["sparse"] = art
        elif art.type == "dense_model/v1":
            latest["dense"] = art
    return latest


def _one_cloud(art, kind: str, max_points: int):
    points = art.load("points")
    xyz = np.asarray(points["xyz"], dtype=np.float64)
    rgb = np.asarray(points.get("rgb", np.full((len(xyz), 3), 160)), dtype=np.uint8)
    error = np.asarray(points.get("error", np.zeros(len(xyz))), dtype=np.float64)

    total = len(xyz)
    if total > max_points:
        # Sparse clouds sample by lowest error: a random sample of a cloud with
        # outliers shows you the outliers. A dense cloud has no per-point error
        # and its outliers are spread evenly rather than concentrated in a tail,
        # so an even stride is the honest sample there.
        keep = (np.linspace(0, total - 1, max_points).astype(int) if kind == "dense"
                else np.argsort(error)[:max_points])
        xyz, rgb, error = xyz[keep], rgb[keep], error[keep]

    prov = art.manifest.produced_by
    return {
        "key": kind,
        "kind": kind,
        "module": prov.module if prov else art.id,
        "artifact": art.id,
        "count": int(len(xyz)),
        "total": int(total),
        "_xyz": xyz,
        "rgb": _b64(rgb, "u1"),
        "error": _b64(error, "<f4"),
        # A cloud with no per-point error offers no error colouring rather than
        # offering it over an array of zeros: a control that does nothing is worse
        # than one that is absent.
        "error_max": (float(np.percentile(error, 95)) if error.any() else None),
    }


def scene_payload(store: ArtifactStore, final_id: str, max_points: int):
    """Every viewable cloud in the lineage, plus the cameras, in one frame.

    All of it is centred and scaled by ONE transform so switching between clouds
    does not move the view -- and so the cameras stay where they belong relative
    to whichever cloud is showing. The reference is the sparse model when there is
    one, because that is the geometry everything else was built against; then the
    dense cloud; then, for a pipeline that stops at pose estimation, the camera
    centres themselves.

    Returns None only when there is nothing spatial at all to draw.
    """
    art = store.open(final_id)
    kinds = _latest_of_each_kind(store, final_id)

    clouds = [_one_cloud(a, kind, max_points)
              for kind, a in (("sparse", kinds.get("sparse")),
                              ("dense", kinds.get("dense"))) if a is not None]

    source = _pose_source(store, art)
    centres, axes = [], []
    if source is not None:
        poses = source.load("poses")
        P = np.asarray(poses["cam_from_world"], dtype=np.float64)
        valid = np.asarray(poses["valid"], dtype=bool)
        for k in range(len(P)):
            if not valid[k]:
                continue
            R, t = P[k][:, :3], P[k][:, 3]
            centres.append(-R.T @ t)
            axes.append(R.T)  # columns are the camera x, y, z in world coordinates

    reference = next((c["_xyz"] for c in clouds if c["kind"] == "sparse"), None)
    if reference is None:
        reference = clouds[0]["_xyz"] if clouds else None
    if reference is None or not len(reference):
        reference = np.asarray(centres) if centres else None
    if reference is None or not len(reference):
        return None

    finite = reference[np.isfinite(reference).all(axis=1)]
    centre = np.median(finite, axis=0) if len(finite) else np.zeros(3)
    spread = (np.percentile(np.linalg.norm(finite - centre, axis=1), 90)
              if len(finite) else 1.0)
    spread = float(spread) if spread > 1e-9 else 1.0

    for cloud in clouds:
        cloud["xyz"] = _b64((cloud.pop("_xyz") - centre) / spread, "<f4")

    prov = source.manifest.produced_by if source is not None else None
    return {
        "clouds": clouds,
        "cameras": [
            {"c": ((np.asarray(c) - centre) / spread).tolist(), "R": np.asarray(a).tolist()}
            for c, a in zip(centres, axes)
        ],
        "camera_source": (prov.module if prov else None),
    }


def quaternion_wxyz(R: np.ndarray) -> tuple[float, float, float, float]:
    """Rotation matrix -> (w, x, y, z), Shepperd's method.

    The branch on which diagonal term is largest is not an optimisation: taking
    `w = sqrt(1 + trace)/2` unconditionally divides by a number near zero for
    rotations near 180 degrees, which is exactly where a pose evaluation cares.
    """
    m00, m01, m02 = R[0]
    m10, m11, m12 = R[1]
    m20, m21, m22 = R[2]
    trace = m00 + m11 + m22
    if trace > 0:
        s = np.sqrt(trace + 1.0) * 2
        q = (0.25 * s, (m21 - m12) / s, (m02 - m20) / s, (m10 - m01) / s)
    elif m00 > m11 and m00 > m22:
        s = np.sqrt(1.0 + m00 - m11 - m22) * 2
        q = ((m21 - m12) / s, 0.25 * s, (m01 + m10) / s, (m02 + m20) / s)
    elif m11 > m22:
        s = np.sqrt(1.0 + m11 - m00 - m22) * 2
        q = ((m02 - m20) / s, (m01 + m10) / s, 0.25 * s, (m12 + m21) / s)
    else:
        s = np.sqrt(1.0 + m22 - m00 - m11) * 2
        q = ((m10 - m01) / s, (m02 + m20) / s, (m12 + m21) / s, 0.25 * s)
    q = np.asarray(q, dtype=np.float64)
    # Sign is a gauge freedom (q and -q are the same rotation). Fixing w >= 0
    # means two exports of the same pose compare equal componentwise.
    if q[0] < 0:
        q = -q
    return tuple(float(v) for v in q / np.linalg.norm(q))


POSE_CONVENTION = (
    "cam_from_world: X_camera = R @ X_world + t. Quaternions are (w, x, y, z) "
    "and encode that same R. This is COLMAP's convention, so the .txt below is a "
    "valid images.txt."
)


def pose_exports(store: ArtifactStore, final_id: str):
    """The estimated poses, in the two forms an evaluation actually wants.

    A reconstruction's poses are the part you compare against ground truth --
    relative rotation and translation-direction error, AUC at 5/10/30 degrees --
    and none of that is reachable from an npz without this repository. So the
    report carries them out.

    Two files rather than one because the two audiences want different things:

      * `images.txt` in COLMAP's format, which every existing evaluation script
        and pycolmap itself already read. No intrinsics: images.txt has nowhere to
        put them, and relative-pose error does not need them.
      * `poses.json`, explicit and self-describing -- rotation matrices AND
        quaternions, the translation, the intrinsics when the artifact carries
        them, the unregistered images listed as such, and the convention written
        out in words. Nothing to infer.

    Unregistered images appear in the json marked `registered: false` and are
    absent from images.txt, which has no way to say "no pose" -- an evaluation
    that silently scores them as identity would be measuring nothing.
    """
    art = store.open(final_id)
    source = _pose_source(store, art)
    if source is None:
        return []

    poses = source.load("poses")
    P = np.asarray(poses["cam_from_world"], dtype=np.float64)
    valid = np.asarray(poses["valid"], dtype=bool)
    index = np.asarray(poses.get("image_index", np.arange(len(P))), dtype=int)

    names = None
    scene_id = source.manifest.scene
    if scene_id:
        try:
            names = [str(n) for n in store.open(scene_id).load("images", "names")]
        except Exception:
            names = None

    K_all = None
    if source.has("intrinsics"):
        data = source.load("intrinsics")
        K = np.asarray(data["K"], dtype=np.float64)
        cam_index = data.get("camera_index")
        if cam_index is None:
            cam_index = np.arange(len(K))
        K_all = {int(i): K[min(int(c), len(K) - 1)].tolist()
                 for i, c in zip(index, np.asarray(cam_index, dtype=int))}

    prov = source.manifest.produced_by
    module = prov.module if prov else source.id

    def name_of(frame: int) -> str:
        if names and 0 <= frame < len(names):
            return names[frame]
        return f"{frame:06d}"

    registered = [(int(index[k]), P[k]) for k in range(len(P)) if valid[k]]

    lines = [
        "# Camera poses estimated by sfmstack.",
        f"# module: {module}   artifact: {source.id}",
        f"# {POSE_CONVENTION}",
        f"# {len(registered)} of {len(P)} images registered; unregistered images "
        f"are OMITTED rather than written as identity.",
        "# Image list with two lines of data per image:",
        "#   IMAGE_ID, QW, QX, QY, QZ, TX, TY, TZ, CAMERA_ID, NAME",
        "#   POINTS2D[] as (X, Y, POINT3D_ID)",
        f"# Number of images: {len(registered)}",
    ]
    for n, (frame, matrix) in enumerate(registered, start=1):
        w, x, y, z = quaternion_wxyz(matrix[:, :3])
        t = matrix[:, 3]
        lines.append(
            f"{n} {w:.9f} {x:.9f} {y:.9f} {z:.9f} "
            f"{t[0]:.9f} {t[1]:.9f} {t[2]:.9f} 1 {name_of(frame)}"
        )
        lines.append("")  # the POINTS2D line, empty: this is a pose export

    document = {
        "produced_by": {"module": module, "artifact": source.id,
                        "type": source.type},
        "convention": POSE_CONVENTION,
        "registered": len(registered),
        "images": [
            {
                "image_index": int(index[k]),
                "name": name_of(int(index[k])),
                "registered": bool(valid[k]),
                "cam_from_world": P[k].tolist() if valid[k] else None,
                "quaternion_wxyz": (list(quaternion_wxyz(P[k][:, :3]))
                                    if valid[k] else None),
                "translation": P[k][:, 3].tolist() if valid[k] else None,
                "K": (K_all or {}).get(int(index[k])),
            }
            for k in range(len(P))
        ],
    }

    def entry(name, text, note):
        raw = text.encode()
        return {
            "artifact": source.id, "module": module, "type": source.type,
            "name": f"{module}-{name}", "bytes": len(raw), "points": None,
            "note": note, "path": None,
            "data": base64.b64encode(raw).decode(),
        }

    return [
        entry("images.txt", "\n".join(lines) + "\n",
              "COLMAP images.txt — loads in pycolmap and in existing evaluation code"),
        entry("poses.json", json.dumps(document, indent=2),
              "explicit matrices, quaternions and intrinsics, convention written out"),
    ]


def downloads(store: ArtifactStore, final_id: str, max_embed_mb: float):
    """Point-cloud sidecars in the lineage, embedded when small enough.

    The `.ply` is the one artifact file that is useful outside this framework --
    MeshLab, CloudCompare, Open3D and every evaluation script read it and none of
    them read the npz. So the report carries it rather than merely mentioning it.

    Embedded as a data: URI, which keeps the report a single self-contained file
    that survives being emailed. Above `max_embed_mb` the path is given instead:
    a 200 MB base64 blob is not a document, and a browser asked to hold one in a
    string will say so.
    """
    found = []
    for art in lineage(store, final_id):
        if "ply" not in art.sidecars():
            continue
        directory = art.sidecar("ply")
        if directory is None:
            continue
        for path in sorted(Path(directory).glob("*.ply")):
            size = path.stat().st_size
            produced = art.manifest.produced_by
            entry = {
                "artifact": art.id,
                "module": produced.module if produced else "",
                "type": art.type,
                "name": f"{produced.module if produced else art.id}-{path.stem}.ply",
                "bytes": int(size),
                "points": art.metric("point_count"),
                "note": "binary PLY with per-point colour",
                "path": str(path),
                "data": None,
            }
            if size <= max_embed_mb * 2**20:
                entry["data"] = base64.b64encode(path.read_bytes()).decode()
            found.append(entry)
    return found


def render(steps, cloud, tried, title: str, clouds=None) -> str:
    data = json.dumps({"steps": steps, "cloud": cloud, "tried": tried,
                       "downloads": clouds or [],
                       "palette": PALETTE, "stageSlot": STAGE_SLOT}, default=str)
    return TEMPLATE.replace("__TITLE__", title).replace("__DATA__", data)


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
:root {
  color-scheme: light;
  --page:#f9f9f7; --surface:#fcfcfb; --ink:#0b0b0b; --ink2:#52514e; --muted:#898781;
  --grid:#e1e0d9; --axis:#c3c2b7; --ring:rgba(11,11,11,0.10);
  --good:#0ca30c; --warning:#fab219; --critical:#d03b3b;
  --s1:#2a78d6; --s2:#eb6834; --s3:#1baf7a; --s4:#eda100;
  --s5:#e87ba4; --s6:#008300; --s7:#4a3aa7; --s8:#e34948;
  --viewer-bg:#111114;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --page:#0d0d0d; --surface:#1a1a19; --ink:#ffffff; --ink2:#c3c2b7; --muted:#898781;
    --grid:#2c2c2a; --axis:#383835; --ring:rgba(255,255,255,0.10);
    --s1:#3987e5; --s2:#d95926; --s3:#199e70; --s4:#c98500;
    --s5:#d55181; --s6:#008300; --s7:#9085e9; --s8:#e66767;
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --page:#0d0d0d; --surface:#1a1a19; --ink:#ffffff; --ink2:#c3c2b7; --muted:#898781;
  --grid:#2c2c2a; --axis:#383835; --ring:rgba(255,255,255,0.10);
  --s1:#3987e5; --s2:#d95926; --s3:#199e70; --s4:#c98500;
  --s5:#d55181; --s6:#008300; --s7:#9085e9; --s8:#e66767;
}
* { box-sizing:border-box; }
body {
  margin:0; background:var(--page); color:var(--ink);
  font:15px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif;
}
.wrap { max-width:1180px; margin:0 auto; padding:32px 20px 72px; }
h1 { font-size:26px; margin:0 0 4px; letter-spacing:-0.01em; }
h2 { font-size:19px; margin:40px 0 14px; letter-spacing:-0.01em; }
.sub { color:var(--ink2); margin:0 0 26px; }
.card {
  background:var(--surface); border:1px solid var(--ring);
  border-radius:12px; padding:18px 20px; margin-bottom:14px;
}
/* hero figures */
.hero { display:flex; flex-wrap:wrap; gap:26px; margin:0 0 26px; }
.hero div { min-width:120px; }
.hero .n { font-size:30px; font-weight:640; letter-spacing:-0.02em; font-variant-numeric:tabular-nums; }
.hero .l { color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:0.05em; }
/* pipeline step */
.step { display:flex; gap:14px; align-items:flex-start; }
.dot { width:10px; height:10px; border-radius:50%; margin-top:7px; flex:none; }
.name { font-weight:620; font-size:16px; }
.meta { color:var(--muted); font-size:12.5px; font-variant-numeric:tabular-nums; }
.chip {
  display:inline-block; font-size:11px; padding:1px 7px; border-radius:999px;
  border:1px solid var(--ring); color:var(--ink2); margin-left:6px; vertical-align:1px;
}
/* metric tiles */
.tiles { display:grid; grid-template-columns:repeat(auto-fill,minmax(158px,1fr)); gap:10px; margin-top:14px; }
.tile { border:1px solid var(--ring); border-radius:9px; padding:9px 11px; background:var(--page); }
.tile .k { color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:0.045em;
           white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.tile .v { font-size:19px; font-weight:600; font-variant-numeric:tabular-nums; margin-top:2px; }
.tile .b { font-size:11px; color:var(--muted); font-variant-numeric:tabular-nums; }
.flag { font-size:11px; font-weight:600; }
.flag.warning { color:var(--warning); }
.flag.good { color:var(--good); }
/* diagnostics */
.diag { border-left:3px solid var(--axis); padding:7px 0 7px 12px; margin-top:11px; font-size:13.5px; }
.diag.warn { border-left-color:var(--warning); }
.diag.error { border-left-color:var(--critical); }
.diag.info { border-left-color:var(--s1); }
.diag b { font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:12.5px; }
.diag ul { margin:5px 0 0; padding-left:18px; color:var(--ink2); }
/* params + notes */
details { margin-top:11px; }
summary { cursor:pointer; color:var(--ink2); font-size:13px; }
pre { overflow-x:auto; background:var(--page); border:1px solid var(--ring);
      border-radius:8px; padding:10px 12px; font-size:12.5px; margin:8px 0 0; }
.note { color:var(--ink2); font-size:13.5px; margin-top:10px; }
/* viewer */
#viewer { width:100%; height:560px; display:block; border-radius:10px;
          background:var(--viewer-bg); cursor:grab; touch-action:none; }
#viewer:active { cursor:grabbing; }
.controls { display:flex; flex-wrap:wrap; gap:8px; align-items:center; margin-top:11px; }
.group { display:inline-flex; gap:0; border-radius:7px; overflow:hidden; }
.group button { border-radius:0; margin:0; }
.group button + button { border-left:none; }
.group button:first-child { border-top-left-radius:7px; border-bottom-left-radius:7px; }
.group button:last-child { border-top-right-radius:7px; border-bottom-right-radius:7px; }
.sep { width:1px; height:20px; background:var(--ring); }
button { font:inherit; font-size:13px; padding:5px 12px; border-radius:7px;
         border:1px solid var(--ring); background:var(--surface); color:var(--ink); cursor:pointer; }
button[aria-pressed="true"] { background:var(--s1); border-color:var(--s1); color:#fff; }
.legend { display:flex; gap:14px; align-items:center; font-size:12.5px; color:var(--ink2); margin-left:auto; }

/* point-cloud downloads */
.downloads { display:flex; flex-wrap:wrap; gap:10px; align-items:center; }
a.dl { display:inline-flex; align-items:baseline; gap:8px; font:inherit; font-size:13px;
       padding:7px 14px; border-radius:7px; border:1px solid var(--s1);
       background:var(--s1); color:#fff; text-decoration:none; }
a.dl:hover { filter:brightness(1.08); }
a.dl .meta { font-size:12px; opacity:0.85; font-variant-numeric:tabular-nums; }
code.path { font:12.5px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;
            background:color-mix(in srgb, var(--ink) 7%, transparent);
            padding:2px 6px; border-radius:5px; word-break:break-all; }
.swatch { display:inline-block; width:10px; height:10px; border-radius:2px; margin-right:5px; vertical-align:-1px; }

/* what was tried */
.tried { width:100%; border-collapse:collapse; font-size:13px; }
.tried th { white-space:nowrap; }
.tried td { vertical-align:top; }
.tried tr.failed td { background:color-mix(in srgb, var(--critical) 6%, transparent); }
.tried .mod { font-weight:600; }
.tried .why { color:var(--ink2); font-size:12.5px; }
.tried code { font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:11.5px;
              color:var(--ink2); }
.kv { display:inline-flex; gap:5px; align-items:baseline; margin:0 14px 3px 0;
      white-space:nowrap; }
.kv .k { color:var(--muted); font-size:11px; }
.kv .v { font-variant-numeric:tabular-nums; font-weight:600; font-size:12.5px; }
.varied { display:flex; flex-direction:column; gap:2px; }
.stagerow td { color:var(--muted); font-size:11px; text-transform:uppercase;
               letter-spacing:0.05em; padding-top:14px; border-bottom:none; }
.verdict { font-size:11px; font-weight:600; padding:1px 7px; border-radius:999px;
           border:1px solid var(--ring); white-space:nowrap; }
.verdict.used { color:var(--good); border-color:color-mix(in srgb, var(--good) 40%, transparent); }
.verdict.failed { color:var(--critical); border-color:color-mix(in srgb, var(--critical) 40%, transparent); }
.verdict.superseded { color:var(--ink2); }
.scroll { overflow-x:auto; }
table { border-collapse:collapse; width:100%; font-size:13px; margin-top:8px; }
th,td { text-align:left; padding:6px 10px; border-bottom:1px solid var(--grid); }
th { color:var(--muted); font-weight:600; font-size:11.5px; text-transform:uppercase; letter-spacing:0.04em; }
td.num { text-align:right; font-variant-numeric:tabular-nums; }
</style>
</head>
<body>
<div class="wrap">
  <h1>__TITLE__</h1>
  <p class="sub" id="subtitle"></p>
  <div class="hero" id="hero"></div>

  <h2>Reconstruction</h2>
  <div class="card" id="downloads-card" hidden>
    <div class="downloads" id="downloads"></div>
    <p class="note" id="downloads-note"></p>
  </div>
  <div class="card">
    <canvas id="viewer"></canvas>
    <div class="controls">
      <span class="group" id="c-clouds"></span>
      <button id="c-pts" aria-pressed="true">Points</button>
      <button id="c-cam" aria-pressed="true">Cameras</button>
      <span class="sep"></span>
      <button id="c-rgb" aria-pressed="true">Colour: image</button>
      <button id="c-err" aria-pressed="false">Colour: reprojection error</button>
      <button id="c-reset">Reset view</button>
      <span class="legend" id="legend"></span>
    </div>
    <p class="note">Drag to orbit · wheel to zoom · shift-drag to pan</p>
  </div>

  <h2>What was tried</h2>
  <p class="sub" id="tried-sub"></p>
  <div class="card scroll" id="tried"></div>

  <h2>Pipeline</h2>
  <div id="steps"></div>

  <h2>All metrics</h2>
  <div class="card"><table id="table"></table></div>
</div>

<script>
const DATA = __DATA__;
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const seriesVar = (i) => `var(--s${(i % 8) + 1})`;

function fmt(v) {
  if (v === null || v === undefined) return "—";
  if (typeof v !== "number") return String(v);
  if (Number.isInteger(v)) return v.toLocaleString();
  if (v !== 0 && Math.abs(v) < 0.001) return v.toExponential(2);
  // Thousands separators and at most 3 decimals, trailing zeros dropped: 2170.8,
  // not 2170.800. Tabular figures in the CSS keep columns aligned regardless.
  return v.toLocaleString(undefined, {maximumFractionDigits: 3});
}
function band(h) {
  if (!h) return "";
  const [lo, hi] = h;
  if (lo !== null && hi !== null) return `healthy ${fmt(lo)}–${fmt(hi)}`;
  if (lo !== null) return `healthy ≥ ${fmt(lo)}`;
  if (hi !== null) return `healthy ≤ ${fmt(hi)}`;
  return "";
}

/* ---------- header ---------- */
const total = DATA.steps.reduce((a, s) => a + (s.seconds || 0), 0);
const last = DATA.steps[DATA.steps.length - 1] || {};
const lastMetric = (n) => (last.metrics || []).find(m => m.name === n);
const poseStep = DATA.steps.find(s => s.type === "poses/v1") || {};
const reg = (poseStep.metrics || []).find(m => m.name === "registered_images");
const regFrac = (poseStep.metrics || []).find(m => m.name === "registered_fraction");

// The headline point count is the FINAL cloud's, and its true size rather than
// the sampled one the viewer draws.
const finalCloud = (DATA.cloud && DATA.cloud.clouds.length)
  ? DATA.cloud.clouds[DATA.cloud.clouds.length - 1] : null;

$("#subtitle").textContent =
  `${DATA.steps.length} modules · ` +
  (finalCloud ? `${finalCloud.total.toLocaleString()} points · ` : "") +
  `${total.toFixed(1)}s total`;

const hero = [
  reg ? {n: `${reg.value}${regFrac ? " / " + Math.round(reg.value / regFrac.value) : ""}`, l: "cameras registered"} : null,
  finalCloud ? {n: finalCloud.total.toLocaleString(),
                l: (finalCloud.kind === "dense" ? "dense points" : "3D points")} : null,
  lastMetric("reprojection_error_after") ? {n: fmt(lastMetric("reprojection_error_after").value) + " px", l: "reprojection error"} : null,
  {n: total.toFixed(1) + "s", l: "wall clock"},
].filter(Boolean);
$("#hero").innerHTML = hero.map(h =>
  `<div><div class="n">${esc(h.n)}</div><div class="l">${esc(h.l)}</div></div>`).join("");


/* ---------- what was tried ----------
   The lineage below shows what produced the model. This shows what did not:
   modules that failed leave no artifact to walk back through, and modules that
   worked but lost a comparison leave one nothing points at. Both are in run.md. */
(function () {
  const tried = DATA.tried;
  if (!tried || !tried.entries.length) {
    $("#tried").parentElement && ($("#tried").style.display = "none");
    $("#tried-sub").textContent = "No run record found beside this store.";
    document.querySelectorAll("h2").forEach(h => {
      if (h.textContent === "What was tried") h.style.display = "none";
    });
    $("#tried-sub").style.display = "none";
    $("#tried").style.display = "none";
    return;
  }
  const c = tried.counts;
  $("#tried-sub").textContent =
    `${c.total} module configuration${c.total === 1 ? "" : "s"} attempted across ` +
    `${tried.runs.length} run${tried.runs.length === 1 ? "" : "s"} — ` +
    `${c.used} in the final model, ${c.superseded} superseded, ${c.failed} failed.`;

  const verdict = (e) =>
    e.status === "failed" ? ["failed", "failed"]
    : e.used ? ["used", "in final model"]
    : ["superseded", "superseded"];

  let html = `<table class="tried">
    <thead><tr><th>module</th><th>outcome</th><th>time</th>
    <th>varied</th><th>result</th></tr></thead><tbody>`;
  let stage = null;
  for (const e of tried.entries) {
    if (e.stage !== stage) {
      stage = e.stage;
      html += `<tr class="stagerow"><td colspan="5">${esc(stage || "unplaced")}</td></tr>`;
    }
    const [cls, label] = verdict(e);
    const varied = Object.keys(e.differs || {}).length
      ? `<div class="varied">` + Object.entries(e.differs)
          .map(([k, v]) => `<code>${esc(k)}=${esc(fmt(v))}</code>`).join("") + `</div>`
      : "";
    const result = e.status === "failed"
      ? `<span class="why">${esc(e.error || "no error recorded")}</span>`
      : e.metrics.map(m =>
          `<span class="kv"><span class="k">${esc(m.name)}</span>` +
          `<span class="v">${fmt(m.value)}</span>` +
          (m.health === "warning" ? '<span class="flag warning">⚠</span>' : "") +
          `</span>`
        ).join("");
    html += `<tr class="${cls === "failed" ? "failed" : ""}">
      <td class="mod">${esc(e.module)}${e.runs > 1 ? `<span class="chip">×${e.runs}</span>` : ""}</td>
      <td><span class="verdict ${cls}">${esc(label)}</span></td>
      <td class="num">${e.seconds != null ? e.seconds.toFixed(1) + "s" : "—"}</td>
      <td>${varied}</td>
      <td>${result}</td></tr>`;
  }
  $("#tried").innerHTML = html + "</tbody></table>";
})();

/* ---------- pipeline ---------- */
$("#steps").innerHTML = DATA.steps.map((s, i) => {
  const tiles = s.metrics.map(m => `
    <div class="tile">
      <div class="k" title="${esc(m.meaning || m.name)}">${esc(m.name)}</div>
      <div class="v">${fmt(m.value)}</div>
      <div class="b">${esc(band(m.healthy))}
        ${m.health === "warning" ? '<span class="flag warning">⚠ outside</span>' : ""}
      </div>
    </div>`).join("");
  const diags = s.diagnostics.map(d => `
    <div class="diag ${esc(d.severity)}">
      <b>${esc(d.code)}</b> — ${esc(d.message)}
      ${d.actions.length ? "<ul>" + d.actions.map(a => `<li>${esc(a)}</li>`).join("") + "</ul>" : ""}
    </div>`).join("");
  const params = Object.keys(s.params).length
    ? `<details><summary>parameters</summary><pre>${esc(JSON.stringify(s.params, null, 2))}</pre></details>` : "";
  return `
  <div class="card"><div class="step">
    <span class="dot" style="background:${seriesVar(i)}"></span>
    <div style="flex:1;min-width:0">
      <div><span class="name">${esc(s.module)}</span>
        <span class="chip">${esc(s.type)}</span>
        ${s.device ? `<span class="chip">GPU ${esc(s.device)}</span>` : ""}
      </div>
      <div class="meta">${s.seconds != null ? s.seconds.toFixed(2) + "s" : ""} · ${esc(s.id)}</div>
      <div class="tiles">${tiles}</div>
      ${diags}
      ${s.note ? `<p class="note">${esc(s.note)}</p>` : ""}
      ${params}
    </div>
  </div></div>`;
}).join("");

/* ---------- metric table (the non-visual view of the same numbers) ---------- */
const rows = DATA.steps.flatMap(s => s.metrics.map(m => `
  <tr><td>${esc(s.module)}</td><td>${esc(m.name)}</td>
      <td class="num">${fmt(m.value)}</td><td>${esc(band(m.healthy))}</td>
      <td>${m.health === "warning" ? '<span class="flag warning">⚠ outside</span>'
           : m.health === "good" ? '<span class="flag good">✓ ok</span>' : "—"}</td></tr>`));
$("#table").innerHTML =
  `<thead><tr><th>module</th><th>metric</th><th>value</th><th>band</th><th>state</th></tr></thead>
   <tbody>${rows.join("")}</tbody>`;

/* ---------- downloads ---------- */
(function () {
  const files = DATA.downloads || [];
  if (!files.length) return;
  const mb = b => b < 1024 ? b + " B"
                : b < 1048576 ? (b / 1024).toFixed(0) + " KB"
                : (b / 1048576).toFixed(b < 10485760 ? 2 : 1) + " MB";
  const label = f => f.name.replace(/^[^-]*-/, "");
  const external = [];
  $("#downloads").innerHTML = files.map(f => {
    if (!f.data) { external.push(f); return ""; }
    return `<a class="dl" download="${esc(f.name)}"
              href="data:application/octet-stream;base64,${f.data}"
              title="${esc(f.note || "")}">
              ${esc(label(f))}
              <span class="meta">${
                f.points ? Number(f.points).toLocaleString() + " pts · " : ""}${mb(f.bytes)}</span>
            </a>`;
  }).join("");

  // One line per KIND of file rather than one per file: three buttons with three
  // near-identical captions is noise, and what a reader needs is what each format
  // is FOR.
  const seen = new Set();
  const notes = [];
  for (const f of files) if (f.note && !seen.has(f.note)) { seen.add(f.note); notes.push(esc(f.note)); }
  for (const f of external)
    notes.push(`${esc(label(f))} is ${mb(f.bytes)} — too large to embed. On disk at `
               + `<code class="path">${esc(f.path)}</code>`);
  $("#downloads-note").innerHTML = notes.join("<br>");
  $("#downloads-card").hidden = false;
})();

/* ---------- 3D viewer ---------- */
(function () {
  const scene = DATA.cloud;
  const canvas = $("#viewer");
  if (!scene) { canvas.parentElement.style.display = "none"; return; }

  const dec = (b64, Type) => {
    const bin = atob(b64), buf = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
    return new Type(buf.buffer);
  };

  // Sequential blue ramp for error — one hue, light to dark, never a rainbow.
  const RAMP = ["#cde2fb","#9ec5f4","#6da7ec","#3987e5","#256abf","#184f95","#0d366b"];

  // Every cloud is decoded up front. They share one normalisation, computed
  // host-side from the sparse model, so switching between them does not move the
  // view and the cameras stay where they belong against either.
  const clouds = scene.clouds.map(c => {
    const xyz = dec(c.xyz, Float32Array);
    const rgb = dec(c.rgb, Uint8Array);
    const err = dec(c.error, Float32Array);
    const N = c.count;
    const rgbColour = new Array(N), errColour = new Array(N);
    for (let i = 0; i < N; i++) {
      rgbColour[i] = `rgb(${rgb[i*3]},${rgb[i*3+1]},${rgb[i*3+2]})`;
      const t = Math.min(1, err[i] / (c.error_max || 1));
      errColour[i] = RAMP[Math.min(RAMP.length - 1, Math.floor(t * RAMP.length))];
    }
    return Object.assign({}, c, {xyz, N, rgbColour, errColour});
  });
  const cameras = scene.cameras || [];

  // Frame the whole scene across EVERY cloud and the cameras. Sizing off the
  // active cloud alone would rescale the view on each switch, and the world
  // frame's own scale is arbitrary, so a fixed default distance frames some
  // reconstructions and misses others entirely.
  let radius = 1;
  {
    let r = 0;
    for (const c of clouds)
      for (let i = 0; i < c.N; i++)
        r = Math.max(r, Math.hypot(c.xyz[i*3], c.xyz[i*3+1], c.xyz[i*3+2]));
    for (const cam of cameras)
      r = Math.max(r, Math.hypot(cam.c[0], cam.c[1], cam.c[2]));
    radius = r > 1e-6 ? r : 1;
  }
  const HOME = {yaw: 0.6, pitch: -0.35, dist: radius * 2.2};
  // Frusta are sized against the OBJECT, not the scene radius. The points are
  // normalised so their 90th-percentile distance is 1, and cameras usually sit
  // several object-diameters out — scaling the frusta off the total radius
  // makes them dwarf the thing they are looking at.
  const CAM_SCALE = 0.13;

  let yaw = HOME.yaw, pitch = HOME.pitch, dist = HOME.dist, panX = 0, panY = 0;
  let mode = "rgb";
  let active = 0;                       // which cloud
  let showPoints = clouds.length > 0;   // a pose-only run has none to show
  let showCams = cameras.length > 0;
  const ctx = canvas.getContext("2d", { alpha: false });
  const current = () => clouds[active];

  function resize() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = canvas.clientWidth * dpr;
    canvas.height = canvas.clientHeight * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    draw();
  }

  function rotate(p) {
    const cy = Math.cos(yaw), sy = Math.sin(yaw);
    const cp = Math.cos(pitch), sp = Math.sin(pitch);
    const x = p[0] * cy + p[2] * sy;
    const z = -p[0] * sy + p[2] * cy;
    const y = p[1] * cp - z * sp;
    return [x, y, z * cp + p[1] * sp];
  }

  function draw() {
    const w = canvas.clientWidth, h = canvas.clientHeight;
    ctx.fillStyle = getComputedStyle(document.documentElement)
                      .getPropertyValue("--viewer-bg").trim() || "#111114";
    ctx.fillRect(0, 0, w, h);
    const f = h * 0.9, cx = w / 2 + panX, cy = h / 2 + panY;

    const cloud = current();
    if (showPoints && cloud) {
      // Depth-sorted painter's algorithm. At a few tens of thousands of points
      // this is well inside a frame budget and needs no WebGL context to go wrong.
      const xyz = cloud.xyz, N = cloud.N;
      const order = [];
      for (let i = 0; i < N; i++) {
        const p = rotate([xyz[i*3], xyz[i*3+1], xyz[i*3+2]]);
        const z = p[2] + dist;
        if (z <= 0.05) continue;
        order.push([z, cx + f * p[0] / z, cy + f * p[1] / z, i]);
      }
      order.sort((a, b) => b[0] - a[0]);
      const useError = mode === "err" && cloud.error_max != null;
      const colours = useError ? cloud.errColour : cloud.rgbColour;
      for (const [z, sx, sy, i] of order) {
        const s = Math.max(1.4, Math.min(4.5, 2.4 * radius / z));
        ctx.fillStyle = colours[i];
        ctx.fillRect(sx - s / 2, sy - s / 2, s, s);
      }
    }

    if (showCams) {
      ctx.lineWidth = 1;
      ctx.strokeStyle = "#eb6834";
      ctx.globalAlpha = 0.85;
      const S = CAM_SCALE;
      for (const cam of cameras) {
        // Frustum corners one focal length in front of the centre.
        const corners = [[-1,-0.75,1.4],[1,-0.75,1.4],[1,0.75,1.4],[-1,0.75,1.4]]
          .map(v => [
            cam.c[0] + S*(cam.R[0][0]*v[0] + cam.R[0][1]*v[1] + cam.R[0][2]*v[2]),
            cam.c[1] + S*(cam.R[1][0]*v[0] + cam.R[1][1]*v[1] + cam.R[1][2]*v[2]),
            cam.c[2] + S*(cam.R[2][0]*v[0] + cam.R[2][1]*v[1] + cam.R[2][2]*v[2]),
          ]);
        const project = (p) => {
          const r = rotate(p), z = r[2] + dist;
          return z > 0.05 ? [cx + f*r[0]/z, cy + f*r[1]/z] : null;
        };
        const apex = project(cam.c);
        const pts = corners.map(project);
        if (!apex || pts.some(p => !p)) continue;
        ctx.beginPath();
        for (let k = 0; k < 4; k++) {
          ctx.moveTo(apex[0], apex[1]); ctx.lineTo(pts[k][0], pts[k][1]);
          ctx.moveTo(pts[k][0], pts[k][1]);
          ctx.lineTo(pts[(k+1)%4][0], pts[(k+1)%4][1]);
        }
        ctx.stroke();
      }
      ctx.globalAlpha = 1;
    }
  }

  function sampledText(c) {
    if (!c) return "";
    return c.total > c.N
      ? `${c.N.toLocaleString()} of ${c.total.toLocaleString()} points, `
        + (c.kind === "dense" ? "evenly sampled" : "sampled by lowest error")
      : `${c.N.toLocaleString()} points`;
  }

  function setLegend() {
    const cloud = current();
    const cam = cameras.length
      ? `<span><span class="swatch" style="background:#eb6834"></span>${cameras.length} cameras${
           scene.camera_source ? " · " + esc(scene.camera_source) : ""}</span>`
      : "";
    if (!showPoints || !cloud) { $("#legend").innerHTML = cam; return; }
    const useError = mode === "err" && cloud.error_max != null;
    $("#legend").innerHTML = useError
      ? `<span><span class="swatch" style="background:#cde2fb"></span>0 px</span>
         <span><span class="swatch" style="background:#0d366b"></span>${cloud.error_max.toFixed(2)} px</span>
         ${cam}`
      : `${cam}<span>${esc(cloud.module)} · ${sampledText(cloud)}</span>`;
  }

  let drag = null;
  canvas.addEventListener("pointerdown", e => {
    drag = {x: e.clientX, y: e.clientY, pan: e.shiftKey};
    canvas.setPointerCapture(e.pointerId);
  });
  canvas.addEventListener("pointermove", e => {
    if (!drag) return;
    const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
    if (drag.pan) { panX += dx; panY += dy; }
    else { yaw += dx * 0.006; pitch = Math.max(-1.5, Math.min(1.5, pitch + dy * 0.006)); }
    drag.x = e.clientX; drag.y = e.clientY;
    draw();
  });
  const stop = () => { drag = null; };
  canvas.addEventListener("pointerup", stop);
  canvas.addEventListener("pointercancel", stop);
  canvas.addEventListener("wheel", e => {
    e.preventDefault();
    dist = Math.max(radius * 0.15, Math.min(radius * 40, dist * Math.exp(e.deltaY * 0.0012)));
    draw();
  }, {passive: false});

  const press = (id, on) => {
    const el = $(id);
    if (el) el.setAttribute("aria-pressed", String(on));
  };

  // A control that does nothing is worse than one that is absent, so each is
  // removed rather than disabled when its subject does not exist: no cameras on
  // a run with no poses, no error colouring on a cloud with no per-point error,
  // no cloud selector with one cloud.
  if (!cameras.length) $("#c-cam").remove();
  if (!clouds.length) { $("#c-pts").remove(); $("#c-rgb").remove(); }

  function syncColourControls() {
    const cloud = current();
    const hasError = !!cloud && cloud.error_max != null && showPoints;
    const err = $("#c-err");
    if (err) err.hidden = !hasError;
    if (!hasError && mode === "err") { mode = "rgb"; press("#c-rgb", true); }
    const rgb = $("#c-rgb");
    if (rgb) rgb.hidden = !showPoints;
  }

  if (clouds.length > 1) {
    // Sparse and dense in the same frame, swapped rather than overlaid: two
    // clouds of the same scene drawn together are indistinguishable from one
    // noisy cloud.
    $("#c-clouds").innerHTML = clouds.map((c, i) =>
      `<button data-cloud="${i}" aria-pressed="${i === active}">${
         esc(c.kind === "dense" ? "Dense" : "Sparse")}</button>`).join("");
    $("#c-clouds").querySelectorAll("button").forEach(btn => {
      btn.onclick = () => {
        active = Number(btn.dataset.cloud);
        showPoints = true;
        press("#c-pts", true);
        $("#c-clouds").querySelectorAll("button").forEach(
          b => b.setAttribute("aria-pressed", String(b === btn)));
        syncColourControls(); setLegend(); draw();
      };
    });
  } else if (clouds.length === 1) {
    $("#c-clouds").remove();
  }

  if ($("#c-pts")) $("#c-pts").onclick = () => {
    showPoints = !showPoints; press("#c-pts", showPoints);
    syncColourControls(); setLegend(); draw();
  };
  if ($("#c-cam")) $("#c-cam").onclick = () => {
    showCams = !showCams; press("#c-cam", showCams); setLegend(); draw();
  };
  if ($("#c-rgb")) $("#c-rgb").onclick = () => {
    mode = "rgb"; press("#c-rgb", true); press("#c-err", false); setLegend(); draw();
  };
  if ($("#c-err")) $("#c-err").onclick = () => {
    mode = "err"; press("#c-rgb", false); press("#c-err", true); setLegend(); draw();
  };
  $("#c-reset").onclick = () => {
    yaw = HOME.yaw; pitch = HOME.pitch; dist = HOME.dist; panX = panY = 0; draw();
  };

  press("#c-pts", showPoints);
  press("#c-cam", showCams);
  syncColourControls();

  window.addEventListener("resize", resize);
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", draw);
  setLegend();
  resize();
})();
</script>
</body>
</html>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("store", type=Path)
    ap.add_argument("artifact", help="the FINAL artifact; lineage is walked backwards")
    ap.add_argument("-o", "--output", type=Path, default=Path("report.html"))
    ap.add_argument("--title", default="SfM reconstruction report")
    ap.add_argument("--max-points", type=int, default=60000)
    ap.add_argument("--max-embed-mb", type=float, default=48.0,
                    help="largest .ply embedded in the report; larger ones are linked by path")
    args = ap.parse_args()

    store = ArtifactStore(args.store)
    if not store.exists(args.artifact):
        print(f"no artifact {args.artifact} in {args.store}", file=sys.stderr)
        return 1

    steps = collect(store, args.artifact)
    cloud = scene_payload(store, args.artifact, args.max_points)
    tried = attempts(store, args.artifact, {s["id"] for s in steps})
    clouds = pose_exports(store, args.artifact) \
        + downloads(store, args.artifact, args.max_embed_mb)
    args.output.write_text(render(steps, cloud, tried, args.title, clouds))

    size_kb = args.output.stat().st_size / 1024
    print(f"{args.output}  ({size_kb:.0f} KB, {len(steps)} steps, "
          f"{tried['counts']['total'] if tried else 0} attempts, "
          f"{'+'.join(str(c['count']) for c in cloud['clouds']) if cloud else 0} points, "
          f"{len(cloud['cameras']) if cloud else 0} cameras, "
          f"{sum(1 for c in clouds if c['data'])}/{len(clouds)} ply embedded)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
