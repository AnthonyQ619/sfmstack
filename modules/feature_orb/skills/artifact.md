---
module: FeatureDetectionORB
module_version: 1.0.0
produces: features/v1
curated_at: 2026-08-07
---

# Reading a FeatureDetectionORB artifact

## Layout

```
data/keypoints.npz
    xy            (N, 2) float32   pixel coordinates in the RESIZED image
    image_index   (N,)   int32     which image, sorted ascending
    scores        (N,)   float32   Harris response
    scale         (N,)   float32   detection scale (keypoint size)
    orientation   (N,)   float32   degrees
data/descriptors.npz
    desc          (N, 32) uint8    rotated BRIEF, 256 bits
    binary        scalar  bool     True
```

Concatenated across images with an index, not a per-image list — variable-length
arrays cannot go in an npz without pickling, and every consumer wants one
vectorized table.

## `binary` is load-bearing

`desc` is uint8 and must be compared with **Hamming** distance. A matcher that
treats it as a 32-dimensional float vector under L2 will produce matches — they
will just be wrong, and wrong in a way that survives the ratio test and reaches
geometric verification before failing.

Both matchers here read `binary` and select `NORM_HAMMING` (or an LSH index for
FLANN) automatically. If you write your own consumer, read the flag.

Note the descriptor width differs from SIFT's: 32 uint8 versus 128 float32. Code
that hardcodes 128 will break, which is the intended outcome.

## `scores` is a Harris response

Not comparable to SIFT's `response`. It is used internally to rank keypoints before
suppression and for the trim after SSC; treat it as an ordering within one image,
not as a quality measure across detectors.

## What is NOT here

**The detections SSC rejected.** With `detect_multiplier: 4` roughly three quarters
of what was detected is discarded. Only `suppression_ratio` records that it
happened.

**Any indication of which suppression ran.** The `suppression` parameter is in the
artifact's provenance (`produced_by.params`), which is where the answer lives, and
it is part of the artifact id — so an `ssc` run and a `none` run are separate,
comparable artifacts rather than one overwriting the other.
