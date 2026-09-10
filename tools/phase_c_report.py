#!/usr/bin/env python3
"""Generate `skills/evidence/agentic-campaign-2026-09.md` from the run data.

The campaign: the six-step agentic loop driven over every corpus capture at full
frame count, planning only from retrievable context. This writes the raw tables
so the claims made in `plan/`, `health/` and `judge/` can be traced back and
re-run, which is the thing the seventeen-capture sweep did not do.

    tools/phase_c_report.py --data <scratch dir> [-o <path>]

The data directory holds the campaign's JSON: `all_legs.json` (every leg with
its health profile and ground-truth error), `band.json` (motion readings against
the outcome under the cheap classical branch), `headtest.json`, `exp_e.json`,
`gtsam_control.json` and `spswap.json`.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def load(d: Path, name: str):
    p = d / name
    return json.loads(p.read_text()) if p.exists() else None


def num(v, p=3):
    return f"{v:.{p}f}" if isinstance(v, (int, float)) else "—"


def shipped_table(legs) -> list[str]:
    """Best model per capture: registration first, then the accounting rungs."""
    best: dict[str, dict] = {}
    for r in legs:
        p = r["profile"]
        key = (p["registration"], p.get("point_count") or 0)
        if r["capture"] not in best or key > best[r["capture"]]["_k"]:
            best[r["capture"]] = dict(r, _k=key)
    out = ["| capture | pipeline | px | reg | points | GT rot° | GT trn° |",
           "| --- | --- | --- | --- | --- | --- | --- |"]
    for c in sorted(best):
        r = best[c]
        p = r["profile"]
        out.append(f"| {c} | `{r['leg']}` | {r['px']} | {p['registration']:.2f} | "
                   f"{p.get('point_count') or 0} | {num(r.get('gt_rot'))} | "
                   f"{num(r.get('gt_trn'))} |")
    return out


def band_table(band) -> list[str]:
    out = ["| capture | imgs | reg on the cheap branch | `overall_magnitude` full | "
           "`high_motion_tail` full | `overall_magnitude` at the 12-frame head |",
           "| --- | --- | --- | --- | --- | --- |"]
    for r in sorted(band, key=lambda x: x["reg_nn"] if x["reg_nn"] is not None else -1):
        out.append(f"| {r['capture']} | {r.get('n') or '—'} | {num(r['reg_nn'])} | "
                   f"{num(r['full_mag'], 4)} | {num(r['full_tail'], 4)} | "
                   f"{num(r['head_mag'], 4)} |")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("-o", "--out", type=Path,
                    default=REPO / "skills" / "evidence" / "agentic-campaign-2026-09.md")
    a = ap.parse_args(argv)
    d = a.data

    legs = load(d, "all_legs.json") or []
    band = load(d, "band.json") or []
    head = load(d, "headtest.json") or {}
    expe = load(d, "exp_e.json") or {}
    ctl = load(d, "gtsam_control.json") or {}
    sp = load(d, "spswap.json") or {}

    L: list[str] = []
    w = L.append
    w("# Campaign: agentic-campaign-2026-09 — the loop driven over every capture, "
      "planning only from context")
    w("")
    w("**This is a raw evidence table. Cite it; do not plan from it.** The reasoning "
      "built on these rows lives in [`plan/`](../plan/scene_to_pipeline.md), "
      "[`health/ladder.md`](../health/ladder.md) and "
      "[`judge/swap_or_build.md`](../judge/swap_or_build.md), stated as capture "
      "properties rather than as scene names.")
    w("")
    w("## Protocol")
    w("")
    w("Steps 0–6 of the tool loop over every capture in "
      "[CORPUS.txt](CORPUS.txt), at **full frame count**, with every module and "
      "parameter chosen from retrievable context alone. Ground truth was computed "
      "once at the end by a separate script; no plan, parameter or branch choice "
      "saw it.")
    w("")
    w(f"{len(legs)} pipeline legs. Two working resolutions appear: the campaign "
      "opened at `max_edge: 1024`, inherited from the reference driver, and moved "
      "to the loader's own default of 1600 once that was noticed — the `px` column "
      "says which.")
    w("")
    w("## The model shipped for each capture")
    w("")
    w("Selected on registration first and the accounting rungs second, which is the "
      "rule in `health/ladder.md`. Where that rule and ground truth disagree the "
      "disagreement is recorded below rather than hidden by the selection.")
    w("")
    L.extend(shipped_table(legs))
    w("")
    w("**DTU rotations are corrected**; translations are not. See "
      "[the ground-truth section](#the-ground-truth-these-were-scored-against).")
    w("")
    w("**Two captures where that selection rule and ground truth disagree, and "
      "the rule loses.** On a shallow-relief subject two models both registered "
      "the whole capture and the rule preferred the one truth ranks roughly sixty "
      "times worse. On a dim built interior the rule preferred a model with more "
      "points and better coverage that is worse against truth on both axes. In "
      "both cases the branch the rule declined was the one whose poses came from "
      "a global reconstructor, on which the yield rungs cannot be computed at "
      "all — so the tiebreak fell to coverage and point count alone. This is the "
      "hazard `health/ladder.md` now records.")
    w("")
    w("## Every leg")
    w("")
    w("| capture | leg | px | reg | points | coverage | yield_obs | error | "
      "GT rot° | GT trn° |")
    w("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for r in sorted(legs, key=lambda x: (x["capture"], -x["profile"]["registration"])):
        p = r["profile"]
        y = p.get("yield_obs")
        w(f"| {r['capture']} | `{r['leg']}` | {r['px']} | {p['registration']:.2f} | "
          f"{p.get('point_count') or 0} | {num(p.get('coverage'))} | "
          f"{num(y) if y is not None else 'unevaluable'} | {num(p.get('error'))} | "
          f"{num(r.get('gt_rot'))} | {num(r.get('gt_trn'))} |")
    w("")
    w("## The connectivity rule, refitted on full captures")
    w("")
    w("The rule in `plan/scene_to_pipeline.md` §3b was fitted on fourteen captures "
      "at twelve frames with `sampling: head`, and states a clean gap in "
      "`overall_magnitude` between the captures that fragment and those that do "
      "not. These are the readings and the outcomes at full frame count, scored "
      "against the branch the rule is about — a classical detector and a "
      "ratio-test matcher.")
    w("")
    L.extend(band_table(band))
    w("")
    w("**Separation, as the probability that a fragmenting capture reads higher "
      "than a complete one.** No statistic tested produces a clean gap under "
      "either definition of fragmentation.")
    w("")
    w("| statistic | any frame lost (7 vs 9) | reg < 0.8 (4 vs 12) |")
    w("| --- | --- | --- |")
    for name, a1, a2 in (("`high_motion_tail` / √n", 0.921, 0.896),
                         ("`overall_magnitude` / √n", 0.889, 0.896),
                         ("`overall_magnitude` × 12/n", 0.905, 0.896),
                         ("`high_motion_tail`, full capture", 0.905, 0.875),
                         ("`overall_magnitude`, full capture", 0.857, 0.833),
                         ("`pair_p90_across`, full capture", 0.873, 0.771),
                         ("`overall_magnitude` at the 12-frame head", 0.730, 0.938)):
        w(f"| {name} | {a1:.3f} | {a2:.3f} |")
    w("")
    w("## The twelve-frame head sample against the full capture")
    w("")
    w("Every capture rebuilt at the exact fitting protocol — `max_images: 12, "
      "sampling: head` — and read on the same modules.")
    w("")
    w("| capture | `texture_density` head / full | `overall_magnitude` head / full |")
    w("| --- | --- | --- |")
    full = {r["capture"]: r for r in band}
    tex = (load(d, "extra_tables.json") or {}).get("texture_full", {})
    for c in sorted(head):
        h = head[c]
        f = full.get(c, {})
        w(f"| {c} | {num(h.get('texture_density'), 0)} / "
          f"{num(tex.get(c), 0)} | "
          f"{num(h.get('overall_magnitude'), 4)} / {num(f.get('full_mag'), 4)} |")
    w("")
    w("## Experiment E — is `registered_fraction` gated on surviving structure?")
    w("")
    w("The pose stage's triangulation filters swept on healthy tracks (tighten) "
      "and on tracks that had produced full registration with no structure "
      "(relax).")
    w("")
    w("| capture | min angle° | max reproj px | `registered_fraction` | "
      "`points_triangulated` |")
    w("| --- | --- | --- | --- | --- |")
    for k, v in expe.items():
        tag, cap, pj = k.split("|")
        pp = json.loads(pj)
        w(f"| {cap} ({tag}) | {pp['min_triangulation_angle_deg']} | "
          f"{pp['max_reprojection_error']} | {num(v.get('registered_fraction'))} | "
          f"{v.get('points_triangulated')} |")
    w("")
    w("## The n-view triangulator, against the pairwise one")
    w("")
    w("Identical poses and tracks, matched track-length floor, only the "
      "triangulator swapped.")
    w("")
    extra = load(d, "extra_tables.json") or {}
    if extra.get("gtsam_control"):
        w("| triangulator | points | coverage | yield_obs | two-view share | "
          "GT rot° | GT trn° |")
        w("| --- | --- | --- | --- | --- | --- | --- |")
        for r in extra["gtsam_control"]:
            w(f"| {r['leg']} | {r['points']} | {num(r['coverage'])} | "
              f"{num(r['yield_obs'])} | {num(r['two_view'])} | "
              f"{num(r['gt_rot'])} | {num(r['gt_trn'])} |")
    w("")
    w("## A learned detector on three captures a classical one solved")
    w("")
    w("Every leg below ran at `saturation: 0.0`, so the cap is not what is being "
      "measured.")
    w("")
    if extra.get("spswap"):
        w("| capture | leg | reg | points | coverage | GT rot° | GT trn° |")
        w("| --- | --- | --- | --- | --- | --- | --- |")
        for r in extra["spswap"]:
            w(f"| {r['capture']} | `{r['leg']}` | {num(r['reg'], 2)} | "
              f"{r['points']} | {num(r['coverage'])} | {num(r['gt_rot'])} | "
              f"{num(r['gt_trn'])} |")
    w("")
    w('<a id="the-ground-truth-these-were-scored-against"></a>')
    w("")
    w("## The ground truth these were scored against")
    w("")
    w("**DTU carries a fixed per-position rotation offset.** Seven reconstructions "
      "of seven different scenes, sharing only the arm's physical stops, agree "
      "with each other roughly three times more closely than any agrees with the "
      "shipped extrinsics; after the world-gauge alignment their per-position "
      "residuals agree across scans to a third of their own size. Fitting that "
      "correction on six scans and applying it to the held-out seventh takes the "
      "rotation error from 0.53–0.62° to 0.11–0.24°. The mechanism is named in "
      "`tools/gt_poses.py`: the shipped matrices are the rectified camera's and "
      "the working images are the cleaned/distorted set. **The correction is "
      "rotation-only**; the translation column is uncorrected.")
    w("")
    w("**The other family needs no correction.** The same test over eighteen "
      "model pairs finds model-to-model disagreement comparable to or larger than "
      "the best model's disagreement with truth. A method that finds a large "
      "offset on one family and nothing on the other is not manufacturing the "
      "offset.")
    w("")
    w("---")
    w("")
    w("*Generated by `tools/phase_c_report.py`.*")
    a.out.write_text("\n".join(L) + "\n")
    print(f"{a.out}  ({len(L)} lines, {len(legs)} legs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
