---
module: SparseTriangulationGTSAM
module_version: 1.1.0
curated_at: 2026-08-10
---

# What SparseTriangulationGTSAM cannot do

## It cannot fix poses

It takes `poses/v1` as given. Every point is triangulated against those cameras,
so a wrong pose produces wrong structure that reprojects consistently into the
wrong place. `rejected_cheirality` climbing is the usual first sign, and no
threshold here helps.

**Escape:** a second, independent pose estimate.

```
find(produces="poses/v1")
```

Or skip pose estimation entirely and let the reconstruction estimate it:

```
find(produces="sparse_model/v1", not_consuming="poses/v1")
```

`SparseGlobalCOLMAP` answers that one.

## Two-view tracks

On a track seen in exactly two views, LOST, multi-view DLT and OpenCV's two-view
DLT are the same computation. This module then costs more for an identical answer,
and says so with a `mostly_two_view` diagnostic below `mean_track_length` 2.2.

The fix is upstream, not here: widen the matcher's `window`, or use
`pairing: exhaustive`, so tracks reach more views.

## Uncalibrated scenes

Needs intrinsics; refuses without them. GTSAM's camera model is calibrated by
construction.

**Escape:** `find(produces="sparse_model/v1", not_consuming="poses/v1")` — the
feed-forward reconstructors estimate intrinsics themselves.

## Scale is arbitrary and unrecoverable

Inherited from the poses, not introduced here. It matters most for
`max_landmark_distance`, whose threshold is in that arbitrary unit. Nothing in an
image-only pipeline fixes this; it needs a known length in the scene or metric
depth.

## It does not refine poses along with points

This is triangulation, not bundle adjustment: points move, cameras do not. A
model where both should move needs

```
find(consumes="sparse_model/v1", produces="sparse_model/v1")
```

which is `BundleAdjustmentGlobal` and `BundleAdjustmentLocal`.

## Colour is best-effort

Colours come from sampling the images at each observation, which needs Pillow. If
Pillow is missing the module still runs and every point is mid-grey. The
containerised image always has it; an in-process run in a bare environment may not.
