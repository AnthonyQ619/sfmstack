---
module: FeatureMatchSuperGlue
module_version: 1.6.0
curated_at: 2026-08-10
---

# Reading a FeatureMatchSuperGlue artifact

## Layout

`pairwise_matches/v1`: `pairs` (image_pair) and `matches` (xy, pair_index,
feature_index, confidence). Identical in shape to every other matcher here, which
is what lets five matchers be swapped without touching anything downstream.

## `feature_index` is present

It points into the `features/v1` keypoint table this module consumed, so the
tracker merges observations by identity rather than by proximity. That is the
detector-based path and it is exact; `merge_eps_px` is ignored entirely.

Note the indices are into the FULL keypoint table, not into the truncated set this
module matched. A consumer never sees the truncation.

## `confidence` is a Sinkhorn score

The assignment probability from the optimal-transport layer. **It is not
comparable to LightGlue's confidence**, which comes from a matchability head with
different calibration. Comparing the two modules' `mean_match_score` is comparing
two different quantities that happen to share a range.

Everything else in the artifact IS comparable across all five matchers, because
verification, the view graph and planarity are the same code.

## Metrics that mislead

**`matches_per_pair` is bounded by `max_keypoints`.** A pair cannot produce more
matches than the smaller image has keypoints fed to the matcher. 1100 matches at
`max_keypoints: 2048` is a very high yield; the same number at 8192 is not.

**`mean_match_score` high with `inlier_ratio` low** is the signature of a weight
set mismatched to the scene: confident matches that fail geometry. It is the one
pair of metrics here worth reading together every time.

**`keypoints_used` below the detector's `keypoints_per_image`** means the
detector's own metrics describe a larger set than was matched. Its
`spatial_coverage` in particular no longer applies — truncation keeps the
highest-scoring keypoints, which are not the best-spread ones.

**`inlier_ratio` near 1.0 is normal here**, unlike for a classical matcher. It
means verification found almost nothing to reject, which is what a good learned
matcher on an easy scene should produce. It stops being informative in that
regime; `planarity` and `graph_components` still are.
