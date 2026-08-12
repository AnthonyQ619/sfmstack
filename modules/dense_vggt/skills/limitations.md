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

The reason it is not harmless is that **the cameras do not move with the points**.
Unprojection places each pixel along a ray from its own camera:

```
X_world(f) = C_f + R_fᵀ · ray · depth · s
```

Getting `s` wrong by a factor *k* therefore replaces view *f*'s cloud with

```
X_wrong = C_f + (X_true − C_f) / k
```

— a scaling **about that view's own camera centre**, not about the world origin.
The centres differ from view to view, so this is not a similarity transform of the
reconstruction and the views stop agreeing with each other. Two cameras a distance
`d` apart place their copies of the same surface point

```
d · (1 − 1/k)
```

apart. At *k* = 2 that is half the baseline; at *k* = 5, four fifths of it.

**How to tell the two apart on any scene.** A pure shrink would scale the cloud's
bounding box by exactly `1/k`. A splay scales it by less, because the per-view
shells are spread across the camera rig as well as being individually smaller. So:

```
bbox_wrong / bbox_correct  ≈ 1/k      → a global rescale
bbox_wrong / bbox_correct  >  1/k     → the views disagree; the gap is the splay
```

The size of the gap depends on the capture — it grows with the camera baselines
relative to the object, so a wide-baseline set splays visibly and a
nearly-coincident one barely at all. The algebra above holds regardless.

**The consequence is the same everywhere: the visual signature of a wrong scale is
not a small object. It is a smeared or multiplied one** — which looks like bad
depth, and is not.

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
