---
module: FeatureDetectionALIKED
module_version: 1.1.0
curated_at: 2026-08-08
---

# When to stop tuning ALIKED and switch

## Descriptor discriminability

*Symptom:* healthy keypoint counts and coverage, but the matcher reports fewer
matches or a lower `inlier_ratio` than SuperPoint gets on the same scene.

*Why no parameter helps:* ALIKED's descriptors are 128-d against SuperPoint's
256-d, and the model is smaller. It trades descriptive power for localisation and
speed, deliberately. `variant: aliked-n32` recovers some of it; the rest is the
design.

*Switch to:* SuperPoint, if match count rather than reprojection error is what is
limiting you.

```
sfm_find_alternatives(produces="features/v1", excluding="FeatureDetectionALIKED")
```

## Textureless regions

Same limitation as every interest-point detector, and for the same reason: a
featureless surface has no structure to score, and lowering the threshold far
enough produces detections whose descriptors are not repeatable.

*Switch to:* a detector-free matcher.

```
sfm_find_alternatives(produces="pairwise_matches/v1", not_consuming="features/v1")
```

## When ALIKED finds nothing

The module raises rather than producing an empty artifact, and the message names
the most likely cause first:

1. **`detection_threshold` set to SuperPoint's scale** (0.0005 instead of 0.2).
   This one is inverted relative to the SuperPoint case: SuperPoint's value here is
   so low that it should detect *everything*, and if you are seeing nothing the
   cause is elsewhere. It is the reverse swap — this module's 0.2 pasted into
   SuperPoint — that produces silence there.
2. Images did not decode.
3. Genuinely blank images.

## Scale change

ALIKED's deformable sampling adapts the receptive field per keypoint, which helps
with moderate scale variation, but there is no explicit pyramid. Large scale
change — an approaching shot spanning 4x — is handled better by SIFT's pyramid or
ORB's, both of which sample scale explicitly.

*What to do:* SIFT if a GPU is not essential, or accept shorter tracks across the
scale extremes and rely on the matcher's `window` to link them through
intermediates.

## The weight-set coupling

Recorded because it is an integration limitation rather than a model one.

ALIKED features must be matched by LightGlue's `aliked` weights. The wrong set
does not error — it produces matches with plausible geometry and low confidence.
`FeatureMatchLightGlue` infers the set from this artifact's provenance and
cross-checks the 128-d width, but that inference only works because this module is
in its known-detector table.

A custom detector emitting 128-d descriptors would not be inferable, and would
need `weights` set by hand. That is a limitation of the coupling, and the reason
`mean_match_score` exists as a metric — a low value with a healthy inlier ratio is
the signature of the wrong weights.
