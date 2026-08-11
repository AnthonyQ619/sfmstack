---
module: DenseVGGT
module_version: 1.0.0
curated_at: 2026-08-11
---

# What DenseVGGT cannot do

## The scale it cannot measure alone

It has no correspondences, so nothing in its own inputs relates VGGT's depth unit
to the poses' unit. With a `tracks/v1` input the scale is estimated and reported
with its spread; without one it is the `depth_scale` parameter.

**A wrong scale does not fail, and it is not a harmless rescale.** Every metric
here is unchanged — the same pixels survive, because the depth filter and the
confidence filter are both scale-invariant — so `depth_scale`, its spread, and the
`scale_unverified` diagnostic are the only evidence.

The reason it is not harmless is that the cameras do not move with the points.
Unprojection is

```
X_world(f) = C_f + R_fᵀ · ray · depth · s
```

so getting `s` wrong by a factor *k* replaces each view's cloud with `C_f + (X −
C_f)/k` — a scaling **about that view's own camera centre**. Every view shrinks
toward a different point, so the views stop agreeing. Two cameras `d` apart put
their copies of the same surface point `d · (1 − 1/k)` apart.

Measured on the 8-view DTU run, true scale 4.4460, run at the default 1.0:

| | correct scale | scale left at 1.0 |
|---|---:|---:|
| bounding-box diagonal | 7.2506 | 3.8996 |
| median distance to nearest camera | 4.4633 | 1.0553 |

A pure shrink would have put the bbox ratio at `1/k` = **0.225**. It is **0.538**.
The excess is the splay: eight shrunken shells, each hugging its own camera,
spread across the rig instead of one surface. With a median baseline of 1.70 the
predicted disagreement is 1.32 — 78% of the baseline.

**So the visual signature of a wrong scale is not a small object. It is a smeared
or multiplied one** — which looks like bad depth, and is not.

## It is not MVS

No photometric consistency check, no cross-view fusion, no visibility reasoning. A
surface seen from four views appears four times, offset by whatever the depth
predictions disagree about. `points_per_view` × `views_contributing` is
`point_count` by construction — there is no fusion step that could make it
otherwise.

**Escape:** a real MVS module.

```
find(produces="dense_model/v1", consumes="sparse_model/v1")
```

## No depth maps in the artifact

`dense_model/v1` can carry them and this module does not write them. They exist
and they are in VGGT's letterboxed 518-square frame, not the scene's — writing
them would invite a consumer to index them with scene pixel coordinates and get
silently wrong depths. The point cloud is already in the scene's world frame,
which is the part that composes.

## Accuracy is the depth prior's

Bounded by what VGGT predicts, which is a learned monocular prior refined across
views. It is smooth, complete, and locally plausible; it is not photometrically
verified anywhere.

## Only posed views contribute

A view with `valid=False` in the pose artifact is skipped entirely. That is
correct — there is nowhere to put its points — but it means coverage silently
follows the pose estimator's `registered_fraction`.
