---
module: FeatureMatchLightGlue
module_version: 1.0.0
curated_at: 2026-08-08
---

# When LightGlue is not the answer

## Easy scenes

*Symptom:* more matches and longer tracks than a classical matcher, and worse
final accuracy.

Measured on DTU scan1, 10 images, everything downstream identical:

| stack | matches/pair | long_track% | conflict | points | final error |
|---|---:|---:|---:|---:|---:|
| SIFT + NN | 494.9 | 0.491 | 0.004 | 6040 | **0.246 px** |
| SuperPoint + LightGlue | 649.2 | 0.607 | **0.206** | 1834 | 0.645 px |

*Why:* DTU is well-lit, high-texture and turntable-captured — inside SIFT's design
envelope. LightGlue's advantages (repetition, illumination, wide baseline) do not
apply, while its permissive default threshold admits matches the ratio test would
have rejected. Those become contradictory tracks two stages later.

*What to do:* raise `filter_threshold`, or use the classical matcher. This is not a
defect; it is the model being applied outside the regime it was trained for.

**The general lesson**, which is the reason this is recorded so prominently: match
count and track length are not quality. A change that raises both while raising the
tracker's `inconsistent_rate` has made the reconstruction worse. The tracker's
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
sfm_find_modules(produces="pairwise_matches/v1", not_consuming="features/v1")
```

## Planar and rotation-only captures

*Symptom:* `planarity` above 0.9.

Identical to the classical matchers' limitation and not fixable by any matcher:
LightGlue will match a planar scene beautifully and the triangulation will still be
degenerate. The correspondence is not what is failing.

## No GPU

*Symptom:* it works and takes 50x longer.

The module falls back to CPU rather than failing, which is why the measurements in
this repo exist at all. But 55.8s for 45 pairs at 2048 keypoints is not a working
configuration for real captures.

If no GPU is reachable, `FeatureMatchNN` is both faster and — on the evidence above,
for easy scenes — more accurate. The 6.2 GB image is also pure cost in that case.

## What would change the verdict

Recorded so the DTU result is not over-generalised. The comparison should be re-run
on a capture LightGlue is actually aimed at before concluding anything general:

- ETH3D `courtyard` — outdoor, real illumination variation, mixed resolutions.
- Any capture with repeated structure (facades, tiling).
- Sparsely sampled sets where SIFT's descriptor fails across the baseline. The
  measured case in `match_nn`'s limitations file — 6 of DTU's 49 images, where
  SIFT produced 3 disconnected components — is exactly such a test, and LightGlue
  should win it decisively.

I expect the ordering to reverse on all three. It has not been measured.
