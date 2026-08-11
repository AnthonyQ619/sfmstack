---
module: SparseGlobalCOLMAP
module_version: 1.0.0
curated_at: 2026-08-10
---

# What SparseGlobalCOLMAP cannot do

## Uncalibrated scenes

It needs intrinsics and refuses without them. Rotation averaging works on
calibrated relative poses; an uncalibrated graph gives projective quantities that
do not average.

**Escape:** a reconstructor that estimates its own intrinsics.

```
find(produces="sparse_model/v1", not_consuming="pairwise_matches/v1")
```

VGGT and MapAnything qualify and take `scene/v1` directly.

## What global cannot recover from

**A disconnected view graph.** Two components have no relative rotation between
them, so no averaging relates them. The pipeline returns several models and this
module keeps the largest, marking the rest `valid=False`. Fix it in the matcher —
`pairing: exhaustive`, or a wider `window`.

**A wrong relative rotation admitted into averaging.** Incremental SfM tends to
localise a bad pair's damage to the images near it; averaging distributes it. This
is the real trade, and it is why `min_num_matches` and `min_inlier_ratio` are
stricter here than a matcher's own thresholds.

**Repeated structure.** A facade that matches itself produces a confident, wrong
relative pose. It fails the same way incremental does, but the error spreads
further. Raise `min_inlier_ratio` toward 0.5 on such scenes and check the
matcher's `planarity`.

## No per-image evidence

There is no seed pair to inspect, no `min_pnp_inliers` to relax, no per-image
inlier count. When one camera lands in the wrong place, this module cannot say
why — the evidence is in the view graph it was given.

**Escape:** run the incremental estimator on the same tracks for a second opinion.

```
find(produces="poses/v1", consumes="tracks/v1")
```

Two independent estimates disagreeing about one camera localises the problem to
that camera; agreeing localises it to the matcher.

## It is not a refinement stage

It reconstructs from correspondences. Feeding it a model to improve is not
possible — it consumes `pairwise_matches/v1` and nothing else. For refinement:

```
find(consumes="sparse_model/v1", produces="sparse_model/v1")
```

`BundleAdjustmentGlobal` and `BundleAdjustmentLocal` answer that, and running
global BA after this module is legitimate and usually buys a little.

## Determinism

`random_seed` defaults to 0 so a re-run reproduces. Setting it to -1 makes the
solve non-deterministic while leaving the artifact id unchanged — two genuinely
different outputs would collide on one id. Change a real parameter if you want to
compare runs.
