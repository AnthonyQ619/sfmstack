---
module: SparseGlobalCOLMAP
module_version: 1.4.3
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

## Matches with no `feature_index`

It refuses them, **before the solve rather than after it**, as
`matches_not_indexed`.

The mechanism is structural, not a tuning threshold. With no `feature_index` every
match endpoint is its own keypoint, and COLMAP's correspondence graph merges
observations by keypoint IDENTITY rather than by geometry. So a point seen in ten
images produces ten unrelated keypoints and nine independent pairs: **no track can
reach a third view**, however much the images overlap. Two independent gates then
discard what is left -- `min_track_len` demands three views, and retriangulation
ignores two-view tracks by a default this module does not expose. Lowering
`min_track_len` passes the first gate and not the second, which is why that dial
is not the fix.

This is a property of the INPUT, not of the capture and not of the matcher's
quality. A detector-free matcher can return an excellent correspondence field and
still land here.

**Escape:** give the matches keypoint identity first, then run this module on the
result.

```
find(produces="pairwise_matches/v1", consumes="pairwise_matches/v1")
```

That is the transform shape -- the only module family that consumes the type it
produces -- and it fills the optional `feature_index` the matcher left empty. Read
its own page for the tolerance it takes; the tolerance is the whole parameter.

**Second escape:** the incremental route -- a tracker, pose estimation, then
triangulation -- reconstructs these same matches without that step, because a
tracker merges by proximity and never needed identity. It costs the tracker's
`merge_eps_px`, which is per matcher and per resolution.

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
