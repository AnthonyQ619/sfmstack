---
module: FeatureDetectionSuperPoint
module_version: 1.1.0
produces: features/v1
curated_at: 2026-08-07
---

# Reading a FeatureDetectionSuperPoint artifact

## Layout

```
data/keypoints.npz
    xy            (N, 2) float32   pixel coordinates in the SCENE's resolution
    image_index   (N,)   int32     which image, sorted ascending
    scores        (N,)   float32   heatmap confidence
data/descriptors.npz
    desc          (N, 256) float32
```

No `scale` and no `orientation`: SuperPoint estimates neither. That absence is
load-bearing — LightGlue's `sift` and `doghardnet` weight sets require both as
inputs, so those weight sets cannot be used with these features, and
`FeatureMatchLightGlue` raises rather than silently proceeding.

## Coordinates are always in scene pixels

Even when `resize_long_edge` made inference run at a different resolution. The
rescaling happens here so no consumer needs to know, and so `resize_long_edge` can
be tuned for cost without touching anything downstream.

The consequence to remember: detections found at 640px and rescaled to 1600px
carry 640px localisation precision. The coordinates are correctly *placed*, not
more *precise*.

## Descriptors are 256-d, not 128

Wider than SIFT and ALIKED. Code that hardcodes 128 breaks here, which is the
intended outcome. `FeatureMatchLightGlue` uses the width as a cross-check on its
inferred weight set.

They are L2-normalised by the model. No `binary` flag, so matchers use L2 distance.

## `scores` is a heatmap confidence

On SuperPoint's own scale — typically 1e-3 to 1e-1 — and **not** comparable to
ALIKED's scores or SIFT's contrast responses. `mean_score` in the metrics is useful
for comparing two runs of this detector on the same scene, and meaningless across
detectors.

## What is NOT here

**Multi-scale detections.** SuperPoint is fully convolutional with no pyramid; it
sees exactly one scale.

**Rejected detections.** Everything below `detection_threshold` or suppressed by
NMS is gone, with only `saturation` recording that the cap bound.

**Which device it ran on.** In the narrative body, not as a metric. The output is
identical on CPU and GPU — only timing differs — so it is not something a consumer
should branch on.

## Metrics that mislead

`keypoints_per_image` is usually exactly `max_keypoints`, and comparing it to
SIFT's is comparing different things: 2048 SuperPoint keypoints are roughly as much
signal as 4096 SIFT ones.

`spatial_coverage` is the metric worth reading, and SuperPoint scores well on it
(0.932 on the reference run) largely because of the heatmap NMS. Do not treat that
high number as headroom — it is the normal operating point, not a margin.
