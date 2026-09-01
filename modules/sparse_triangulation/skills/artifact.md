---
module: SparseTriangulation
module_version: 1.1.0
produces: sparse_model/v1
curated_at: 2026-08-31
---

# Reading a SparseTriangulation artifact

## Layout

```
data/points.npz
    xyz         (P, 3) float64   world coordinates
    rgb         (P, 3) uint8     mean colour over the point's observations
    error       (P,)   float64   mean reprojection error, pixels
    track_id    (P,)   int32     the tracks/v1 track this point came from
data/observations.npz
    obs         (O, 4) float64   [frame_idx, point_index, x, y]
data/poses.npz
    cam_from_world (N, 3, 4) float64
    valid          (N,)      bool
    image_index    (N,)      int32
```

`P` points, `O` observations, `N` scene images. The poses are passed through
unchanged from the input `poses/v1` — this module does not move cameras.

## Coordinates are UNDISTORTED pixels

`observations/obs` columns `x, y` are in undistorted, working-resolution pixels.
Not raw image pixels.

This matters and is easy to get wrong. Distortion is removed once, at the top of
every classical geometry module, and never re-applied. A consumer that models
distortion again applies it twice. The COLMAP export in `BundleAdjustmentGlobal`
therefore uses PINHOLE cameras with no distortion terms — not as an
approximation, but because it is correct.

To get back to raw image pixels you would need to re-distort with the scene's
`distortions` array. To get to original-resolution pixels, multiply by the scene's
per-image `scale`.

## `track_id` survives

Each point remembers the track it came from, so a point can be related back to the
observations, the matches, and ultimately the keypoints that produced it. The BA
module preserves this through its own round trip.

Useful when a point looks wrong and you want to know which pair of images is
responsible.

## `error` is a mean, the filter was a max

`points/error` records the *mean* reprojection error across a point's
observations, because that is the useful summary. The acceptance test used the
*maximum*. So every point in this artifact had all of its observations under
`max_reprojection_error`, and the recorded mean is comfortably below it.

Do not use `error` to re-filter at the same threshold and conclude nothing is
rejected.

## Scale and frame

Inherited from the poses. If those came from `PoseEssentialToPnP`, the world frame
is its seed pair's first camera and scale is arbitrary — the seed baseline is the
unit. See that module's artifact notes.

## The four readings that see what the means hide

Every producer of `sparse_model/v1` publishes these, so they are comparable across
modules in a way a module's own metrics are not. Each exists because a scalar the
type already published was concealing something:

- **`min_frame_points`** — the emptiest registered camera. `registered_images`
  counts a camera holding almost no structure exactly like a well-covered one, and
  a whole-model `point_count` cannot be moved by one starved view. This is the
  reading that predicts a view failing downstream while every headline looks fine.
- **`two_view_fraction`** — the share of points seen in exactly two views. Those
  are exactly determined, four residuals against three unknowns, so their residual
  is near zero *by construction* rather than because they are good. On a
  two-view-dominated cloud they drag the mean down and the model reads better than
  it is.
- **`p95_reprojection_error`** — separates a uniformly mediocre model from a good
  model carrying a few bad points. The two want opposite responses, and the mean
  cannot tell them apart.
- **`p05_triangulation_angle`** — the weak end of the parallax distribution. A
  point on near-parallel rays sits at an ill-determined depth while reprojecting
  beautifully into the views that placed it, so it is invisible to every
  reprojection metric, and a median cannot see a tail. Where this reading is low,
  the cloud's SHAPE is uncertain in a way its error does not report.

`mean_reprojection_error` here is the **per-point** mean. It is worth knowing why
that is stated: producers of this type once published three different populations
under the one name — points, observations, and a frame that was not published at
all — and the spread was wide enough to invert a head-to-head comparison. An
observation mean weights long tracks, and long tracks are the higher-error points.

**Take them before choosing what comes next.** They describe the artifact rather
than the process that made it, so they are the honest basis for comparing this
module's output against another producer's — which the module-specific metrics,
measuring different things under similar names, are not.

## What is NOT here

**Intrinsics.** This module reads them and does not change them, so it writes no
`intrinsics` file. If the input poses carried one, it was used and is still
available there. `BundleAdjustmentGlobal` with `refine_focal_length` writes one.

**A COLMAP sidecar.** Produced by `BundleAdjustmentGlobal`, not here — writing one
would make pycolmap a dependency of a module that otherwise needs only OpenCV.

**Anything dense.** This is a sparse cloud of tracked features, typically a few
thousand points. It is not a surface and should not be rendered as one.

## Metrics that mislead

`yield` near 1.0 (0.99 on the reference run) means the filters are barely biting.
Good on clean input; on hard input a high yield means the thresholds are too loose.

`point_count` alone says nothing. 6941 points at 0.376px is a good model; the same
count at 3px with a 1° median angle is a bad one. Read it beside
`median_triangulation_angle`.

`mean_reprojection_error` is measured against the poses that were given, so it
cannot detect a globally wrong-but-self-consistent model. A reconstruction can be
internally consistent and still be the wrong shape.
