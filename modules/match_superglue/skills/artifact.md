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
