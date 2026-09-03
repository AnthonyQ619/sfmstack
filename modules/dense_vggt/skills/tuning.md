---
module: DenseVGGT
module_version: 1.0.0
curated_at: 2026-08-11
---

# Tuning DenseVGGT

1. Was the scale measured or assumed? `scale_unverified` fires when assumed.
2. `mean_depth_confidence` — then set `min_confidence` from it, never blind.
3. `stride` for size.

## Reference run

A controlled-rig capture, 8 contiguous images, `max_edge: 1024`, poses from
`PoseEssentialToPnP`, `stride: 2`, `min_confidence: 1.0`, GPU, in a container:

| metric | without tracks | with tracks |
|---|---:|---:|
| `point_count` | 401 968 | 401 968 |
| `views_contributing` | 8 | 8 |
| `depth_scale` | 1.0000 (assumed) | **4.4460** (measured) |
| `depth_scale_spread` | null | 0.0039 |
| `mean_depth_confidence` | 46.63 | 46.63 |
| runtime | 22 s | 2 s (warm) |

The point count is identical because the scale changes where points land, not
which pixels survive. The 0.0039 spread says VGGT's depth and these poses agree
very well up to that one scalar.

Note `depth_scale` here (4.4460, 8 images) against `SparseVGGT`'s 2.1164 on the
same scene with 12 images. Both are right: the classical estimator fixes its seed
pair's baseline to 1.0, a different seed pair gives a different unit, and the
scale is a property of the depth/pose PAIR rather than of either one.

## `min_confidence` — read the metric before setting it

**VGGT's confidence is unbounded above.** The mean on the reference run is 46.6,
not 0.46. A value that looks like a sensible probability threshold is either a
no-op or a wall, and which one is not predictable.

The procedure: run once at `min_confidence: 0.0`, read `mean_depth_confidence`,
then set the threshold as a fraction of that. Raising it is the right way to clean
a noisy cloud — it filters on the model's own uncertainty, where `stride` merely
samples less of the same noise.

## `stride`

Quadratic in both axes: stride 2 is a quarter the points of stride 1, which would
be ~268k per view before filtering. That is more than most consumers want and is
dominated by redundancy between overlapping views rather than by detail — nothing
here fuses them. 4 for a quick look, 1 only when the cloud is the deliverable.

## Nothing survives

`min_confidence` is the cause in almost every case, for the reason above. Set it
to 0 and re-read `mean_depth_confidence`.

If it is genuinely 0, check the pose artifact has valid poses at all — this module
only unprojects views that carry one.

## The cloud looks right and measures wrong

The signature of an assumed scale. Check `scale_unverified`: if it fired, the
cloud is at whatever distance `depth_scale` put it, which with the default 1.0 and
non-VGGT poses is arbitrary.

The fix is to pass tracks, not to tune `depth_scale` by eye. The estimate is exact
and takes no extra inference — the depth maps are already computed.

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
