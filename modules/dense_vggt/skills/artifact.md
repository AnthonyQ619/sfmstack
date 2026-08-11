---
module: DenseVGGT
module_version: 1.0.0
curated_at: 2026-08-11
---

# Reading a DenseVGGT artifact

## Layout

`dense_model/v1`: `points` (xyz, rgb) and a `confidence` file. No `depth` maps —
see [limitations](limitations.md#no-depth-maps-in-the-artifact).

## The cloud is in the SUPPLIED poses' frame and scale

Not VGGT's. `depth_scale` is the scalar that got it there. Whether that scalar was
MEASURED or ASSUMED is the single most important thing about this artifact, and
`depth_scale_spread` being null is how you tell: null means no tracks were
supplied and the parameter was used.

## `confidence` is per point and unbounded

VGGT's own, carried through so a consumer can filter harder without re-running
inference. It is not a probability — means around 46 are normal — and it is not
comparable to any other module's confidence.

## Metrics that mislead

**`point_count` is mostly a function of `stride`.** Quadratic in it. Comparing two
runs' point counts without comparing their strides compares the parameter.

**`mean_depth_confidence` says nothing about accuracy across methods.** It is
self-reported and unbounded. Use it within this module, across settings.

**`depth_scale_spread` of null is a warning, not an absence.** It means the scale
was never checked.

**Nothing here measures agreement between views.** There is no fusion, so a
consistent-looking cloud may be four slightly different surfaces overlaid. The
metrics cannot see that and neither can a viewer at low zoom.
