---
module: DenseMVS
module_version: 1.1.0
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

**It is a whole-frame fraction, so it dilutes with whatever is not surface.** The
denominator is every pixel, including backdrop, sky and clipped sweep — none of
which any densifier should certify. On a capture whose frames are mostly lit
backdrop the reading lands far below the band while the cloud over the subject is
sound; one corpus capture delivered a good cloud at roughly a fifth of the
reference run's reading, with two thirds of every frame blown-out backdrop. **Before
treating a low reading as a fault, ask what share of the frame is subject at all** —
the description's `empty_regions` is the check — and confirm against the readings
that do not dilute: `views_contributing` against `input_registered_images`, and
`fusion_ratio`. A low reading with every view contributing is a framing fact, not a
stereo failure.

**It is not comparable to `DenseVGGT`'s `mean_depth_confidence` either.** One is
what fraction of the image was verifiable; the other is a network's unbounded
self-report.
