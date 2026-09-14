---
module: PoseEssentialToPnP
module_version: 1.4.0
produces: poses/v1
curated_at: 2026-09-13
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
