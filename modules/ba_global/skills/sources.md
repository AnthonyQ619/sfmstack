---
module: BundleAdjustmentGlobal
module_version: 1.1.0
curated_at: 2026-08-07
---

# Sources

## Bundle adjustment

**Triggs, McLauchlan, Hartley, Fitzgibbon, "Bundle Adjustment — A Modern
Synthesis", Vision Algorithms 1999.** Still the reference. Sections 3 and 4 cover
the sparse normal-equation structure that makes the problem tractable; section 6
covers gauge freedom, which is why this module pins two cameras
(`BundleAdjustmentGauge.TWO_CAMS_FROM_WORLD`) rather than leaving the similarity
free.

The gauge choice matters practically: without it the solver wanders along the
7-dimensional similarity manifold, which costs iterations and produces a model in
an arbitrary frame each run.

## The robust loss

Cauchy, via Ceres. **Triggs et al., section 5.3** on robust cost functions.

The default-on choice is a judgement, not a citation: real correspondence sets
always contain a few gross outliers that survive upstream filtering, and squared
error lets them dominate. The predecessor also defaulted `robust_loss=True`, using
Huber; Cauchy is more aggressive at large residuals, which suits an input where
the outliers are *wrong* rather than merely noisy.

## Implementation

**pycolmap 4.1.1**, wrapping COLMAP's `BundleAdjuster` over Ceres.

Two API details worth recording, because both produced plausible wrong numbers
rather than errors:

- `Reconstruction.compute_mean_reprojection_error()` averages a per-point `error`
  field that is unset until `update_point_3d_errors()` is called. It returns
  **0.0** on a freshly built reconstruction.
- `pycolmap.bundle_adjustment(rec, options)` returns `None` (its signature says
  so). Convergence and iteration counts must come from
  `create_default_bundle_adjuster(...).solve()`.

Ceres solver options live at `options.ceres.solver_options`, not on
`options.ceres`. The object rejects unknown attributes, so a typo is an
`AttributeError` at solve time rather than a silently ignored setting — the good
failure mode, and worth relying on.

## COLMAP's larger loop

**Schönberger and Frahm, CVPR 2016**, section 4.5. COLMAP does not call BA once;
it alternates local BA, global BA, retriangulation, and filtering, iterating until
the model stops growing.

This module is one call. The alternation is expressible at the orchestrator level —
triangulate, adjust, triangulate again — which the driving agent can drive without
any new module, and which is a better fit for this architecture than nesting
optimisers inside estimators (as the predecessor did).

## Predecessor code

`scene_agent/breadth_agent/src/sfmcore/optimization.py`,
`BundleAdjustmentOptimizerGlobal` (lines 332+).

Same backend, same defaults for `refine_*` (all False) and `max_num_iterations`
(50 there, 100 here). The substantive differences:

- It consumed and returned a live `Scene` object holding a `pycolmap.Reconstruction`
  in memory, which is what forced the whole pipeline into one process. Here the
  model round-trips through arrays, and the COLMAP form is an optional sidecar.
- It could not report before/after error, because it had no independent measure of
  the input — the reconstruction it was handed was the same object it mutated.
