---
module: BundleAdjustmentGlobal
module_version: 1.0.0
curated_at: 2026-08-07
---

# Tuning BundleAdjustmentGlobal

Very little to tune, and most of what looks tunable should be left alone. The
interesting decisions are `robust_loss`, `min_track_length`, and whether to refine
intrinsics.

## Reference run

DTU scan1, 12 contiguous images, `max_edge: 1024`, SIFT → NN (exhaustive) →
UnionFind → PoseEssentialToPnP → SparseTriangulation, all defaults:

| metric | value |
|---|---|
| `reprojection_error_before` | 0.3763 px |
| `reprojection_error_after` | 0.2531 px |
| `error_reduction` | 0.328 |
| `points_optimized` | 6941 |
| `observations_optimized` | 22743 |
| `iterations` | 154 |
| `converged` | 1 |
| runtime | 5.3 s |

`reprojection_error_before` (0.3763) matches what `SparseTriangulation`
independently reported (0.376) from a completely separate implementation. That
agreement is a useful cross-check — if the two ever disagree, one of them has a
convention bug, most likely around distortion or resolution.

## `converged` is 0

The solver stopped without reaching convergence.

1. **Check `reprojection_error_before` first.** BA cannot rescue a badly wrong
   input; it will wander and stop. A "before" above ~5px means fix the poses.
2. **Raise `max_iterations`** if `iterations` sits at the cap. This bit on the
   reference scene: the original default of 100 stopped a solve that needed 154,
   and the reprojection error was *identical* either way (0.2531) — only the
   `converged` flag showed it. Raising the cap cost 1.7s. The default is now 300.
3. **Turn `refine_focal_length` off** if it was on. Free intrinsics destabilise
   short sequences badly.

## `error_reduction` near zero

Two very different situations, distinguished by the error level:

- **Low error, no change.** The input was already at a local minimum. Nothing to
  do. This is the expected result of running BA twice.
- **High error, no change.** The poses are at a *bad* local minimum and BA cannot
  climb out of it — it minimises from where it starts. Fix the poses; more
  iterations will not help.

`error_reduction` can also come out **negative**, which is not necessarily wrong:
with `robust_loss` on, the solver is not minimising mean error, it is minimising a
loss that discounts outliers. Trading a slightly worse mean for a much better
inlier fit is the intended behaviour.

## `robust_loss` and `loss_scale`

Leave `robust_loss` on. Plain squared error lets a handful of gross outliers
dominate the whole solve, and there are always some — a mistriangulated point or a
wrong match survives the upstream filters more often than not.

`loss_scale` is roughly "residuals beyond this many pixels stop being trusted".
Set it near the reprojection error you expect from *good* observations: 1-2px at a
typical working resolution. Too large and the robust loss does nothing; too small
and real structure is treated as outlying.

If the input is genuinely clean and you want the last fraction of accuracy, turn
the robust loss off and compare — but check `error_reduction` did not go negative
for the wrong reason.

## `min_track_length`

2 (default) includes two-view points. Such a point has exactly as many constraints
as unknowns, so **BA cannot improve it** — it can only slide it along its ray. It
adds residual blocks without adding information.

3 is a defensible tightening, and on a cloud with a low `mean_track_length` it will
remove a lot. Check `points_optimized` afterwards: if it collapses, the input cloud
was mostly two-view and the real fix is upstream in the matcher's `window`.

## Refining intrinsics

`refine_focal_length` is **off** by default because a supplied calibration is
usually better than what BA recovers from a short sequence, and — more
dangerously — a wrong focal length absorbs pose error into itself and still
reports convergence.

Turn it on when the calibration is untrusted or absent. The refined K is written
to the output artifact's `intrinsics` file, and downstream modules prefer that over
the scene's calibration.

`refine_principal_point` should stay off more firmly still. The principal point is
weakly observable from a short sequence and trades off directly against
translation; refining it on limited data moves error around rather than removing it.

## Cost

Scales with observations, not images. 22743 observations converged in 3.7s.
A hundred thousand takes minutes. If a solve is genuinely slow, `min_track_length: 3`
is the cheapest real reduction, because it removes the residual blocks that carry
the least information.
