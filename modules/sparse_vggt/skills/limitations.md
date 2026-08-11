---
module: SparseVGGT
module_version: 1.0.0
curated_at: 2026-08-11
---

# What SparseVGGT cannot do

## One scale for the whole scene

Everything rests on a single scalar relating VGGT's depth unit to the supplied
poses' unit. That is exactly right when the depth is consistent with the geometry
up to scale, and wrong when the depth is locally good and globally drifting — a
regime learned monocular depth is known for.

`depth_scale_spread` is the check, and it is reported rather than assumed. Above
~0.25 the module warns; the cloud will look plausible and measure wrong.

**Escapes:**

```
find(consumes="poses/v1", produces="sparse_model/v1")
```

`SparseTriangulation` and `SparseTriangulationGTSAM` need no depth prior.

## It cannot fix poses

Points are placed with the supplied cameras. Wrong poses give wrong structure that
reprojects consistently into the wrong place, and additionally corrupt the scale
estimate — so a pose problem shows up here as a scale problem, which is a
misleading place to start debugging. Check the pose estimator's own metrics first.

## Accuracy is bounded by the depth prior

Measured on DTU with identical tracks: 0.967 px against `SparseTriangulation`'s
0.365 px. Ray intersection is more accurate where rays are available. This module
is for where they are not.

## Single-view points are unverified

A track seen once gets a point from one depth prediction, with nothing checking it.
`single_view_points` says how many. They are real structure and the reason to use
this module on short tracks; they are also the part of the cloud that no
measurement here supports.

## Nearest-pixel depth sampling

Depth is read at the nearest pixel of the 518-square, not interpolated. Bilinear
interpolation on a depth map blends across depth discontinuities and invents
surface between foreground and background — precisely at the edges keypoints like
to sit on. The cost is sub-pixel precision in the depth, which is small next to
the prior's own error.

## No track_id

Points are not traced back to their `tracks/v1` rows. `SparseTriangulation` writes
`track_id`; if you need that link, use it.

## Chunking is safe here, unlike in PoseVGGT

`max_images_per_pass` splits inference. Depth is per-view, so chunking changes what
the model attends to but not what frame the output lands in — expect slightly worse
depth in small chunks, not a broken model. `PoseVGGT` cannot say the same.
