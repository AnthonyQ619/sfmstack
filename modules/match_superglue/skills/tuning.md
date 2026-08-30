---
module: FeatureMatchSuperGlue
module_version: 1.6.0
curated_at: 2026-08-10
---

# Tuning FeatureMatchSuperGlue

1. `graph_components` — above 1 nothing downstream can recover.
2. `inlier_ratio` — for a learned matcher this should be high; below 0.5 something
   is wrong with the pairing or the weights, not with the threshold.
3. `keypoints_used` against the detector's `keypoints_per_image`.
4. `matches_per_pair` and `mean_match_score` last.

## Reference run

A turntable capture of a compact object, 12 contiguous images, `max_edge: 1024`, SuperPoint at defaults,
`pairing: sequential`, `window: 1`, `weights: outdoor`, on GPU in a container:

| metric | value |
|---|---|
| `pairs_matched` | 11 of 11 |
| `matches_per_pair` | 1102.6 |
| `inlier_ratio` | 0.992 |
| `mean_match_score` | 0.874 |
| `keypoints_used` | 2020.2 |
| `graph_components` | 1 |
| runtime | 5.9 s |

LightGlue on the identical features gives 1089.1 / 0.991 / 0.851 in 5.3 s.

## Nothing matched

1. **`match_threshold`** 0.2 → 0.1. The direct dial.
2. **The other weight set.** `indoor` and `outdoor` are trained on ScanNet and
   MegaDepth respectively. On a scene far from either, both will be mediocre, but
   the gap between them is worth one run to measure.
3. **The detector's `keypoints_min`.** SuperGlue cannot match keypoints that were
   never found.
4. **`max_keypoints`** if the detector produced very few — this truncates, it
   never adds.

## `inlier_ratio` below 0.5

Unusual for a learned matcher and worth taking seriously rather than tuning away.

- **Check `planarity` first.** Near 1.0, the pair is planar or rotation-only and
  verification is rejecting correctly. Nothing to fix in the matcher.
- **Check the weight set against the scene.** Outdoor weights on a textureless
  interior produce confident matches that fail geometry — high `mean_match_score`
  with low `inlier_ratio` is that signature exactly.
- **Then raise `match_threshold`** toward 0.4. Trading count for precision is
  clean here because the Sinkhorn score is reasonably calibrated.
- **Do not lower `ransac_threshold`.** That converts a low inlier ratio into a low
  match count without improving anything.

## `graph_components` above 1

Same fix as every matcher — raise `window`, or `pairing: exhaustive` — with one
cost note specific to the learned matchers: each pair is a network forward pass,
not a descriptor comparison. Going from `window: 1` to `exhaustive` on 20 images
is 190 forward passes against 19. Raise `window` one step at a time.

## `keypoints_used` below the detector's count

`max_keypoints` truncated the detector's output, so the detector's
`keypoints_per_image` and `spatial_coverage` no longer describe what was matched.
Two honest fixes, and one dishonest one:

- Raise `max_keypoints`. Attention is quadratic in it: 2048 → 4096 is roughly 4x
  the matching time.
- Or lower the DETECTOR's `max_keypoints` to the same value, so its metrics
  describe the set that actually reached the matcher.
- The dishonest option is leaving them mismatched and reading the detector's
  coverage as if it applied. Truncation keeps the highest-scoring keypoints, which
  are not the best-spread ones.

## `sinkhorn_iterations`

Leave at 20. The published training value is 100 and buys almost nothing at
inference — it refines an assignment whose costs are already fixed by the GNN. If
matching cost matters, 10 is usually indistinguishable; check `matches_per_pair`
moved by less than a percent before keeping it.

## Cost

5.9 s for 11 pairs at 2020 keypoints on an A6000, most of it model load. Per-pair
cost is quadratic in `max_keypoints` and linear in pair count. On CPU this is
roughly 20x slower and not a working configuration for anything real.
