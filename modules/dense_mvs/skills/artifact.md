---
module: DenseMVS
module_version: 1.0.0
curated_at: 2026-08-11
---

# Reading a DenseMVS artifact

## Layout

`dense_model/v1`: `points` (xyz, rgb). A `depth` file only when
`write_depth_maps` is on **and** every undistorted view shares a resolution —
see [limitations](limitations.md#depth-maps-are-in-the-undistorted-frame) before
using it. No `confidence` file: there is nothing to put in it.

## The cloud is in the sparse model's frame and scale

Unchanged. Unlike `DenseVGGT` there is no scale to resolve — the depths come out
of the same geometry the poses are in, because they were searched for in it.

## `depth_map_completeness` is the metric that carries the meaning

It is the fraction of pixels that survived photometric and geometric filtering,
and it stands in for the confidence channel PatchMatch does not have. 0.65 on the
reference run.

**It is not comparable across `max_image_size`.** More pixels means finer detail
per pixel and a stricter consistency test, so completeness falls as resolution
rises even as the point count climbs. 0.717 at 600 px and 0.650 at 1200 px on the
same scene.

**It is not comparable to `DenseVGGT`'s `mean_depth_confidence` either.** One is
what fraction of the image was verifiable; the other is a network's unbounded
self-report.

## Metrics that mislead

**`point_count` is mostly `max_image_size`.** Quadratic in it. Two runs' point
counts are not comparable unless the resolutions match — 46 562 at 600 px and
128 327 at 1200 px are the same reconstruction.

**A larger cloud is not a better one, across methods.** On the reference scene
`DenseVGGT` produced 47% more points than `DenseMVS` and covered the triangulated
structure half as tightly, in a bounding box 70% larger. Point count measures
willingness to guess as much as it measures coverage.

**`views_contributing` equal to `input_registered_images` is the healthy case,**
and a gap is a different failure from a low `registered_images` — those views were
posed and then photometrically rejected.

**`fusion_ratio` is about overlap, not quality.** ~32 on the reference run means
about 32 depth-map pixels fused into each point. Near 1 means fusion merged
nothing.

**Nothing here measures accuracy against ground truth.** Every number is internal
consistency. A reconstruction can be complete, well-fused, and in the wrong place
if the poses were.
