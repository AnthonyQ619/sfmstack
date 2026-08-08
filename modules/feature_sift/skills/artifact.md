# Reading the output — FeatureDetectionSIFT

Produces `features/v1`.

## Payload

```
data/keypoints.npz
  xy           [N, 2] float32   pixel coords in the scene's WORKING resolution
                                (scene size_current, not the original file)
  image_index  [N]    int32     which image each keypoint belongs to; ascending
  scores       [N]    float32   OpenCV response (contrast strength)
  scale        [N]    float32   detection scale, i.e. cv2.KeyPoint.size
  orientation  [N]    float32   degrees

data/descriptors.npz
  desc         [N, 128] float32  RootSIFT when root_sift=true (the default)
```

One concatenated table, not a per-image list. Slice it:

```python
xy  = feats.load("keypoints", "xy")
idx = feats.load("keypoints", "image_index")
image_3 = xy[idx == 3]
```

## Coordinates

`xy` is in the **working** resolution. To get original-file coordinates,
multiply by the per-image scale from the scene:

```python
scale = scene.load("images", "scale")     # [n_images, 2]
orig  = xy / scale[idx]
```

Use the per-image row, not a set-wide scalar. On ETH3D courtyard the source
images differ by a few pixels across the set, so scales differ in the fourth
decimal — small, but it is a systematic bias in triangulated geometry, not noise.

## Sanity checks

- `idx.max() + 1` should equal the scene's image count. A shortfall means a frame
  produced **zero** keypoints and was skipped entirely — every track through it is
  broken. Check the `starved_frames` diagnostic.
- `desc` rows align 1:1 with `xy` rows. Anything else is a producer bug.
- RootSIFT descriptors are non-negative and each row sums to roughly the same
  value. Negative entries mean `root_sift` was off or the transform misapplied.
- `xy` should span the frame. Compare `xy.min(0)` / `xy.max(0)` against
  `size_current` — a tight bounding box is the `poor_coverage` case.

## Metrics, and which to trust

| Metric | Read it as |
| --- | --- |
| `keypoints_per_image` | Mean. The least informative of the four on its own. |
| `keypoints_min` | **The one that matters.** Tracks chain through frames, so the worst frame bounds multi-view support for the whole sequence. |
| `saturation` | Fraction of images hitting the cap. Tells you *which* knob is binding: high → `max_keypoints`; low → `contrast_threshold`. |
| `spatial_coverage` | Fraction of an 8×8 grid holding a detection. Guards against the clustered-detections case that counts alone hide. |

A high mean with a low minimum is the characteristic shape of an uneven set and
is worse than a uniformly lower mean.

## Inspecting it

`sfm_artifact(<id>)` for the manifest and narrative. The npz files are plain
numpy with no custom loader:

```python
import numpy as np
d = np.load("artifacts/<id>/data/keypoints.npz")
d["xy"], d["image_index"]
```
