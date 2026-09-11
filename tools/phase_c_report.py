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
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def load(d: Path, name: str):
    p = d / name
    return json.loads(p.read_text()) if p.exists() else None


def num(v, p=3):
    return f"{v:.{p}f}" if isinstance(v, (int, float)) else "—"


def capture_anchor(capture: str) -> str:
    """A stable per-capture id so a precedent row can cite THIS capture's rows.

    `evidence/INDEX.md` is keyed on capture kind and carries no measurements;
    each of its rows links here instead, which is what keeps the retrieval file
    free of numbers while leaving the numbers one hop away. Changing this slug
    breaks those links, so it is derived mechanically from the capture name
    rather than written by hand.
    """
    return "cap-" + re.sub(r"[^a-z0-9]+", "-", capture.lower()).strip("-")


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
        out.append(f"| <a id=\"{capture_anchor(c)}\"></a>{c} | `{r['leg']}` | "
                   f"{r['px']} | {p['registration']:.2f} | "
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
    leg = load(d, "legend.json")
    if leg:
        w('<a id="what-the-leg-names-mean"></a>')
        w("")
        w("## What the leg names mean")
        w("")
        n_names = len({r["leg"] for r in leg["rows"]})
        n_amb = len(leg.get("ambiguous", []))
        w(f"**A leg name is a label from the driving script, not a description "
          f"of the pipeline, and {n_amb} of the {n_names} names do not mean one "
          f"thing.** The table below is the authority; read a leg name through "
          f"it rather than through what it looks like it says. Every row is "
          f"read back out of the artifacts themselves — each one records the "
          f"module, the version and the resolved parameters that produced it — "
          f"so this is what ran, not a transcription of what a script says "
          f"should have run.")
        w("")
        w("The worst case, and the reason this table exists: `sup@1600` and "
          "`sup@1024` abbreviate *superseded path* — the pipeline a capture had "
          "been solved with before this campaign — and that path is not the "
          "same pipeline on every capture. On one capture it is SuperPoint into "
          "the global reconstructor; on another it is SIFT with contrast "
          "normalisation into the incremental chain with n-view triangulation. "
          "A reader who expands `sup` to SuperPoint is right about one of them "
          "and wrong about the other. This was caught when a precedent row in "
          "`evidence/INDEX.md` was written from the name and had to be "
          "corrected against the recorded chain.")
        w("")
        w("`loftr` and `roma` each cover two legs that differ only in the "
          "`setting` parameter, which is not a detail: it selects between two "
          "separately trained weight sets, and each module's own tuning notes "
          "say the wrong one costs `inlier_ratio` outright. `mine@1600` covers "
          "two legs that differ in whether contrast normalisation was on.")
        w("")
        w("| leg | on these captures | the chain that actually ran |")
        w("| --- | --- | --- |")
        for r in sorted(leg["rows"], key=lambda x: (x["leg"], x["captures"])):
            star = " ⚠" if r["leg"] in leg.get("ambiguous", []) else ""
            caps = ", ".join(r["captures"])
            chain = " → ".join(f"`{s}`" for s in r["chain"])
            w(f"| `{r['leg']}`{star} | {caps} | {chain} |")
        w("")
        w("⚠ marks a name that covers more than one chain. Working resolution "
          "is in the `px` column of the tables above and is not repeated here.")
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
    auc = load(d, "pose_auc.json")
    if auc:
        w('<a id="pose-accuracy-auc"></a>')
        w("")
        w("## Pose accuracy of the shipped models — AUC@5 and AUC@30")
        w("")
        w("**The convention, because AUC means several things.** Error is "
          "measured on image PAIRS, not absolute poses: a reconstruction is "
          "determined only up to a similarity, so an absolute comparison needs "
          "a gauge alignment whose residual is itself a free parameter, while a "
          "relative rotation is gauge-free and a relative translation is "
          "gauge-free in direction. Per pair, `pose error = max(rotation error, "
          "translation direction error)` in degrees. AUC@t is the normalised "
          "area under the cumulative error curve on [0, t] — 1.0 means every "
          "pair is exact, 0.0 means every pair is worse than t.")
        w("")
        w("**DTU rotations carry the fitted correction below; DTU translations "
          "do not.** So a DTU pose column is bounded by its uncorrected "
          "translation term and understates those models — the rotation columns "
          "beside it are the fair reading for that family.")
        w("")
        w("| capture | leg | pairs | median rot° | median trn° | AUC@5 pose | "
          "AUC@30 pose | AUC@5 rot | AUC@30 rot |")
        w("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
        for r in auc["rows"]:
            w(f"| {r['capture']} | `{r['leg']}` | {r['pairs']} | "
              f"{num(r['rot_median'])} | {num(r['trn_median'])} | "
              f"{num(r['auc5_pose'])} | {num(r['auc30_pose'])} | "
              f"{num(r['auc5_rot'])} | {num(r['auc30_rot'])} |")
        s = auc["summary"]
        p, m = s["pooled"], s["mean_over_scenes"]
        w("")
        w(f"| over {s['n_scenes']} scenes | AUC@5 pose | AUC@30 pose | "
          f"AUC@5 rot | AUC@30 rot |")
        w("| --- | --- | --- | --- | --- |")
        w(f"| pooled over all {s['n_pairs']} pairs | {num(p['auc5_pose'])} | "
          f"{num(p['auc30_pose'])} | {num(p['auc5_rot'])} | {num(p['auc30_rot'])} |")
        w(f"| mean over scenes, each weighted equally | {num(m['auc5_pose'])} | "
          f"{num(m['auc30_pose'])} | {num(m['auc5_rot'])} | {num(m['auc30_rot'])} |")
        w("")
        w("**Read the two summary rows as different questions.** The pooled row "
          "is dominated by whichever scenes contributed the most pairs, and pair "
          "count grows with the square of the images; the mean over scenes gives "
          "a fifteen-image capture the same weight as a fifty-image one. They "
          "agree closely here, which is itself worth knowing — it says no single "
          "scene is carrying the corpus figure.")
        w("")
        w("**Two readings the medians elsewhere in this file cannot give you.**")
        w("")
        w("First, one capture is not like the others: the shallow-relief "
          "interior sits near half on AUC@5 where every other model is above "
          "0.8, and it is the same model the selection rule preferred over a "
          "branch truth ranks far better. The rung table said the two were "
          "close; the error distribution says they are not.")
        w("")
        w("Second, **a median can be excellent while the distribution has a "
          "tail, and AUC is where that shows.** One outdoor site reports one of "
          "the best median rotations in the corpus and one of the worst AUC@30 "
          "figures, which can only mean a subset of its cameras is badly placed "
          "while most are near-exact. Every rung in `health/ladder.md` is a "
          "median, a p75 or a fraction, so none of them can see this; it is the "
          "clearest case in the corpus for reading a distribution rather than a "
          "summary statistic.")
        w("")
    w('<a id="are-these-models-reproducible"></a>')
    w("")
    w("## Are these models reproducible? Mostly, and the cache was hiding the rest")
    w("")
    w("Twelve of the sixteen shipped models run through `PoseEssentialToPnP`, "
      "and all twelve were recomputed across a forced module version change. "
      "The four that use the global reconstructor instead were not, which is "
      "stated as a gap below rather than glossed.")
    w("")
    rec = load(d, "recompute.json")
    if rec:
        same = sum(1 for r in rec if r["identical"])
        w("| capture | points | GT rot° | shipped points | shipped GT rot° | |")
        w("| --- | --- | --- | --- | --- | --- |")
        for r in rec:
            w(f"| {r['capture']} | {r['points']} | {num(r['gt_rot'])} | "
              f"{r['was_points']} | {num(r['was_gt_rot'])} | "
              f"{'identical' if r['identical'] else '**differs**'} |")
        w("")
        w(f"**{same} of {len(rec)} came back bit-identical.** The {len(rec) - same} "
          "that moved did so by around a percent of their points, with their "
          "error against reference geometry moving in the fourth decimal.")
    w("")
    w("**The cause is the in-loop local bundle adjustment, and it is not RANSAC "
      "sampling.** The obvious suspect was the unseeded RANSAC in the "
      "incremental pose module and it was wrong: probed directly and inside "
      "that module's own image, `findEssentialMat(USAC_MAGSAC)` and "
      "`solvePnPRansac(SQPNP)` both return identical results over repeated "
      "unseeded calls on a heavily outlier-contaminated problem, and both "
      "ignore `cv2.setRNGSeed`. A seed parameter written against that "
      "hypothesis was withdrawn when the probe falsified it.")
    w("")
    w("**How it was isolated.** One capture was run end to end in two separate "
      "artifact stores under identical parameters, so both executed rather than "
      "one being served from cache. `scene`, `features`, `matches` and `tracks` "
      "came back with **bit-identical payloads**; `poses` diverged. Re-running "
      "only the pose module from that identical tracks payload with "
      "`local_ba: false` gave bit-identical poses in both stores, and with it "
      "on gave different ones. The local bundle adjustment is a multithreaded "
      "Ceres solve: the same residuals summed in a different order across "
      "threads differ in the last bits, and an incremental method feeds that "
      "back into its next registration until it changes a consensus set. "
      "Untested next step: that solve does not set "
      "`solver_options.num_threads`.")
    w("")
    w("**What is established is about the cache, and it is the part that "
      "generalises.** An unchanged recipe is served from the artifact store and "
      "never re-executed, so nothing ever runs twice to disagree with itself "
      "and a pipeline looks perfectly reproducible whether or not it is. Worse, "
      "the usual check cannot see through it: an artifact id is derived from "
      "the recipe — module, version, parameters, input ids — and not from the "
      "bytes produced, so two artifacts sharing an id are two runs of one "
      "recipe and nothing more. An earlier version of this section reported "
      "upstream stages as bit-identical on the strength of matching ids; that "
      "was a vacuous comparison, and the payload comparison that replaced it is "
      "what the claim above now rests on.")
    w("")
    sp = load(d, "repeat_spread.json")
    if sp:
        w(f"**Both models that moved read slightly worse on both axes, and on "
          f"the one with enough repeats to say so, that is what a top draw "
          f"looks like rather than a model degrading.** {sp['n']} observations "
          f"of a computationally identical chain on that capture:")
        w("")
        w("| points | where it came from |")
        w("| --- | --- |")
        for o in sp["observations"]:
            w(f"| {o['points']} | {o['origin']} |")
        w("")
        w(f"They span {sp['range']} points, {sp['range_pct']:.2f}% of the "
          f"largest, with a standard deviation of {sp['sd']}. **The shipped "
          f"value is the highest of the {sp['n']}.** So the recompute reading "
          f"lower is the expected consequence of having recorded the best of "
          f"several draws, and the honest summary of that capture's point count "
          f"is the spread rather than any one of these numbers. The other "
          f"capture that moved has only two observations, so nothing of the "
          f"kind can be said about it — it is lower by under a percent, and "
          f"that is all the evidence supports.")
        w("")
    w("**Nothing shipped was replaced.** These runs produced new artifacts "
      "beside the originals, which still exist unchanged with the point counts "
      "in the shipped table above.")
    w("")
    w("**The gap.** The four shipped models built by the global reconstructor "
      "were never recompute-checked, so nothing here says whether that branch "
      "reproduces. One of the twelve above was also nearly missed for a reason "
      "worth repeating: an earlier spot check re-ran that capture on its "
      "*global* branch, which is not the branch it shipped, and the sweep that "
      "followed then treated it as covered. Checking that a re-run used the "
      "pipeline the capture actually shipped is not automatic.")
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
