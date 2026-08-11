---
module: FeatureMatchRoMa
module_version: 1.0.0
curated_at: 2026-08-10
---

# Reading a FeatureMatchRoMa artifact

## Layout

`pairwise_matches/v1`: `pairs` (image_pair) and `matches` (xy, pair_index,
confidence). Same shape as every other matcher **except** that `feature_index` is
absent.

## No `feature_index` — check for it, do not assume it

Its absence is the signal a consumer needs. `FeatureTrackUnionFind` branches on
it: present means exact merging by keypoint identity, absent means proximity
merging governed by `merge_eps_px`. A consumer that assumes it is present will
raise; one that assumes it is absent will do more work than it needs to on
detector-based input.

## Coordinates are in the scene's working resolution

RoMa matches at its own internal resolution (560 coarse, 864 upsampled) and
returns a normalised warp. This module maps that back using the SCENE's
`size_current`, so the coordinates here are in the same frame as SIFT's, LoFTR's
and LightGlue's — which is what lets every downstream pixel threshold stay
resolution-agnostic.

## `confidence` is a certainty, not a score

RoMa regresses a per-pixel certainty as part of its output. It is closer to a
calibrated uncertainty than LightGlue's matchability score, which is why
`min_certainty` is a usable dial rather than a guess. It is still self-reported
and not comparable across methods.

## Metrics that mislead

**`matches_per_pair` is bounded by `max_matches`.** 4951 out of 5000 sampled means
the field was almost entirely usable; the same number out of 50000 would mean the
opposite. Always read the parameter beside it.

**`inlier_ratio` near 0.99 is normal here** on an easy scene and stops being
informative in that regime. On a hard scene it is one of the two metrics that
still discriminate, along with `planarity`.

**`mean_certainty` near 1.0 is normal** and is informative mainly at its low end.

**`certainty_floor_effect` is null when `min_certainty` is 0**, which is the
default — a null means the filter did not run, not that nothing was low-certainty.

## What is NOT here

**Keypoints.** No `features/v1` is produced and none is consumed. Anything wanting
a keypoint table for another purpose must run a detector separately.

**The dense warp itself.** The full per-pixel field is computed and discarded
after sampling; only the sampled correspondences are written. A dense
reconstruction wants `dense_model/v1` from an MVS module, not this.
