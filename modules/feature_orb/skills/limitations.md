---
module: FeatureDetectionORB
module_version: 1.0.0
curated_at: 2026-08-07
---

# When to stop tuning ORB and switch

ORB's ceiling is set by the BRIEF descriptor. It samples intensity comparisons in
a fixed pattern, rotated by the keypoint's orientation — which buys in-plane
rotation invariance and nothing else.

## Scale and viewpoint change

*Symptom:* fine per-pair matching on adjacent frames, and the matcher's
`graph_components` above 1 no matter how far `window` is raised.

*Why no parameter helps:* the pyramid gives ORB *some* scale invariance, but BRIEF
has no affine model at all. Past roughly 25-30 degrees of out-of-plane rotation the
comparisons stop agreeing — noticeably earlier than SIFT, which manages 40-50.

*Try first:* raise `n_levels` and lower `scale_factor` toward 1.1. This genuinely
helps for scale and costs detection time.

*Switch to:* SIFT for the same CPU-only, no-weights profile, or a learned detector
(SuperPoint, ALIKED) if a GPU is available.

```
sfm_find_modules(produces="features/v1", excluding="FeatureDetectionORB")
```

## Low texture

*Symptom:* `keypoints_min` low and `spatial_coverage` low even at
`fast_threshold: 5`.

*Why no parameter helps:* FAST needs a corner — a centre pixel differing from an
arc of its ring. A smooth region has none at any threshold, and lowering the
threshold far enough to fire produces detections on sensor noise, which match
confidently and wrongly.

*Switch to:* a detector-free matcher, which skips interest points entirely.

```
sfm_find_modules(produces="pairwise_matches/v1", not_consuming="features/v1")
```

## Repeated structure

*Symptom:* healthy counts, healthy coverage, poor `inlier_ratio` downstream, and a
raised `inconsistent_rate` from the tracker.

*Why it is worse here than with SIFT:* binary descriptors are lower-dimensional
and more quantised, so the distances between a true match and a repeat are closer
together. The ratio test has less to separate, and it was already the wrong tool
for repetition.

*Switch to:* a learned matcher, which reasons about the match set jointly rather
than per-keypoint.

## When ORB finds nothing

The module raises rather than producing an empty artifact. Causes in order:

1. `fast_threshold` too high for a dim capture. Lower it to 5-10.
2. `edge_threshold` larger than the images. It must be at least the 31-pixel patch
   size, and it excludes a border of that width — on a thumbnail-sized image that
   can be everything.
3. The images did not decode. Check the scene artifact resolves its paths.

## What ORB is genuinely good at

Recorded so the limitations above are not read as "always use SIFT". ORB is the
right choice for video with small inter-frame motion, for a first pass over a large
capture where you want to know whether the pipeline runs at all, and for parameter
sweeps where you will run the pipeline dozens of times. Its weaknesses are all
about *large* change between views, and video does not have large change between
views.
