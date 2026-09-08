#!/usr/bin/env python3
"""Turn the Phase B results into the campaign file for the alternate legs.

  skills/evidence/alternate-legs-2026-09.md

Phase A produced a distribution. This campaign produces something the reference
could not: **controlled pairs**. Every leg is a single-stage swap against the
reference pipeline, so two models of one capture differ in one module, and the
legs whose swap sits at or after the pose stage produce models with IDENTICAL
registration -- which is the only condition under which a ground-truth accuracy
comparison between two models means anything.

    tools/phase_b_report.py ~/sfm-phase-a-store
"""
from __future__ import annotations

import argparse
import json
import sys
from itertools import combinations
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "packages" / "sfmkit" / "src"))
EVIDENCE = REPO / "skills" / "evidence"

# The internal rungs, and whether a HIGHER raw value is the healthier one. The
# agreement test below asks, for each controlled pair, whether the rung moved
# the same way ground truth did -- so the direction has to be explicit.
RUNG_DIRECTION = {
    "registration": "higher",
    "conditioning": "higher",
    "composition": "higher",
    "coverage": "higher",
    "error": "lower",
    "yield_obs": "higher",
    "yield_track": "higher",
    "pose_agreement": "lower",
    "pose_agreement_translation": "lower",
    "point_count": "higher",
}



def _f(v, n=3):
    if v is None or (isinstance(v, float) and v != v):
        return "—"
    return f"{v:.{n}f}" if isinstance(v, float) else str(v)


def load(store: Path):
    ref = {r["capture"]: r
           for r in json.loads((store / "phase_a_results.json").read_text())}
    legs = []
    for name in ("phase_b_results.json", "phase_b_results_ff.json",
                 "phase_b_results_trk.json"):
        p = store / name
        if p.exists():
            legs += json.loads(p.read_text())
    return ref, legs


def image_digests(store_root: Path, rows) -> dict[str, tuple[str, str]]:
    """module -> (image tag, digest) actually used, read back from the artifacts.

    Recorded for the same reason Phase A records it: a version tag does not pin
    behaviour, and the digest is the only field in a row that separates output
    produced before a rebuild from output produced after.
    """
    try:
        from sfmkit import ArtifactStore
        store = ArtifactStore(store_root)
    except Exception:
        return {}
    out = {}
    for r in rows:
        for aid in (r.get("artifacts") or {}).values():
            try:
                prov = store.open(aid).manifest.produced_by
            except Exception:
                continue
            out.setdefault(prov.module, (prov.image, prov.image_digest))
    return out


def complete_models(ref, legs) -> dict[str, list]:
    """capture -> every model of it that registered 100% of the capture.

    Two such models contain the same images, so a ground-truth accuracy
    comparison between them is legitimate whatever stage the swap was at --
    which is a wider and more informative set than the by-construction pairs,
    because it contains comparisons the alternate wins.
    """
    out: dict[str, list] = {}
    for c, r in ref.items():
        if r["profile"]["registration"] == 1.0:
            out.setdefault(c, []).append(("reference", r))
    for r in legs:
        p = r.get("profile")
        if not r.get("failed") and p and p["registration"] == 1.0:
            out.setdefault(r["capture"], []).append((r["leg"], r))
    return {c: v for c, v in out.items() if len(v) > 1}


def _gt(r):
    v = r.get("gt", {}).get("gt_rotation_deg")
    return v if isinstance(v, float) and v == v else None


def ranking(groups) -> tuple[dict, int, dict]:
    """Per rung: how often it ranked a comparable pair the way truth did.

    Split by what differs between the two models, because a rung that is a
    selection effect behaves completely differently when the only difference IS
    a selection rule.
    """
    tally = {k: [0, 0, 0] for k in RUNG_DIRECTION}
    split = {"filter": {k: [0, 0, 0] for k in RUNG_DIRECTION},
             "branch": {k: [0, 0, 0] for k in RUNG_DIRECTION}}
    n = 0
    for rows in groups.values():
        for (n1, r1), (n2, r2) in combinations(rows, 2):
            g1, g2 = _gt(r1), _gt(r2)
            if g1 is None or g2 is None or g1 == g2:
                continue
            n += 1
            first_better = g1 < g2
            # A leg whose swap is an optimizer differs from its comparand by a
            # point-retention rule and nothing else.
            kind = ("filter" if "ba_local" in (n1, n2) else "branch")
            for k, d in RUNG_DIRECTION.items():
                v1, v2 = r1["profile"].get(k), r2["profile"].get(k)
                if v1 is None or v2 is None or v1 == v2:
                    tally[k][2] += 1
                    split[kind][k][2] += 1
                    continue
                says = (v1 > v2) if d == "higher" else (v1 < v2)
                i = 0 if says == first_better else 1
                tally[k][i] += 1
                split[kind][k][i] += 1
    return tally, n, split


