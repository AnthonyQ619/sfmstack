---
module: FeatureDetectionSuperPoint
module_version: 1.1.0
curated_at: 2026-08-07
---

# When to stop tuning SuperPoint and switch

## Textureless regions

*Symptom:* `spatial_coverage` stays low with large empty areas, at any
`detection_threshold`.

*Why no parameter helps:* SuperPoint is still an interest-point detector. It is
much better than SIFT at deciding *which* weak structure is repeatable, but a
genuinely featureless surface has no structure to score. Lowering the threshold far
enough produces detections whose descriptors are not repeatable, which match
confidently and wrongly.

*Switch to:* a detector-free matcher, which estimates dense correspondence without
interest points at all.

```
sfm_find_modules(produces="pairwise_matches/v1", not_consuming="features/v1")
```

## Rotation

*Symptom:* pairs with large in-plane rotation fail while their neighbours match
fine.

*Why:* SuperPoint has no orientation estimation and no rotation augmentation in
training. SIFT, which estimates a dominant orientation per keypoint, is genuinely
better here — one of the few axes where the classical detector wins outright.

*Switch to:* SIFT, or `FeatureDetectionALIKED` with `variant: aliked-n16rot`, which
is trained with rotation augmentation specifically for this.

## Very large images

*Symptom:* memory pressure, or detections concentrated at one scale.

SuperPoint is fully convolutional and has no pyramid. It sees one scale, the one
you feed it. On a 4000px image its receptive field covers a much smaller fraction
of the scene than at 640px, which changes what it considers a keypoint.

*What to do:* `resize_long_edge` to 1024-1600, accepting the localisation cost, or
use SIFT/ALIKED where a pyramid or deformable sampling handles scale properly.

## When SuperPoint finds nothing

The module raises rather than producing an empty artifact.

1. `detection_threshold` set to ALIKED's scale (0.2) rather than SuperPoint's
   (0.0005). Three orders of magnitude apart, and the most likely cause when
   swapping detectors. Nothing clears 0.2 on SuperPoint's heatmap.
2. Images did not decode. Check the scene resolves its paths.
3. Genuinely blank or uniform images.

## The dependency argument

Recorded because it is the strategic limitation rather than a technical one.

This module needs torch, the lightglue package, CUDA wheels, and baked weights —
a 6.2 GB image against SIFT's 594 MB. That cost is shared across all three
LightGlue-family modules and is paid once on disk, but it is real: no GPU, no
network at build time, or an air-gapped host all make SIFT the only option.

The architecture exists so that this is a *per-module* cost rather than a
pipeline-wide one. SIFT and SuperPoint cannot share an environment and do not have
to.
