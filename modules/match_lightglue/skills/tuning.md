---
module: FeatureMatchLightGlue
module_version: 1.0.0
curated_at: 2026-08-08
---

# Tuning FeatureMatchLightGlue

Two things to establish before tuning anything: that `weights` is right, and that
LightGlue is actually the better matcher for this capture. Both are cheap to check
and both invalidate everything downstream if wrong.

## First: is the weight set right?

`weights: auto` handles the known detectors. If you set it by hand, verify with
`mean_match_score` — healthy is above ~0.5. A low score with a healthy
`inlier_ratio` means wrong weights, not a hard scene.

## Second: is LightGlue winning?

Run `FeatureMatchNN` on the same features and compare the **final** reprojection
error after bundle adjustment, not the match count. On DTU the classical stack won
by 2.6x on the output metric while losing on every intermediate one — see
[SKILL.md](SKILL.md).

This is not a formality. The comparison costs one pipeline run.

## `filter_threshold` — the quality dial

Defaults to 0.1, which is deliberately permissive because geometric verification
follows. On an easy scene that permissiveness is where the conflicts come from.

Raise to 0.2-0.3 when:
- the tracker reports `high_conflict_rate`
- `inlier_ratio` is below 0.5
- final reprojection error is worse than a classical stack's

The metric to judge it by is the tracker's `inconsistent_rate`, not
`matches_per_pair` — you are deliberately trading matches for correctness, so the
match count going down is the intended effect, not a regression.

## `graph_components` above 1

Raise `window`, or use `exhaustive`.

Worth knowing: LightGlue tolerates far wider baselines than SIFT, so a large
`window` is genuinely productive here where a classical matcher would find nothing.
Try 4-8 before concluding the capture is too sparsely sampled.

Conversely — if LightGlue *cannot* link two images, they probably do not overlap.
It is the strongest evidence available that a gap is real rather than a matcher
limitation.

## `inlier_ratio` below 0.5

The healthy floor here is **higher** than for classical matchers (0.7 against 0.5),
because LightGlue's raw output is already filtered by a learned criterion. Below
0.5, in order:

1. **Check `weights`.** This is the most common cause and it is silent.
2. Raise `filter_threshold`.
3. Only then consider the scene degenerate — check `planarity`.

## Speed

`depth_confidence` is the good lever, not `n_layers`. It lets easy pairs exit after
fewer layers while hard pairs still get the full stack; reducing `n_layers` weakens
every pair uniformly. Lower `depth_confidence` to 0.9 for a useful speedup at
minimal cost — the pairs it affects are the easy ones by definition.

`width_confidence` complements it by pruning unpromising keypoints between layers.
Lower to 0.95 when images carry many keypoints. Set either to -1 to disable when
you are measuring accuracy rather than throughput.

`flash` should stay on: faster, less memory, no accuracy effect, and it falls back
silently when unavailable — including on CPU.

## Cost, and a caveat on the numbers

The measured 55.8s for 10 images exhaustive (45 pairs) is **CPU** time. This
Docker daemon cannot pass a GPU through — see `docs/design/DECISIONS.md` — so
every timing recorded for this module is one to two orders of magnitude worse than
it should be, and `expected_duration_s: 90` is calibrated for hardware that is not
currently reachable.

The metrics are unaffected: inference runs under `inference_mode` and is
device-independent.

## Per-image tensors are cached

Not a parameter, but it explains the cost shape: keypoint and descriptor tensors
are built once per image and reused across every pair that image appears in. With
exhaustive pairing each image participates in N-1 pairs, so rebuilding them per
pair would dominate. Cost therefore scales with pair count, not with pair count
times keypoints.
