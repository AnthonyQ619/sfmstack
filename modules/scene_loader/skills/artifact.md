# Reading the output — SceneLoader

Produces `scene/v1`.

## Payload

```
data/images.npz
  paths          [N] str      relative to the artifact root when resized,
                              absolute into the dataset when resize: none
  names          [N] str      original filenames, for reporting and COLMAP export
  size_original  [N, 2] int32 (width, height) on disk
  size_current   [N, 2] int32 (width, height) after resize
  scale          [N, 2] f64   size_current / size_original, per image
  content_hash   scalar str   over the resolved file list and resize policy

data/calibration.npz          present only when calibration_path was given
  intrinsics     [C, 3, 3] f64  already scaled to size_current
  distortions    [C, 5]    f64  OpenCV [k1, k2, p1, p2, k3]
  camera_index   [N]       i32  optional; absent means all images share camera 0
  baseline       [3, 4]    f64  optional; stereo rig only

data/images/                  the working images, when resize != none
```

## Per-image geometry

`size_original`, `size_current` and `scale` are **arrays, one row per image**, not
set-wide scalars. Index them per image:

```python
scale = scene.load("images", "scale")
original_xy = working_xy / scale[image_index]        # correct
original_xy = working_xy / scale[0]                  # wrong on mixed-resolution sets
```

Real data mixes resolutions — ETH3D `courtyard` has three distinct sizes across
its images. The differences are a few pixels, so the resulting scale error is in
the fourth decimal: too small to notice by eye and systematic rather than random,
which makes it exactly the kind of bias that survives into triangulated geometry.

## Resolving image paths

Always go through `Artifact.resolve`, never treat `paths` as filesystem paths
directly:

```python
for rel in scene.load("images", "paths"):
    img = cv2.imread(str(scene.resolve(str(rel))))
```

Relative paths resolve against the artifact root; absolute ones pass through.
This is what lets the same artifact work whether the store is mounted at `/store`
in a container or lives under a project directory on the host.

## Sanity checks

- `size_current[:, 0] * size_current[:, 1]` should match the `megapixels` metric.
- `scale` should be ≤ 1 for every image under `auto`; a value above 1 means the
  policy upscaled, which `auto` never does.
- With `resize != none`, every path must resolve to a file inside the artifact.
  A path pointing outside means the artifact is not self-contained and downstream
  containers will need the dataset mounted.
- `intrinsics` are already scaled to `size_current`. Do **not** apply `scale` to
  them again — that is the double-scaling bug the predecessor had, where the
  calibration object was mutated in place and scaled once per call.

## Metrics

| Metric | Read it as |
| --- | --- |
| `n_images` | Set size after `max_images` and sampling. |
| `mixed_resolution` | 1 if sources differ. Informational; means per-image scale is load-bearing. |
| `downscale_factor` | Median linear scale. Below ~0.4, expect noticeably fewer keypoints downstream. |
| `megapixels` | Working megapixels per image. The single best predictor of downstream runtime. |

None of these are quality metrics. This module sets the budget the rest of the
pipeline works within; judge it by what happens downstream.

## Inspecting it

```python
import numpy as np
d = np.load("artifacts/<id>/data/images.npz")
d["names"], d["size_current"], d["scale"]
```

The working images are ordinary PNGs under `data/images/`, named by index.
