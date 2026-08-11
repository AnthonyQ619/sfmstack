---
module: PoseVGGT
module_version: 1.0.0
curated_at: 2026-08-10
---

# What PoseVGGT cannot do

## It cannot tell you whether it is right

No correspondences means no reprojection error, so `mean_reprojection_error` and
`median_reprojection_error` are null. Every other pose estimator here reports one.

A number could be manufactured from VGGT's own point maps, and it would measure how
self-consistent the network is rather than how accurate the poses are — the two
diverge exactly when the model is confidently wrong, which is when you need the
metric. It is null instead.

**How to check it anyway:** triangulate against these poses and read the
triangulator's error.

```
find(consumes="poses/v1", produces="sparse_model/v1")
```

`SparseTriangulation` at defaults is a few seconds and gives a real number.

## Accuracy is initialisation-grade

Measured on 12 DTU frames with identical SIFT tracks: 1.05 px against the
classical estimator's 0.365 px. It gets the geometry approximately right and does
not compete on precision. Follow with `BundleAdjustmentGlobal` when it matters.

## Chunking does not stitch

`max_images_per_pass` above 0 splits the set into independent forward passes. Each
pass has its own world frame AND its own arbitrary scale, and this module does not
align them. The poses across chunks are not comparable, and the module says so with
an `error`-severity diagnostic rather than returning a plausible-looking model.

There is no parameter that fixes this. Sample fewer images instead.

## What it cannot tell you

**Whether the capture had translation.** `baseline_span` is a proxy and a weak one.
A pure-rotation capture yields poses that look fine and triangulate to nothing.

**Which images are wrong.** Every image is posed with equal confidence. There is no
per-image inlier count and no `valid=False` case — anything below
`registered_fraction` 1.0 means images were dropped before the forward pass.

## Scale is arbitrary AND different from the classical estimator's

`PoseEssentialToPnP` fixes the seed pair's baseline to 1.0. VGGT's scale comes from
the network. Neither is metric, and the two are not comparable, so a threshold in
scene units — notably `SparseTriangulationGTSAM`'s `max_landmark_distance` — has to
be re-derived when the pose source changes. `median_camera_separation` is written
for exactly that.

## It needs at least two images

It reasons across the set; one image has no relative pose to estimate. Refused
rather than run.
