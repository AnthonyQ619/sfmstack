---
module: SparseTriangulation
module_version: 1.0.0
produces: sparse_model/v1
curated_at: 2026-08-07
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
