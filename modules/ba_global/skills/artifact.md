---
module: BundleAdjustmentGlobal
module_version: 1.1.0
produces: sparse_model/v1
curated_at: 2026-08-31
---

# Reading a BundleAdjustmentGlobal artifact

## Layout

```
data/points.npz
    xyz          (P, 3) float64   refined world coordinates
    rgb          (P, 3) uint8     carried through from the input
    error        (P,)   float64   per-point mean reprojection error, refined
    track_id     (P,)   int32     the tracks/v1 track this point came from
data/observations.npz
    obs          (O, 4) float64   [frame_idx, point_index, x, y]
data/poses.npz
    cam_from_world (N, 3, 4) float64   refined
    valid          (N,)      bool
    image_index    (N,)      int32
data/intrinsics.npz            <- only when refine_focal_length or
    K              (N, 3, 3)        refine_principal_point was on
data/colmap/                   <- sidecar
    cameras.bin  images.bin  points3D.bin
```

Same type as the input, so BA is idempotent in shape: it can be chained, and a
second run on its own output is a legitimate no-op that should report
`error_reduction` near zero.

## `point_index` is renumbered

Points that fell under `min_track_length` are dropped, so the output is renumbered
densely from 0. **`point_index` in the output observations does not correspond to
`point_index` in the input.**

`track_id` is what survives the round trip. Use it to relate a point back to the
tracks artifact, and through that to the matches and keypoints.

## The `colmap` sidecar

`data/colmap/` holds `cameras.bin`, `images.bin`, `points3D.bin` — a real COLMAP
model, openable directly:

```python
import pycolmap
rec = pycolmap.Reconstruction(str(art.sidecar("colmap")))
```

The npz remains **authoritative**. The sidecar is a convenience for pycolmap
consumers, and a consumer without pycolmap loses nothing but the convenience. This
is what replaces the predecessor's live `Scene.recon` pointer — previously the only
unserializable handoff in the pipeline, and the reason the whole thing had to run
in one process.

One COLMAP camera is written per registered image, even when the whole set shares
intrinsics. Wasteful, and the only shape that also handles a mixed-resolution
capture or a multi-camera rig.

## Cameras are PINHOLE with no distortion

Because `sparse_model/v1` observations are undistorted pixels. If you export this
model and feed it to a COLMAP tool that expects raw images, the images and the
model will disagree — the model matches the *undistorted, resized* images the scene
artifact carries.

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

**Measured on the model this module ships, not the one it was handed.** A solve
moves structure, so the input's conditioning is stale as soon as it finishes. This
matters more here than anywhere else in the type: a refined model is normally the
LAST `sparse_model/v1` in a pipeline, so it is what a dense stage reads, and if the
refiners omitted these the questions would have no answer at the point where
something is about to be built on them.

## What is NOT here

**Removed outliers.** This module optimises and writes back; it does not delete
points except by `min_track_length`. Filtering belongs to `SparseTriangulation`.

**The Ceres residual history.** Only the summary reaches the metrics. If a solve
needs debugging, `converged` and `iterations` are the signals; the full report goes
to the container's stdout and is visible in the job's `log_tail`.

**Covariance.** pycolmap can estimate it (`BACovarianceOptions`) and this module
does not. Recorded as a gap: per-pose uncertainty would be genuinely useful for
deciding which frames to trust, and would be an additive `poses/uncertainty` array
if added.

## Metrics that mislead

`error_reduction` near zero is good news when the error is low and bad news when it
is high. It can also be **negative** without anything being wrong: with the robust
loss on, the solver is not minimising the mean.

`converged: 1` says the solver reached a minimum, not that the minimum is correct.
A model folded on itself converges perfectly well.

`reprojection_error_after` is measured against the poses BA itself produced, so it
cannot detect a globally wrong-but-self-consistent reconstruction. It is a
consistency measure, not an accuracy measure — there is no ground truth anywhere in
this pipeline.
