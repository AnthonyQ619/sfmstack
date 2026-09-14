#!/usr/bin/env python3
"""Phase A: the reference campaign.

Drives ONE fixed pipeline over every capture in skills/evidence/CORPUS.txt and
records, per capture, the seven-rung health profile plus the ground-truth pose
error beside it. The output seeds skills/evidence/ with durable per-capture rows
and the reference distribution the run-summary health digest normalises against.

Fixed, not adaptive, and that is the point: a reference corpus has to be one
recipe applied to every capture, or a percentile means "which pipeline ran"
rather than "how healthy is this model". Alternate legs are Phase B.

    tools/phase_a.py --out store_phase_a            # the whole corpus
    tools/phase_a.py --only DTU/scan1 --frames 12   # one capture, quickly
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import traceback
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "packages" / "sfmorch" / "src"))
sys.path.insert(0, str(REPO / "packages" / "sfmkit" / "src"))
sys.path.insert(0, str(REPO / "tools"))

from gt_poses import gt_for_scene, relative_pose_error  # noqa: E402
from sfmorch.health import components  # noqa: E402
from sfmorch.mcp_server import build_service  # noqa: E402

DATASETS = Path("/home/anthonyq/datasets")
DTU_CALIB = DATASETS / "DTU" / "calibration_DTU_new.npz"

# The reference pipeline. SIFT for detection (the most-run detector in the
# registry, and the branch the corpus is best evidenced on), LightGlue for
# matching (the joint assignment reaches connectivity the ratio test does not),
# union-find tracking, incremental pose, ray-intersection triangulation, global
# bundle adjustment. Every parameter left at its module default except pairing,
# which is exhaustive so the view graph is not a function of frame ordering.
REFERENCE = [
    ("FeatureDetectionSIFT", "features", {"scene": "scene"}, {}),
    ("FeatureMatchLightGlue", "matches",
     {"scene": "scene", "features": "features"}, {"pairing": "exhaustive"}),
    ("FeatureTrackUnionFind", "tracks",
     {"scene": "scene", "matches": "matches"}, {}),
    ("PoseEssentialToPnP", "poses", {"scene": "scene", "tracks": "tracks"}, {}),
    ("SparseTriangulation", "sparse",
     {"scene": "scene", "tracks": "tracks", "poses": "poses"}, {}),
    ("BundleAdjustmentGlobal", "refined",
     {"scene": "scene", "sparse": "sparse"}, {}),
]


def corpus() -> list[str]:
    txt = (REPO / "skills" / "evidence" / "CORPUS.txt").read_text()
    return [ln.strip() for ln in txt.splitlines()
            if ln.strip() and not ln.startswith("#")]


def scene_params(entry: str, frames: int | None) -> dict:
    """Loader parameters for a corpus entry like `/DTU/scan1` or `/ETH/office`."""
    fam, name = entry.strip("/").split("/")
    if fam == "DTU":
        p = {"image_dir": str(DATASETS / "DTU" / name),
             "calibration_path": str(DTU_CALIB)}
    else:
        base = DATASETS / "ETH" / name
        p = {"image_dir": str(base / "images" / "dslr_images_undistorted"),
             "calibration_path": str(base / "dslr_calibration_undistorted"
                                     / "calibration_ETH_new.npz")}
    p |= {"resize": "auto", "max_edge": 1024}
    if frames:
        p |= {"max_images": frames, "sampling": "head"}
    return p


def run_capture(svc, entry: str, frames: int | None) -> dict:
    """One capture through the reference pipeline, returning its evidence row."""
    run_id = "phaseA_" + re.sub(r"[^A-Za-z0-9]+", "_", entry).strip("_")
    row: dict = {"capture": entry.strip("/"), "run_id": run_id}
    t0 = time.time()

    scene_out = svc.run("SceneLoader", run_id=run_id,
                        params=scene_params(entry, frames), wait_s=3600)
    if scene_out.get("status") != "ok":
        raise RuntimeError(f"SceneLoader: {scene_out.get('error')}")
    ids = {"scene": scene_out["outputs"]["scene"]}
    row["n_images"] = scene_out["metrics"].get("n_images")

    stage_metrics = {}
    for module, slot, wiring, params in REFERENCE:
        out = svc.run(module, run_id=run_id,
                      inputs={k: ids[v] for k, v in wiring.items()},
                      params=params, wait_s=7200)
        if out.get("status") != "ok":
            raise RuntimeError(f"{module}: {out.get('error')}")
        ids[slot] = next(iter(out["outputs"].values()))
        stage_metrics[module] = out["metrics"]
        # After a refinement the service may solve the chain a second time
        # (escaped points at the pose stage). The model the pipeline delivers
        # is the one it kept, so that is the one the reference records.
        second = out.get("second_solve")
        if second and second.get("status") not in (None, "pending"):
            row["second_solve"] = {k: second.get(k)
                                   for k in ("status", "kept_window", "kept")}
            if second.get("kept"):
                ids[slot] = second["kept"]
                stage_metrics[module] = {
                    n: m.value for n, m in
                    svc.store.open(second["kept"]).manifest.metrics.items()}
    row["stages"] = stage_metrics
    row["runtime_s"] = round(time.time() - t0, 1)

    store = svc.store
    scene = store.open(ids["scene"])
    model = store.open(ids["refined"])

    # The SAME implementation the run-summary digest calls. Two implementations
    # of one rung would make every percentile meaningless in a way nothing would
    # detect: the reading and the distribution it is scored against have to be
    # the same measurement.
    row["profile"] = components(
        model, scene=scene, tracks=store.open(ids["tracks"]),
        matches=store.open(ids["matches"]))

    cams = model.load("poses", "cam_from_world")
    valid = model.load("poses", "valid")
    image_index = model.load("poses", "image_index")

    names = list(scene.load("images", "names"))
    gt = gt_for_scene(
        names, str(scene.manifest.produced_by.params.get("image_dir", "")))
    if gt:
        est = {int(im): cams[r] for r, (im, ok)
               in enumerate(zip(image_index, valid)) if ok}
        row["gt"] = relative_pose_error(est, gt)
    else:
        row["gt"] = {"gt_pairs": 0, "note": "no ground truth located"}
    row["artifacts"] = ids
    return row


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="store_phase_a", type=Path)
    ap.add_argument("--frames", type=int, default=None,
                    help="cap frames per capture (default: every image)")
    ap.add_argument("--only", action="append", default=None,
                    help="substring of a corpus entry; repeatable")
    ap.add_argument("--results", default=None, type=Path)
    ap.add_argument("--no-docker", action="store_true")
    ap.add_argument("--gpus", default="0,1,2,3",
                    help="comma-separated GPU indices for the containers; pick idle "
                         "ones on a shared machine")
    ap.add_argument("--skip-drift-check", action="store_true",
                    help="do not verify images match source (never for a "
                         "campaign whose rows will be recorded)")
    args = ap.parse_args(argv)

    entries = corpus()
    if args.only:
        entries = [e for e in entries if any(o in e for o in args.only)]

    # A campaign starts with the drift check, not with the first run. An image
    # built before a code edit keeps its version tag, keeps satisfying the
    # artifact cache, and keeps running the old code -- which invalidated this
    # campaign's first attempt after nine captures. Refuse rather than measure
    # something the repository cannot describe.
    if not args.skip_drift_check:
        import subprocess
        drift = subprocess.run(
            [sys.executable, str(REPO / "tools" / "image_drift.py")],
            capture_output=True, text=True)
        if drift.returncode != 0:
            print(drift.stdout)
            if drift.stderr.strip():
                print(drift.stderr[-2000:])
            print("REFUSING to run: rebuild the drifted images first, and use a "
                  "FRESH store -- artifact ids do not cover the image, so an "
                  "existing store hands back what the stale code produced.")
            return 1
        print("[drift] every module image matches its source", flush=True)

    svc = build_service(
        modules_dir=REPO / "modules",
        store_root=args.out.resolve(),
        skills_dir=REPO / "skills",
        use_docker=not args.no_docker,
        mounts=[str(DATASETS)],
        gpus=[int(g) for g in args.gpus.split(",")],
    )

    results_path = args.results or (args.out.resolve() / "phase_a_results.json")
    results_path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    if results_path.exists():
        rows = json.loads(results_path.read_text())
    done = {r["capture"] for r in rows if "profile" in r}

    for entry in entries:
        if entry.strip("/") in done:
            print(f"[skip] {entry} already recorded", flush=True)
            continue
        print(f"[run ] {entry}", flush=True)
        try:
            row = run_capture(svc, entry, args.frames)
            print(f"[ok  ] {entry}  {row['runtime_s']}s  "
                  f"reg={row['profile']['registration']:.2f} "
                  f"pts={row['profile']['point_count']}", flush=True)
        except Exception as exc:
            row = {"capture": entry.strip("/"), "failed": True,
                   "error": f"{type(exc).__name__}: {exc}",
                   "traceback": traceback.format_exc()[-2000:]}
            print(f"[FAIL] {entry}: {row['error']}", flush=True)
        rows = [r for r in rows if r["capture"] != row["capture"]] + [row]
        results_path.write_text(json.dumps(rows, indent=2, default=str))

    print(f"\nwrote {results_path}  ({sum('profile' in r for r in rows)} "
          f"of {len(entries)} captures)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