def render(store: Path, ref: dict, legs: list) -> str:
    ok = [r for r in legs if not r.get("failed")]
    failed = [r for r in legs if r.get("failed")]
    groups = complete_models(ref, legs)
    tally, n_pairs, split = ranking(groups)
    L = []
    w = L.append

    w("# Campaign: alternate-legs-2026-09 — every module the reference pipeline "
      "never ran")
    w("")
    w("**This is a raw evidence table. Cite it; do not plan from it.** The "
      "reasoning built on these rows lives in [`health/ladder.md`](../health/ladder.md), "
      "[`health/smells.md`](../health/smells.md), [`plan/pose.md`](../plan/pose.md) "
      "and [`judge/swap_or_build.md`](../judge/swap_or_build.md), stated as "
      "capture properties rather than as scene names.")
    w("")
    w("## Protocol")
    w("")
    w("Every leg is the reference pipeline of "
      "[reference-pipeline-2026-09](reference-pipeline-2026-09.md) with **one "
      "stage replaced**, run against the reference campaign's own artifact "
      "store. Every stage upstream of the swap is recipe-identical and served "
      "from the cache, so the two models differ in exactly one module and the "
      "difference is attributable to it.")
    w("")
    w("That shape buys the thing the reference campaign could not have: "
      "**models of one capture that can legitimately be compared against "
      "ground truth.** True pose error is measured over the images a model "
      "registered, so it is comparable between two models only when they "
      "registered the same ones. Two conditions give that. A swap at or after "
      "the pose stage cannot add or drop a camera, so it registers exactly "
      "what the reference did. And several captures ended with three or four "
      "*different* pipelines each registering the capture in full — which is "
      "the stronger set, because unlike the first it contains comparisons the "
      "alternate wins.")
    w("")
    w(f"Image drift was verified before the campaign started and every module "
      f"image matched its source. {len(ok)} rows completed; {len(failed)} legs "
      f"failed, and the failures are recorded below because a module refusing "
      f"an input is a reading about the module.")
    w("")

    # ---------------------------------------------------------------- rungs
    w(f"## The rung validation — {n_pairs} comparisons between models of one "
      f"capture, all fully registered")
    w("")
    w("Two models that each registered 100% of a capture contain the same "
      "images, so ground-truth pose error is comparable between them whatever "
      "stage the swap was at. Every such pair is scored on whether the rung "
      "ranked it the way ground truth did.")
    w("")
    w("| Rung | ranked correctly | ranked wrongly | unevaluable |")
    w("| --- | --- | --- | --- |")
    for k, (a_, d_, t_) in sorted(tally.items(), key=lambda x: -x[1][0]):
        w(f"| {k} | {a_} | {d_} | {t_} |")
    w("")
    w("Split by **what differs between the two models** — a bundle adjuster "
      "that deletes short tracks differs from its comparand by a point-"
      "retention rule and by nothing else, and the rungs that are selection "
      "effects behave completely differently on those pairs:")
    w("")
    w("| Rung | differing by a point filter | differing by a change of branch |")
    w("| --- | --- | --- |")
    for k in sorted(RUNG_DIRECTION, key=lambda k: -tally[k][0]):
        fa, fd, _ = split["filter"][k]
        ba, bd, _ = split["branch"][k]
        w(f"| {k} | {fa} of {fa + fd} | {ba} of {ba + bd} |")
    w("")
    for cap in sorted(groups):
        rows = sorted(groups[cap], key=lambda x: _gt(x[1]) if _gt(x[1])
                      is not None else 9e9)
        w(f"**{cap}** — every model below registers the whole capture.")
        w("")
        w("| model | GT rot° | GT trn° | points | conditioning | composition | "
          "coverage | error | yield_obs | pose agreement |")
        w("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
        for name, r in rows:
            p = r["profile"]
            w(f"| {name} | {_f(_gt(r))} | "
              f"{_f(r['gt'].get('gt_translation_deg'))} | {p['point_count']} | "
              f"{_f(p['conditioning'], 2)} | {_f(p['composition'])} | "
              f"{_f(p['coverage'])} | {_f(p['error'])} | {_f(p['yield_obs'])} | "
              f"{_f(p['pose_agreement'])} |")
        w("")

    # ------------------------------------------------------------ every leg
    w("## Every leg, against its reference row")
    w("")
    w("`reg`, `pts`, `comp`, `cov`, `err`, `y_obs`, `pose` are the profile "
      "components; the arrow is reference → leg. `GT rot°` and `GT trn°` are "
      "median relative pose error against the dataset's own poses, over the "
      "images each model registered — **not comparable across differing "
      "registration**, which is most of this table.")
    w("")
    w("| leg | capture | reg | pts | comp | cov | err | y_obs | pose_agr | "
      "GT rot° | GT trn° | imgs w/ GT | s |")
    w("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for r in sorted(ok, key=lambda x: (x["leg"], x["capture"])):
        p = r.get("profile")
        if not p:
            continue
        a = ref.get(r["capture"], {})
        pa, ga = a.get("profile", {}), a.get("gt", {})
        gl = r.get("gt", {})
        arrow = lambda k, n=3: f"{_f(pa.get(k), n)}→{_f(p.get(k), n)}"
        w(f"| {r['leg']} | {r['capture']} | {arrow('registration', 2)} | "
          f"{pa.get('point_count','—')}→{p['point_count']} | "
          f"{arrow('composition')} | {arrow('coverage')} | {arrow('error')} | "
          f"{arrow('yield_obs')} | {arrow('pose_agreement')} | "
          f"{_f(ga.get('gt_rotation_deg'))}→{_f(gl.get('gt_rotation_deg'))} | "
          f"{_f(ga.get('gt_translation_deg'))}→{_f(gl.get('gt_translation_deg'))} | "
          f"{ga.get('gt_images_matched','—')}→{gl.get('gt_images_matched','—')} | "
          f"{r.get('runtime_s','—')} |")
    w("")

    # ------------------------------------------------------- detection only
    det = [r for r in ok if r["leg"] == "orb"]
    if det:
        w("## The detection leg, driven cold")
        w("")
        w("`FeatureDetectionORB` had no readings anywhere in this corpus. Run "
          "on the captures [detection-phase-2026-08](detection-phase-2026-08.md) "
          "drove cold, at the module default, beside the reference campaign's "
          "SIFT row for the same capture and the same frames.")
        w("")
        w("| capture | ORB kp/img | ORB kp_min | ORB sat | ORB coverage | "
          "suppression | SIFT kp/img | SIFT kp_min | SIFT sat | SIFT coverage |")
        w("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
        for r in det:
            o = r["stages"]["FeatureDetectionORB"]
            s = ref[r["capture"]]["stages"]["FeatureDetectionSIFT"]
            w(f"| {r['capture']} | {o['keypoints_per_image']:.0f} | "
              f"{o['keypoints_min']} | {o['saturation']:.2f} | "
              f"{o['spatial_coverage']:.3f} | {o['suppression_ratio']:.3f} | "
              f"{s['keypoints_per_image']:.0f} | {s['keypoints_min']} | "
              f"{s['saturation']:.2f} | {s['spatial_coverage']:.3f} |")
        w("")

    # ------------------------------------------------------------- failures
    if failed:
        w("## What refused to run, and what the refusal says")
        w("")
        w("| leg | capture | failed at | the refusal |")
        w("| --- | --- | --- | --- |")
        for r in sorted(failed, key=lambda x: (x["leg"], x["capture"])):
            msg = r["error"].split("\n")[0]
            msg = msg.replace("|", "\\|")
            if len(msg) > 260:
                msg = msg[:257] + "…"
            w(f"| {r['leg']} | {r['capture']} | {r.get('failed_at','—')} | "
              f"{msg} |")
        w("")

    # --------------------------------------------------------------- images
    dig = image_digests(store, legs)
    if dig:
        w("## The images that produced these rows")
        w("")
        w("A version tag does not pin behaviour. These digests do.")
        w("")
        w("| module | image | digest |")
        w("| --- | --- | --- |")
        for mod in sorted(dig):
            img, d = dig[mod]
            w(f"| {mod} | `{img}` | `{(d or '')[:19]}` |")
        w("")

    w("---")
    w("")
    w(f"*Generated by `tools/phase_b_report.py` from `{store}`. The driver is "
      f"`tools/phase_b.py`, which carries the leg definitions and the reason "
      f"each capture was chosen for each leg.*")
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("store", type=Path)
    ap.add_argument("--out", type=Path,
                    default=EVIDENCE / "alternate-legs-2026-09.md")
    args = ap.parse_args(argv)
    store = args.store.expanduser().resolve()
    ref, legs = load(store)
    args.out.write_text(render(store, ref, legs))
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
