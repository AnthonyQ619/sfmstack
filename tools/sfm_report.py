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


def cloud_payload(store: ArtifactStore, final_id: str, max_points: int):
    """The 3D data, as compact base64 arrays.

    Downsampled by keeping the LOWEST-error points rather than at random: the
    point of the viewer is to see the reconstruction, and a random sample of a
    cloud with outliers shows you the outliers. A dense cloud has no per-point
    error, so there the sample is a uniform stride -- which is the right choice
    for it, since a dense cloud's outliers are spread evenly rather than
    concentrated in a tail.
    """
    art = store.open(final_id)
    if art.type not in ("sparse_model/v1", "dense_model/v1"):
        return None
    dense = art.type == "dense_model/v1"

    points = art.load("points")
    xyz = np.asarray(points["xyz"], dtype=np.float64)
    rgb = np.asarray(points.get("rgb", np.full((len(xyz), 3), 160)), dtype=np.uint8)
    error = np.asarray(points.get("error", np.zeros(len(xyz))), dtype=np.float64)

    total = len(xyz)
    if total > max_points:
        if dense:
            keep = np.linspace(0, total - 1, max_points).astype(int)
        else:
            keep = np.argsort(error)[:max_points]
        xyz, rgb, error = xyz[keep], rgb[keep], error[keep]

    source = _pose_source(store, art)
    if source is None:
        P = np.zeros((0, 3, 4))
        valid = np.zeros(0, dtype=bool)
    else:
        poses = source.load("poses")
        P = np.asarray(poses["cam_from_world"], dtype=np.float64)
        valid = np.asarray(poses["valid"], dtype=bool)
    # Camera centres in world coordinates, and the three axes of each camera.
    centres, axes = [], []
    for k in range(len(P)):
        if not valid[k]:
            continue
        R, t = P[k][:, :3], P[k][:, 3]
        centres.append(-R.T @ t)
        axes.append(R.T)  # columns are the camera x, y, z in world coordinates

    # Centre and scale so the viewer opens on the model regardless of the
    # arbitrary world frame the pose estimator chose.
    finite = xyz[np.isfinite(xyz).all(axis=1)]
    centre = np.median(finite, axis=0) if len(finite) else np.zeros(3)
    spread = np.percentile(np.linalg.norm(finite - centre, axis=1), 90) if len(finite) else 1.0
    spread = float(spread) if spread > 1e-9 else 1.0

    def b64(a, dtype):
        return base64.b64encode(np.ascontiguousarray(a, dtype=dtype).tobytes()).decode()

    # A dense cloud has no per-point reprojection error, so the error colouring is
    # not offered rather than being offered over an array of zeros -- a control
    # that does nothing is worse than one that is absent.
    has_error = bool(error.any())

    return {
        "count": int(len(xyz)),
        "total": int(total),
        "kind": "dense" if dense else "sparse",
        "xyz": b64((xyz - centre) / spread, "<f4"),
        "rgb": b64(rgb, "u1"),
        "error": b64(error, "<f4"),
        "error_max": (float(np.percentile(error, 95)) if has_error else None),
        "cameras": [
            {"c": ((np.asarray(c) - centre) / spread).tolist(), "R": np.asarray(a).tolist()}
            for c, a in zip(centres, axes)
        ],
    }


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
      <button id="c-rgb" aria-pressed="true">Colour: image</button>
      <button id="c-err" aria-pressed="false">Colour: reprojection error</button>
      <button id="c-cam" aria-pressed="true">Cameras</button>
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

$("#subtitle").textContent =
  `${DATA.steps.length} modules · ${DATA.cloud ? DATA.cloud.count.toLocaleString() + " points · " : ""}` +
  `${total.toFixed(1)}s total`;

