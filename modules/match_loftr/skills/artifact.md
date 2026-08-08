---
module: FeatureMatchLoFTR
module_version: 1.0.0
produces: pairwise_matches/v1
curated_at: 2026-08-08
---

# Reading a FeatureMatchLoFTR artifact

## Layout

```
data/pairs.npz
    image_pair       (M, 2) int32     [image_i, image_j]
data/matches.npz
    xy               (N, 4) float32   [x1, y1, x2, y2] in SCENE pixels
    pair_index       (N,)   int32     row of image_pair
    confidence       (N,)   float32   LoFTR match confidence
```

Same type as every other matcher, so everything downstream is unchanged — with one
structural difference.

## No `feature_index`

**This is the defining property of the artifact**, not an omission.

`pairwise_matches/v1` marks `feature_index` optional precisely for this case: a
detector-free matcher has no keypoint table to index into, because there was no
detector. Its absence is what a consumer branches on.

`FeatureTrackUnionFind` reads it: present means merge by identity (exact, no
tolerance, no parameter); absent means merge by proximity, controlled by
`merge_eps_px`. The default of 1.5px is far too small for this input — see
[tuning.md](tuning.md#the-first-thing-to-set-is-not-in-this-module) for the
measured curve.

The module emits a `detector_free_output` info diagnostic on every run saying so,
because it is the one thing that has to be configured downstream and it is silent
otherwise.

## Coordinates are in scene pixels

Even when `resize_long_edge` ran inference at a lower resolution. Rescaling happens
here.

Images are padded (bottom and right, replicate) to a multiple of 8 before
inference, because LoFTR's coarse grid requires it. Padding rather than resizing,
so coordinates need no correction for it — a pad on the bottom-right does not move
anything. Correspondences can in principle land in the padded strip; in practice
the replicated border produces no confident matches.

## `confidence` is LoFTR's own

Not comparable to the ratio-test confidence from the classical matchers, nor to
LightGlue's. All three are in [0, 1] and mean different things. Do not carry a
threshold across matchers.

## What is NOT here

**Any keypoints.** There is no `features/v1` in this path at all. The correspondence
coordinates are all that exists — there is nothing to describe, index, or reuse.

**Coarse/fine stage information.** LoFTR matches coarsely then refines; nothing
records which stage a correspondence came from or how far refinement moved it.

**Which correspondences the confidence filter dropped.** Only the survivors are
recorded.

## Metrics that mislead

`matches_per_pair` has a much higher healthy floor here (200) than for sparse
matchers (100), because semi-dense output is denser by construction. A few hundred
is thin for LoFTR and healthy for SIFT.

`inlier_ratio` runs lower than a sparse matcher's typical value and that is normal —
semi-dense output includes ambiguous regions by design, and geometric verification
is what removes them.

`long_track_fraction` measured downstream will look terrible until the tracker's
`merge_eps_px` is set correctly, and that is a *tracker* configuration problem, not
a matching one. Check it before concluding this module matched badly.
