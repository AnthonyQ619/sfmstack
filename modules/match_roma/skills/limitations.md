---
module: FeatureMatchRoMa
module_version: 1.0.0
curated_at: 2026-08-10
---

# What FeatureMatchRoMa cannot do

## No `feature_index`

The defining limitation of every detector-free matcher, and the one that changes
what you must do downstream.

There is no global keypoint table to index into. Each pair is matched
independently, so one physical point gets an independently estimated sub-pixel
position in every pair it appears in — (312.4, 88.1) here, (313.9, 87.3) there.
The tracker cannot merge by identity and must merge by proximity, which makes
`FeatureTrackUnionFind.merge_eps_px` the parameter that decides whether tracks
chain at all.

Set it too tight and tracks never reach a third view; the tracker's
`inconsistent_rate` stays excellent while registration fails, because splitting
one point into several tracks produces no contradiction. `merge_headroom` is the
only metric that sees that direction.

Measured here: at 1024 px, `merge_eps_px: 4.0` gives `inconsistent_rate` 0.20 and
`merge_headroom` −0.21 — already past the useful tolerance. RoMa's field is
precise enough that 2–3 px is the right neighbourhood, unlike LoFTR where 1.5 px
was too tight.

## The compiled kernel is not installed

`use_custom_corr` needs a CUDA extension the authors ship separately and pip does
not install. With it absent the model constructs and raises on the first forward
pass. Off by default here. The base image could build it and does not.

## Cost

Roughly 1.5 s per pair at 1024 px on an A6000 with the pure-torch correlation, and
the cost is per PAIR, so the view graph dominates everything. `pairing: exhaustive`
on more than ~10 images is rarely the right call.

**Escape:** the cheaper detector-free matcher.

```
find(produces="pairwise_matches/v1", not_consuming="features/v1")
```

`FeatureMatchLoFTR` is the same family at a fraction of the cost.

## It has no keypoints to reuse

A sparse matcher's `features/v1` can feed several matchers; RoMa consumes none and
produces none. Comparing it against a sparse matcher therefore changes two things
at once — the correspondence method AND whether a detector was involved — so the
comparison is between PIPELINES, not between matchers.

## Two weight sets, no more

`outdoor` (MegaDepth) and `indoor` (ScanNet). No fine-tuning path here. A scene
far from both gets whichever is less wrong, and the honest response is to measure
both rather than reason about which should win.

## Scale of the certainty

`mean_certainty` is RoMa's own estimate and is not comparable to LoFTR's
confidence or LightGlue's match score. It reads near 0.997 on easy data, so it is
informative mainly at its low end.