const hero = [
  reg ? {n: `${reg.value}${regFrac ? " / " + Math.round(reg.value / regFrac.value) : ""}`, l: "cameras registered"} : null,
  DATA.cloud ? {n: DATA.cloud.count.toLocaleString(), l: "3D points"} : null,
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

/* ---------- point-cloud downloads ---------- */
(function () {
  const files = DATA.downloads || [];
  if (!files.length) return;
  const mb = b => (b / 1048576).toFixed(b < 1048576 ? 2 : 1) + " MB";
  const bar = $("#downloads");
  const external = [];
  bar.innerHTML = files.map((f, i) => {
    if (!f.data) { external.push(f); return ""; }
    return `<a class="dl" download="${esc(f.name)}"
              href="data:application/octet-stream;base64,${f.data}">
              ${esc(f.module)} point cloud
              <span class="meta">${f.points ? Number(f.points).toLocaleString() + " pts · " : ""}${mb(f.bytes)}</span>
            </a>`;
  }).join("");
  const notes = ["Binary PLY with per-point colour — opens in MeshLab, CloudCompare, "
                 + "Open3D or any evaluation script. The artifact's npz stays authoritative."];
  external.forEach(f => notes.push(
    `${esc(f.module)}'s cloud is ${mb(f.bytes)} — too large to embed. It is on disk at `
    + `<code class="path">${esc(f.path)}</code>`));
  $("#downloads-note").innerHTML = notes.join("<br>");
  $("#downloads-card").hidden = false;
})();

/* ---------- 3D viewer ---------- */
(function () {
  const cloud = DATA.cloud;
  const canvas = $("#viewer");
  if (!cloud) { canvas.parentElement.style.display = "none"; return; }

  const dec = (b64, Type) => {
    const bin = atob(b64), buf = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
    return new Type(buf.buffer);
  };
  const xyz = dec(cloud.xyz, Float32Array);
  const rgb = dec(cloud.rgb, Uint8Array);
  const err = dec(cloud.error, Float32Array);
  const N = cloud.count;

  // Sequential blue ramp for error — one hue, light to dark, never a rainbow.
  const RAMP = ["#cde2fb","#9ec5f4","#6da7ec","#3987e5","#256abf","#184f95","#0d366b"];
  const errColour = new Array(N);
  for (let i = 0; i < N; i++) {
    const t = Math.min(1, err[i] / (cloud.error_max || 1));
    errColour[i] = RAMP[Math.min(RAMP.length - 1, Math.floor(t * RAMP.length))];
  }
  const rgbColour = new Array(N);
  for (let i = 0; i < N; i++)
    rgbColour[i] = `rgb(${rgb[i*3]},${rgb[i*3+1]},${rgb[i*3+2]})`;

  // Frame the whole scene, cameras included. The world frame is the seed
  // camera's and its scale is the seed baseline, so a fixed default distance
  // frames some reconstructions and misses others entirely.
  let radius = 1;
  {
    let r = 0;
    for (let i = 0; i < N; i++)
      r = Math.max(r, Math.hypot(xyz[i*3], xyz[i*3+1], xyz[i*3+2]));
    for (const cam of cloud.cameras)
      r = Math.max(r, Math.hypot(cam.c[0], cam.c[1], cam.c[2]));
    radius = r > 1e-6 ? r : 1;
  }
  const HOME = {yaw: 0.6, pitch: -0.35, dist: radius * 2.2};
  // Frusta are sized against the OBJECT, not the scene radius. The points are
  // normalised so their 90th-percentile distance is 1, and cameras usually sit
  // several object-diameters out -- scaling the frusta off the total radius
  // makes them dwarf the thing they are looking at.
  const CAM_SCALE = 0.13;

  let yaw = HOME.yaw, pitch = HOME.pitch, dist = HOME.dist, panX = 0, panY = 0;
  let mode = "rgb", showCams = true;
  const ctx = canvas.getContext("2d", { alpha: false });

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

    // Depth-sorted painter's algorithm. At a few thousand points this is well
    // inside a frame budget and needs no WebGL context to go wrong.
    const order = [];
    for (let i = 0; i < N; i++) {
      const p = rotate([xyz[i*3], xyz[i*3+1], xyz[i*3+2]]);
      const z = p[2] + dist;
      if (z <= 0.05) continue;
      order.push([z, cx + f * p[0] / z, cy + f * p[1] / z, i]);
    }
    order.sort((a, b) => b[0] - a[0]);
    const colours = mode === "rgb" ? rgbColour : errColour;
    for (const [z, sx, sy, i] of order) {
      const s = Math.max(1.4, Math.min(4.5, 2.4 * radius / z));
      ctx.fillStyle = colours[i];
      ctx.fillRect(sx - s / 2, sy - s / 2, s, s);
    }

    if (showCams) {
      ctx.lineWidth = 1;
      ctx.strokeStyle = "#eb6834";
      ctx.globalAlpha = 0.85;
      const S = CAM_SCALE;
      for (const cam of cloud.cameras) {
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

  const sampled = cloud.total > N
    ? `${N.toLocaleString()} of ${cloud.total.toLocaleString()} points, `
      + (cloud.kind === "dense" ? "evenly sampled" : "sampled by lowest error")
    : `${N.toLocaleString()} points`;

  function setLegend() {
    $("#legend").innerHTML = mode === "rgb"
      ? `<span><span class="swatch" style="background:#eb6834"></span>camera</span>
         <span>${sampled}</span>`
      : `<span><span class="swatch" style="background:#cde2fb"></span>0 px</span>
         <span><span class="swatch" style="background:#0d366b"></span>${cloud.error_max.toFixed(2)} px</span>
         <span><span class="swatch" style="background:#eb6834"></span>camera</span>`;
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

  if (cloud.error_max == null) $("#c-err").remove();
  if (!cloud.cameras.length) $("#c-cam").remove();

  const press = (id, on) => { $(id).setAttribute("aria-pressed", String(on)); };
  $("#c-rgb").onclick = () => { mode = "rgb"; press("#c-rgb", true);
                                if ($("#c-err")) press("#c-err", false); setLegend(); draw(); };
  if ($("#c-err")) $("#c-err").onclick = () => { mode = "err"; press("#c-rgb", false); press("#c-err", true); setLegend(); draw(); };
  if ($("#c-cam")) $("#c-cam").onclick = () => { showCams = !showCams; press("#c-cam", showCams); draw(); };
  $("#c-reset").onclick = () => {
    yaw = HOME.yaw; pitch = HOME.pitch; dist = HOME.dist; panX = panY = 0; draw();
  };

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
    cloud = cloud_payload(store, args.artifact, args.max_points)
    tried = attempts(store, args.artifact, {s["id"] for s in steps})
    clouds = downloads(store, args.artifact, args.max_embed_mb)
    args.output.write_text(render(steps, cloud, tried, args.title, clouds))

    size_kb = args.output.stat().st_size / 1024
    print(f"{args.output}  ({size_kb:.0f} KB, {len(steps)} steps, "
          f"{tried['counts']['total'] if tried else 0} attempts, "
          f"{cloud['count'] if cloud else 0} points, "
          f"{len(cloud['cameras']) if cloud else 0} cameras, "
          f"{sum(1 for c in clouds if c['data'])}/{len(clouds)} ply embedded)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
