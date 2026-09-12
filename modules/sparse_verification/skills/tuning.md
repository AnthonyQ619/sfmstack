---
module: SparseVerification
module_version: 1.0.0
curated_at: 2026-09-12
---

# Tuning SparseVerification

Two parameters, and neither is a fine dial. The decision this module informs is
made on whether the reading is far above the threshold or comfortably under it.

## What the readings have looked like

Correct models, across detector-based and detector-free pipelines, calibrated and
distorted captures, and models whose intrinsics were refined, read a fraction of
a pixel. Models that drifted into a wrong but self-consistent configuration read
many times the pipeline's own inlier threshold. A model off by a fraction of a
degree read under it. Nothing so far has sat near the threshold, which is why the
threshold is not worth tuning finely.

The reading scales with working resolution, like every pixel quantity in the
stack. Compare readings only between models at the same working resolution.

## `inlier_threshold_px`

The held-out residual above which the model is called contradicted. It defaults
to the pose estimator's own inlier threshold, so "agrees with the evidence" means
what the pipeline already means when it accepts a correspondence.

- **Scale it with the working resolution** the way that threshold scales.
- **Do not lower it to catch small errors.** Its job is to catch a model that has
  drifted. A slightly imprecise model reads under it by design, and a threshold
  low enough to flag one would start flagging correct models on captures where
  held-out outliers are common.

## `min_held_out_per_pair`

How many held-out correspondences a pair needs before its median counts. Below
it, a pair contributes nothing and its `residual_px` is NaN.

Lower it only when `nothing_held_out` fires on a capture whose pairs are
genuinely thin, and read the per-pair array before trusting what comes back: a
median over a handful of correspondences is one or two matches deciding a pair.
The better answer to `nothing_held_out` is usually other evidence, not a lower
floor.

## Supplying other evidence

`matches` accepts any `pairwise_matches/v1` of the same scene. The service wires
the model's own ancestor. Running the module yourself with a different matcher's
output gives a test set the model never saw in any form. It does not widen what
the check can see: an error every pair's correspondences allow stays invisible
whichever matcher produced them.

## What here rests on nothing

The threshold's default is inherited from the pose estimator, not fitted here.
The per-pair floor is a judgement about when a median stops being one or two
matches, not a measured optimum. The statement that nothing has sat near the
threshold describes a small number of captures and a handful of deliberately
repeated solves; the next capture sitting near it is expected, not anomalous.
