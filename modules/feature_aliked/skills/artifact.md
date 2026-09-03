---
module: FeatureDetectionALIKED
module_version: 1.2.0
produces: features/v1
curated_at: 2026-08-08
---

# Reading a FeatureDetectionALIKED artifact

## Layout

```
data/keypoints.npz
    xy            (N, 2) float32   pixel coordinates in the SCENE's resolution
    image_index   (N,)   int32     which image, sorted ascending
    scores        (N,)   float32   detection confidence, ALIKED's own scale
data/descriptors.npz
    desc          (N, 128) float32
```

No `scale`, no `orientation`, no `binary` flag. As with SuperPoint, the absence of
scale and orientation means LightGlue's `sift` and `doghardnet` weight sets cannot
consume these features — those were trained with both as inputs, and
`FeatureMatchLightGlue` raises rather than proceeding without them.

## 128-d descriptors, same width as SIFT and DISK

Which is why `FeatureMatchLightGlue` cannot infer the weight set from width alone
and uses provenance as the primary signal, with width as a cross-check. Three
different detectors here produce 128-d float descriptors that need three different
LightGlue weight sets.

## `scores` is on ALIKED's scale

Typically 0.1-0.9, against SuperPoint's 1e-3 to 1e-1. `mean_score` is comparable
across runs of *this* detector on the same scene and meaningless across detectors.

This is the same scale difference that makes `detection_threshold` non-portable,
and reading `mean_score` is the quickest way to confirm which scale a run was on.

## Which variant produced it

Not an array — it is in `produced_by.params`, and therefore part of the artifact
id. So an `aliked-n16` run and an `aliked-n16rot` run are separate, comparable
artifacts rather than one overwriting the other, and `sfm_compare` will name
`variant` among the diverging parameters.

## Coordinates are in scene pixels

Always, even when `resize_long_edge` made inference run at a different resolution.
Detections found at a reduced resolution and rescaled up are correctly *placed* but
carry the localisation precision of the resolution they were found at — which
matters more for this detector than most, since localisation is its whole claim.
