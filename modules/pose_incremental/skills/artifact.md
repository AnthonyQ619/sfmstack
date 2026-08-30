---
module: PoseEssentialToPnP
module_version: 1.1.0
produces: poses/v1
curated_at: 2026-08-07
---

# Reading a PoseEssentialToPnP artifact

## Layout

```
data/poses.npz
    cam_from_world   (N, 3, 4) float64   world-to-camera [R|t], per SCENE image
    valid            (N,)      bool      False where the image could not register
    image_index      (N,)      int32     index into scene/v1 images
```

`N` is the number of images in the **scene**, not the number registered. Rows for
unregistered images are present and carry identity, which is meaningless — that is
what `valid` is for.

## `valid` is not optional

`poses/v1` makes the flag mandatory rather than implying registration from array
length. The reason is specific: a pipeline that silently treats an unregistered
camera as identity produces a reconstruction that looks plausible and is wrong.
Forcing every consumer to confront the flag is the point.

Filter on it before anything else:

```python
poses = art.load("poses")
registered = poses["valid"]
P = poses["cam_from_world"][registered]
frames = poses["image_index"][registered]
```

## Convention

Cam-from-world, matching COLMAP and OpenCV. A world point `X` projects as
`x = K [R|t] X`. The camera centre in world coordinates is `-R.T @ t`.

The world frame is the seed pair's first camera: its pose is exactly `[I|0]`.

## Scale

Arbitrary. `recoverPose` returns a unit-length translation, so the seed pair's
baseline **is** the unit of every distance in and downstream of this artifact.

Two runs on the same scene that pick different seed pairs are related by a
similarity transform, not by identity — which is why comparing two pose artifacts
means comparing metrics, not comparing poses elementwise.

Nothing in an image-only pipeline recovers metric scale. It needs a known length
in the scene, metric depth, or GPS.

## What is NOT here

**The 3D points.** They are computed internally — registration is impossible
without them — and then discarded, because this artifact is `poses/v1`. Run
`SparseTriangulation` to get them as a `sparse_model/v1`.

That looks like waste and is deliberate: it keeps the triangulation *policy* in one
module rather than one per pose estimator. The re-triangulation costs about 1.3s
against 2.0s for the whole pose stage on the reference run. See
`docs/design/DECISIONS.md`.

**Intrinsics.** This module reads them and does not refine them, so it writes no
`intrinsics` file. A pose estimator that *does* estimate them (VGGT, MapAnything)
writes one, and downstream modules prefer it over the scene's calibration.

**Per-image quality.** The metrics are aggregates. `valid` says what failed
outright, and the `partial_registration` diagnostic names up to five by filename.

## Metrics that mislead

`mean_reprojection_error` can look excellent on a reconstruction that is
geometrically wrong. A point triangulated from near-parallel rays reprojects
perfectly into the two views that created it while sitting in the wrong place.
Always read `median_triangulation_angle` beside it.

`registered_fraction` of 1.0 is necessary, not sufficient — lowering
`min_pnp_inliers` raises it by admitting badly-posed images.

`track_utilization` near 1.0 (0.983 on the reference run) means the filters are
barely biting. Good on clean data; a sign the thresholds are too loose if
`mean_reprojection_error` is simultaneously poor.

`local_ba_gain_px` **falling toward zero over a run is success, not failure**, and
the artifact reports only the mean over all solves, so you cannot see that from
here. A large mean means either healthy early correction or sustained late drift,
and only `registered_images` and `mean_reprojection_error` distinguish them.

Worse: **a low `mean_reprojection_error` can be the signature of a model that
stopped early.** On DTU with `local_ba: false`, the 34-camera model reported 0.945px
and the 48-camera model 0.888px — but the smaller number came from the run that
failed to register 14 images. Compare error only between models with the same
`registered_images`; across different counts it is not a comparison at all. This
is the single easiest way to misread this artifact, and it is the mistake made once
already in this repository's own reporting.
