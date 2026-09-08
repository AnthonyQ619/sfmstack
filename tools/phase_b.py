#!/usr/bin/env python3
"""Phase B: the alternate legs.

Phase A ran ONE fixed pipeline over every corpus capture, which is what a
reference distribution requires. This campaign runs the modules that pipeline
never touched, each on the captures it exists for, and each as a **single-stage
swap against the reference** so the comparison has one variable in it.

Two things come out of that shape that Phase A could not produce:

1. **A rung validation.** `ladder.md` says a rung is validated by comparing two
   models of the SAME capture at EQUAL registration, where a ground-truth
   comparison is legitimate. The optimizer leg gives exactly that, by
   construction: bundle adjustment does not add or drop cameras, so global and
   local BA of one sparse model register identically and differ only in what the
   solve did.

2. **Whether the reference's three collapses were reachable at all.** A capture
   that no configuration registers is a different claim from one that the
   reference configuration happened to lose, and only an alternate leg can tell
   them apart.

Run against the Phase A store, deliberately: every stage upstream of the swap is
recipe-identical, so it is served from the artifact cache and the leg pays only
for what actually differs.

    tools/phase_b.py --store ~/sfm-phase-a-store --legs ba_local
    tools/phase_b.py --store ~/sfm-phase-a-store          # every leg
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "packages" / "sfmorch" / "src"))
sys.path.insert(0, str(REPO / "packages" / "sfmkit" / "src"))
sys.path.insert(0, str(REPO / "tools"))

from gt_poses import gt_for_scene, relative_pose_error  # noqa: E402
from phase_a import DATASETS, corpus, scene_params  # noqa: E402
from sfmorch.health import components  # noqa: E402
from sfmorch.mcp_server import build_service  # noqa: E402

# ---------------------------------------------------------------------------
# The reference stages, as reusable pieces. A leg is the reference with ONE of
# these replaced -- anything more and the comparison stops being attributable.

SIFT = ("FeatureDetectionSIFT", "features", {"scene": "scene"}, {})
LIGHTGLUE = ("FeatureMatchLightGlue", "matches",
             {"scene": "scene", "features": "features"},
             {"pairing": "exhaustive"})
TRACKS = ("FeatureTrackUnionFind", "tracks",
          {"scene": "scene", "matches": "matches"}, {})
POSE = ("PoseEssentialToPnP", "poses", {"scene": "scene", "tracks": "tracks"}, {})
SPARSE = ("SparseTriangulation", "sparse",
          {"scene": "scene", "tracks": "tracks", "poses": "poses"}, {})
BA_GLOBAL = ("BundleAdjustmentGlobal", "refined",
             {"scene": "scene", "sparse": "sparse"}, {})

# A detector-free matcher publishes no `feature_index`, so the tracker has no
# keypoint identity to union on and merges endpoints by proximity instead. The
# module's own diagnostic names the setting; it is not a tuning choice here.
TRACKS_PROXIMITY = ("FeatureTrackUnionFind", "tracks",
                    {"scene": "scene", "matches": "matches"},
                    {"merge_eps_px": 2.0})

# The captures the reference pipeline abandoned most of, in order. These are
# where a detector-free or feed-forward branch is being asked the question it
# exists to answer, rather than being run for coverage.
COLLAPSED = ["/ETH/electro", "/ETH/office", "/ETH/meadow"]
PARTIAL = ["/ETH/playground", "/ETH/relief", "/ETH/kicker", "/DTU/scan10"]

# The captures the detection-phase campaign drove cold. ORB is run on these and
# not on the corpus at large so its readings sit beside the other detectors'
# under one protocol.
DETECTION_PHASE = ["/DTU/scan33", "/ETH/facade", "/DTU/scan15", "/DTU/scan10"]


def leg(pipeline, captures, why):
    return {"pipeline": pipeline, "captures": captures, "why": why}


LEGS = {
    # --- the rung validation -------------------------------------------------
    "ba_local": leg(
        [SIFT, LIGHTGLUE, TRACKS, POSE, SPARSE,
         ("BundleAdjustmentLocal", "refined",
          {"scene": "scene", "sparse": "sparse"}, {})],
        None,  # every capture
        "Equal registration by construction, so a ground-truth comparison "
        "between the two models is legitimate -- the one comparison that can "
        "validate a rung rather than define one."),

    # --- detection starves ---------------------------------------------------
    "loftr": leg(
        [("FeatureMatchLoFTR", "matches", {"scene": "scene"},
          {"pairing": "exhaustive", "resize_long_edge": 840}),
         TRACKS_PROXIMITY, POSE, SPARSE, BA_GLOBAL],
        COLLAPSED + ["/ETH/playground"],
        "Detector-free semi-dense matching where the classical branch "
        "registered almost nothing. Tests whether the capture is unreachable "
        "or the configuration was."),

    "roma": leg(
        [("FeatureMatchRoMa", "matches", {"scene": "scene"},
          {"pairing": "exhaustive"}),
         TRACKS_PROXIMITY, POSE, SPARSE, BA_GLOBAL],
        ["/ETH/meadow", "/ETH/office"],
        "The densest matcher in the registry, on the two smallest collapsed "
        "captures -- the only two where its per-pair cost is affordable "
        "exhaustively."),

    "superglue": leg(
        [("FeatureDetectionSuperPoint", "features", {"scene": "scene"}, {}),
         ("FeatureMatchSuperGlue", "matches",
          {"scene": "scene", "features": "features"},
          {"pairing": "exhaustive"}),
         TRACKS, POSE, SPARSE, BA_GLOBAL],
        COLLAPSED,
        "The learned sparse branch, kept sparse: SuperGlue is trained on "
        "SuperPoint, so the pair moves together and the swap is of a branch "
        "rather than of one module."),

    # --- feed-forward --------------------------------------------------------
    "pose_vggt": leg(
        [SIFT, LIGHTGLUE, TRACKS,
         ("PoseVGGT", "poses", {"scene": "scene"}, {}),
         SPARSE, BA_GLOBAL],
        COLLAPSED + PARTIAL,
        "A pose stage that never sees the tracks, on the captures whose "
        "incremental registration stalled. Registration here is a property of "
        "the capture, not of a seed pair."),

    "sparse_vggt": leg(
        [SIFT, LIGHTGLUE, TRACKS, POSE,
         ("SparseVGGT", "sparse",
          {"scene": "scene", "tracks": "tracks", "poses": "poses"}, {}),
         BA_GLOBAL],
        PARTIAL,
        "Learned depth in place of ray intersection, where the reference's "
        "parallax is narrow enough that triangulation is the weak stage."),

    "sparse_mapanything": leg(
        [SIFT, LIGHTGLUE, TRACKS, POSE,
         ("SparseMapAnything", "sparse",
          {"scene": "scene", "tracks": "tracks", "poses": "poses"}, {}),
         BA_GLOBAL],
        PARTIAL,
        "The second feed-forward reconstructor, on the same captures as "
        "sparse_vggt so the two are comparable to each other and not only to "
        "the reference."),

    # --- alternate trackers --------------------------------------------------
    "tapir": leg(
        [SIFT,
         ("FeatureTrackTapir", "tracks",
          {"scene": "scene", "features": "features"}, {}),
         POSE, SPARSE, BA_GLOBAL],
        ["/DTU/scan33", "/ETH/playground", "/ETH/courtyard"],
        "A point tracker in place of match-graph union-find, on an ordered "
        "orbit, a capture the reference half-registered, and a capture it "
        "fully registered -- so the leg has a control."),

    "vggsfm": leg(
        [SIFT,
         ("FeatureTrackVGGSfM", "tracks",
          {"scene": "scene", "features": "features"}, {}),
         POSE, SPARSE, BA_GLOBAL],
        ["/DTU/scan33", "/ETH/playground", "/ETH/courtyard"],
        "The same swap with the second tracker, on the same three captures."),

    "vggsfm_chunked": leg(
        [SIFT,
         ("FeatureTrackVGGSfM", "tracks",
          {"scene": "scene", "features": "features"},
          {"max_points_num": 20480}),
         POSE, SPARSE, BA_GLOBAL],
        ["/DTU/scan33"],
        "The same tracker with its memory chunk lowered, on the capture where "
        "the default ran out of GPU memory. The module documents this dial as "
        "'purely a memory control -- the result is identical whatever it is set "
        "to', which is a claim a campaign can check rather than repeat."),

    # --- detection, cold -----------------------------------------------------
    "orb": leg(
        [("FeatureDetectionORB", "features", {"scene": "scene"}, {})],
        DETECTION_PHASE,
        "The one detector in the registry with no readings at all, run on the "
        "captures the detection-phase campaign drove cold so its numbers sit "
        "beside the others' under one protocol."),
}


def run_leg_capture(svc, leg_name: str, spec: dict, entry: str,
                    frames: int | None, row: dict) -> dict:
    """Fill `row` in place, so a leg that dies mid-pipeline still records the
    stages that ran.

    A leg failing at the sparse step because the stage before it produced
    something unusable is one of the more informative outcomes this campaign
    can have, and the metrics of that stage are the whole content of the
    finding. Losing them to the exception would leave a row saying only that
    something went wrong.
    """
    t0 = time.time()

    scene_out = svc.run("SceneLoader", run_id=row["run_id"],
                        params=scene_params(entry, frames), wait_s=3600)
    if scene_out.get("status") != "ok":
        raise RuntimeError(f"SceneLoader: {scene_out.get('error')}")
    ids = {"scene": scene_out["outputs"]["scene"]}
    row["n_images"] = scene_out["metrics"].get("n_images")

    stage_metrics, stage_seconds = {}, {}
    row["stages"], row["stage_seconds"], row["artifacts"] = (
        stage_metrics, stage_seconds, ids)
    for module, slot, wiring, params in spec["pipeline"]:
        t1 = time.time()
        out = svc.run(module, run_id=row["run_id"],
                      inputs={k: ids[v] for k, v in wiring.items()},
                      params=params, wait_s=14400)
        stage_seconds[module] = round(time.time() - t1, 1)
        if out.get("status") != "ok":
            row["failed_at"] = module
            raise RuntimeError(f"{module}: {out.get('error')}")
        ids[slot] = next(iter(out["outputs"].values()))
        stage_metrics[module] = out["metrics"]
    row["runtime_s"] = round(time.time() - t0, 1)

    # A detection-only leg has no model to profile, and saying so is the honest
    # state rather than reporting an empty profile.
    final = ids.get("refined") or ids.get("sparse")
    if final is None:
        row["profile"] = None
        return row

    store = svc.store
    scene = store.open(ids["scene"])
    model = store.open(final)
    row["profile"] = components(
        model, scene=scene,
        tracks=store.open(ids["tracks"]) if "tracks" in ids else None,
        matches=store.open(ids["matches"]) if "matches" in ids else None)

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
    return row


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--store", default="store_phase_a", type=Path,
                    help="the Phase A store, so upstream stages are cached")
    ap.add_argument("--legs", action="append", default=None,
                    help=f"one of {sorted(LEGS)}; repeatable")
    ap.add_argument("--only", action="append", default=None,
                    help="substring of a capture; narrows every leg")
    ap.add_argument("--frames", type=int, default=None)
    ap.add_argument("--results", default=None, type=Path)
    ap.add_argument("--gpus", default="0,1,2,3")
    ap.add_argument("--no-docker", action="store_true")
    ap.add_argument("--skip-drift-check", action="store_true")
    args = ap.parse_args(argv)

    # Same refusal as Phase A, and it matters more here: this campaign runs ten
    # modules the reference never exercised, which are the ones most likely to
    # have drifted from their source without anyone noticing.
    if not args.skip_drift_check:
        drift = subprocess.run(
            [sys.executable, str(REPO / "tools" / "image_drift.py")],
            capture_output=True, text=True)
        if drift.returncode != 0:
            print(drift.stdout)
            print("REFUSING to run: rebuild the drifted images first. Artifact "
                  "ids do not cover the image, so a store that already holds a "
                  "stale module's output will hand it back.")
            return 1
        print("[drift] every module image matches its source", flush=True)

    names = args.legs or list(LEGS)
    unknown = [n for n in names if n not in LEGS]
    if unknown:
        print(f"unknown leg(s): {unknown}; known: {sorted(LEGS)}")
        return 2

    svc = build_service(
        modules_dir=REPO / "modules",
        store_root=args.store.expanduser().resolve(),
        skills_dir=REPO / "skills",
        use_docker=not args.no_docker,
        mounts=[str(DATASETS)],
        gpus=[int(g) for g in args.gpus.split(",") if g.strip()],
    )

    results_path = (args.results
                    or args.store.expanduser().resolve() / "phase_b_results.json")
    rows = json.loads(results_path.read_text()) if results_path.exists() else []
    done = {(r["leg"], r["capture"]) for r in rows if not r.get("failed")}
    all_captures = corpus()

    for name in names:
        spec = LEGS[name]
        entries = spec["captures"] or all_captures
        if args.only:
            entries = [e for e in entries if any(o in e for o in args.only)]
        print(f"\n=== leg {name}: {len(entries)} capture(s)", flush=True)
        for entry in entries:
            key = (name, entry.strip("/"))
            if key in done:
                print(f"[skip] {name} {entry}", flush=True)
                continue
            print(f"[run ] {name} {entry}", flush=True)
            row = {"leg": name, "capture": entry.strip("/"),
                   "run_id": "phaseB_" + name + "_"
                             + re.sub(r"[^A-Za-z0-9]+", "_", entry).strip("_")}
            try:
                run_leg_capture(svc, name, spec, entry, args.frames, row)
                p = row.get("profile")
                tail = (f"reg={p['registration']:.2f} pts={p['point_count']}"
                        if p else "detection only")
                print(f"[ok  ] {name} {entry}  {row['runtime_s']}s  {tail}",
                      flush=True)
            except Exception as exc:
                row |= {"failed": True,
                        "error": f"{type(exc).__name__}: {exc}",
                        "traceback": traceback.format_exc()[-2000:]}
                print(f"[FAIL] {name} {entry}: {row['error']}", flush=True)
            rows = [r for r in rows
                    if (r["leg"], r["capture"]) != (row["leg"], row["capture"])]
            rows.append(row)
            results_path.write_text(json.dumps(rows, indent=2, default=str))

    ok = sum(1 for r in rows if not r.get("failed"))
    print(f"\nwrote {results_path}  ({ok} of {len(rows)} rows succeeded)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
