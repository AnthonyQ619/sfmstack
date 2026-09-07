---
module: FeatureMatchLightGlue
module_version: 1.6.0
curated_at: 2026-08-08
---

# When LightGlue is not the answer

## Captures inside the classical detector's design envelope

*Symptom:* more matches and longer tracks than a classical matcher, and worse
final accuracy.

**The capture properties that produce it**, which is what to check yours against:
well lit, densely and aperiodically textured, short baselines between adjacent
frames, no repeated objects, photometrically stable across the set. Turntable and
studio-rig captures of a textured subject are the common case; so is any short,
slow, evenly-lit walk around something with real surface detail.

*Why:* every advantage this module has — repetition, illumination change, wide
baseline — needs something to act on, and on such a capture none of them do. What
remains is the permissive default threshold, which admits correspondences the ratio
test would have rejected. Those survive two-view verification (they are
geometrically consistent) and become contradictory tracks two stages later, where
the tracker's conflict rate is the first thing that sees them.

*What that costs, one measurement, everything downstream held identical:* the
classical stack finished with roughly **three times the points at roughly a third
of the final reprojection error**, while trailing on matches per pair and on track
length — and with a tracker conflict rate nearly two orders of magnitude lower.
`[observed: 1]` — one capture, so read the direction rather than the factor.

*The trap this sets:* every metric available at the matching stage prefers this
module on such a capture, and the disagreement only becomes visible after bundle
adjustment. **Do not read a matching-stage win as settling it.** Both branches share
one detection artifact, so the A/B costs no re-detection; run it, and if you must
choose before the outcome exists, say which reading you chose on.

*Traceability:* the run behind the numbers above is in
[`skills/evidence/EVIDENCE.md`](../../../skills/evidence/EVIDENCE.md). Do not locate your capture
by matching its readings against that table — check it against the capture
properties in the second paragraph instead. A number that matches a recorded run to
several digits usually means you are reading your own capture back.

*What to do:* raise `filter_threshold`, or use the classical matcher. This is not a
defect; it is the model being applied outside the regime it was trained for.

**The general lesson**, which is the reason this is recorded so prominently: match
count and track length are not quality. A change that raises both while raising
this module's `cycle_merge_rate + cycle_split_rate` — or the tracker's
`inconsistent_rate` one stage later — has made the reconstruction worse. Prefer the
cycle terms when you are still turning the dial: they are on this artifact, and
`inconsistent_rate` has twice been measured sitting flat across the range that
decided the run. The tracker's
tuning file documents the same trap arriving from a completely different cause (a
`ratio_test` sweep). Two independent routes to the same failure signature is worth
internalising.

## Wrong weights are silent

*Symptom:* plausible matches, healthy `inlier_ratio`, `mean_match_score` below ~0.4,
and downstream accuracy that is quietly poor.

*Why no parameter helps:* LightGlue is trained per descriptor type. Given ALIKED
descriptors and SuperPoint weights it still produces an assignment — the attention
mechanism does not know the input distribution is wrong. Geometric verification
does not catch it either, because the surviving matches genuinely come from one
rigid scene.

*What to do:* leave `weights: auto`. It infers from provenance and cross-checks
descriptor width, and refuses rather than guessing on an unknown producer.

*The structural limitation:* inference relies on a table of known detector module
names. A **custom** detector emitting 128-d descriptors is not inferable and needs
`weights` set by hand. The clean fix is an additive optional array in `features/v1`
recording the descriptor type, which would make this self-describing; see
`docs/design/DECISIONS.md`.

## Detector-free captures

*Symptom:* the scene is genuinely textureless and the detector cannot find
repeatable keypoints anywhere.

*Why no parameter helps:* LightGlue matches keypoints. If there are no good
keypoints, a better matcher for them does not help — the information was lost at
detection.

*Switch to:* a detector-free matcher, which estimates correspondence densely with
no interest points at all.

```
sfm_find_alternatives(produces="pairwise_matches/v1", not_consuming="features/v1")
```

## Planar and rotation-only captures

*Symptom:* `planarity` above 0.9.

**Not a matcher problem, and not fixable by swapping matchers.** The explanation
and what to do instead are owned by `plan/matching.md` section 5, "`planarity`
is the one metric here whose answer is not a matcher" -- read it there rather than
here, because three matcher files used to restate it and drifted apart in wording
while agreeing in substance.

## No GPU

*Symptom:* it works and takes 50x longer.

The module falls back to CPU rather than failing, which is why the measurements in
this repo exist at all. But 55.8s for 45 pairs at 2048 keypoints is not a working
configuration for real captures.

If no GPU is reachable, `FeatureMatchNN` is both faster and — on the evidence above,
for easy scenes — more accurate. The 6.2 GB image is also pure cost in that case.

## What would change the verdict

Recorded so the result above is not over-generalised. It is one capture *kind*, and
the comparison should be re-run on a capture this module is actually aimed at
before concluding anything general — that is, one where at least one of its
advantages has something to act on:

- **Outdoor, with real illumination variation across the set.**
- **Repeated structure** — a facade of identical bays, tiling, a row of castings.
- **Sparsely sampled**, so adjacent frames are far enough apart that a classical
  descriptor fails across the baseline. `match_nn`'s limitations file records such
  a case, where thinning a set until the baseline widened left the classical branch
  in three disconnected components; this module should win that decisively.

Since the original writing, the direction has held on captures of the second and
third kinds: on fast, widely-spaced captures the joint matcher roughly doubled the
surviving pair count and lifted every image off a single-edge connection, where the
ratio test left two images one pair from being lost. So the split is not
"LightGlue is worse" — it is that **the two branches win on different capture
properties, and the matching stage's own metrics only see one of the two.**

I expect the ordering to reverse on all three. It has not been measured.
