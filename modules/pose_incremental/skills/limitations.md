---
module: PoseEssentialToPnP
module_version: 1.0.0
curated_at: 2026-08-07
---

# When to stop tuning PoseEssentialToPnP and switch

## Uncalibrated scenes

*Symptom:* the module refuses to run at all.

It needs intrinsics and will not guess them. This is not tunable — an essential
matrix is only an essential matrix with respect to a known K.

*Switch to:* a pose estimator that estimates intrinsics jointly.

```
sfm_find_modules(produces="poses/v1", excluding="PoseEssentialToPnP")
```

VGGT and MapAnything are the candidates, and they do not merely tolerate an
uncalibrated scene — they do **better** without a supplied K, because they solve
for it jointly with everything else. Do not pass `calibration_path` to SceneLoader
on that path.

## Degenerate captures

*Symptom:* `no_viable_initial_pair`, or a seed that only just clears
`init_min_angle_deg` and a model with low `median_triangulation_angle` throughout.

*Why no parameter helps:* a planar scene or a pure-rotation capture has no
parallax to recover depth from. The essential matrix is degenerate, and lowering
`init_min_angle_deg` does not create baseline — it seeds on a pair that cannot
support structure, and that error propagates into every later registration.

**Check the matcher's `planarity` metric first.** Above ~0.9 a homography explains
the pairs as well as epipolar geometry does, which is a capture problem. No module
here fixes it. If the target genuinely is planar, this is a homography-estimation
problem, not an SfM one.

## Sparse sampling

*Symptom:* healthy per-pair matching, but `registered_fraction` well below 1.0 and
tracks that never reach a third view.

Measured in this repo: uniformly sampling 6 of DTU scan1's 49 images (every eighth
frame) leaves gaps SIFT cannot bridge even with exhaustive matching — 3 view-graph
components and zero tracks reaching a third view, so nothing can register. Six
*contiguous* frames connect completely.

*What helps:* `sampling: head` in SceneLoader, or more images. Not a parameter here.

## Drift on long sequences

*Symptom:* reprojection error grows with distance from the seed pair; the model
curves.

*Why no parameter helps:* this module is greedy. It registers one image at a time
against fixed structure and never moves a point once accepted, so small errors
compound. That is inherent to incremental SfM without refinement.

*What helps:* run `BundleAdjustmentGlobal` after it — that is exactly what it is
for. For very long sequences, interleaved local BA during registration is the
principled answer. The predecessor did this by taking a
`BundleAdjustmentOptimizerLocal` *instance* as a constructor argument, making one
module's behaviour a function of another module's object; this architecture
deliberately does not reproduce that coupling.

Recorded as a known gap: if drift proves to be the binding constraint, the right
shape is a pose estimator that calls BA as a sub-step, not a parameter here.

## When a global method is simply better

*Symptom:* the images are an unordered collection rather than a sequence, and
registration order is doing real work.

Incremental SfM is order-dependent by construction. On unordered collections a
global method that solves all poses at once is both faster and more robust.

*Switch to:* a mapper that goes straight from correspondences to a reconstruction,
skipping the separate pose stage:

```
sfm_find_modules(produces="sparse_model/v1", not_consuming="poses/v1")
```
