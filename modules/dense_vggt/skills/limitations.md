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

**A wrong scale does not fail.** The cloud comes out correctly shaped, correctly
coloured, and the wrong size, sitting in front of cameras at the wrong distance —
and every metric here is unchanged, because the same pixels survive. `depth_scale`
and the `scale_unverified` diagnostic are the only evidence.

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
