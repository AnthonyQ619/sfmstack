---
module: PoseEssentialToPnP
module_version: 1.2.0
curated_at: 2026-08-07
---

# When to stop tuning PoseEssentialToPnP and switch

## Uncalibrated scenes

*Symptom:* the module refuses to run at all.

It needs intrinsics and will not guess them. This is not tunable — an essential
matrix is only an essential matrix with respect to a known K.

*Switch to:* a pose estimator that estimates intrinsics jointly.

```
sfm_find_alternatives(produces="poses/v1", excluding="PoseEssentialToPnP")
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

*What helps:* **more images — load all of them.** This failure is a consequence
of subsampling, not a property of the capture: the same 49-frame capture connects
completely when it is loaded whole. `sampling: head` was previously named here as
the fix, and it is only the fix for an artificially capped set, where it buys a
contiguous baseline instead of a sparse one. If you find yourself choosing a
sampling mode to make a reconstruction connect, the actual answer is that the cap
should not be there. Not a parameter here.

## Drift on long sequences

*Symptom:* reprojection error grows with distance from the seed pair; the model
curves.

*Why no parameter helps:* this module is greedy. It registers one image at a time
against fixed structure and never moves a point once accepted, so small errors
compound. That is inherent to incremental SfM without refinement.

*What helps, and it is already on:* **interleaved local bundle adjustment during
registration is implemented in this module and enabled by default** — `local_ba`
plus six parameters that shape it. It refines a sliding window of recent cameras
and their structure as registration proceeds, which is the principled answer to
compounding drift. Follow it with `BundleAdjustmentGlobal`, which this module does
not do and is not a substitute for.

**Correction, because this section said the opposite.** An earlier version
described in-loop local BA as an unimplemented known gap, on the grounds that the
predecessor achieved it by taking a `BundleAdjustmentOptimizerLocal` *instance* as
a constructor argument and this architecture would not reproduce that coupling.
The coupling was indeed not reproduced — the solve is internal rather than another
module's object — but the capability was, and the text was never updated. A reader
arriving here from either local-BA diagnostic was told the feature they were
already running did not exist.

*The residual limit:* local BA bounds drift within its window and cannot bound it
across a sequence much longer than the window. On a set at or below the window
size there is no drift to bound at all, and the parameter guidance changes shape
accordingly — see `tuning.md` and the `local_ba_window` note in the manifest.

## When a global method is simply better

*Symptom:* the images are an unordered collection rather than a sequence, and
registration order is doing real work.

Incremental SfM is order-dependent by construction. On unordered collections a
global method that solves all poses at once is both faster and more robust.

*Switch to:* a mapper that goes straight from correspondences to a reconstruction,
skipping the separate pose stage:

```
sfm_find_alternatives(produces="sparse_model/v1", not_consuming="poses/v1")
```
