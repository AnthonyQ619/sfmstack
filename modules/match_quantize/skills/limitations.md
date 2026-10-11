---
module: MatchQuantize
module_version: 1.0.1
curated_at: 2026-10-10
---

# What MatchQuantize cannot do

## It does not improve a single correspondence

**It makes the match set consistent, and it pays for that in precision.** Every
endpoint is replaced by its lattice point, so the output's coordinates are worse than
the input's by up to half a cell diagonal. Nothing about the matching gets better: a
poor `inlier_ratio` in, a poor `inlier_ratio` out.

So it buys exactly one thing — that a consumer merging by keypoint identity can form
multi-view tracks — and the correct expectation is **a working reconstruction rather
than the best one available.** Measured on nine captures and two detector-free
matchers, the global route through this module reached parity with the incremental
route on the same correspondences for one matcher, and a worse but working result for
the other [S5]. Where the incremental route already works, it remains the better route.

## Detector-based input is refused

A detector-based matcher publishes `feature_index`, which is **exact** identity:
keypoint *k* of an image is row *k* in every pair that cites it. Binning would replace
that with a coordinate approximation — strictly worse, and invisible afterwards.

The module raises rather than degrading quietly. If what you wanted was to merge
duplicate detections of one physical point, that is a different job and it belongs to
the tracker's `merge_eps_px`, which has a conflict metric and an under-merge metric to
steer by.

## Conflicts need a confidence to rank

`on_conflict: confidence` keeps the highest-confidence contender when two
correspondences claim one endpoint cell. **If the input carries no `confidence` array
it cannot rank them**, and falls back to dropping all contenders with a warning rather
than keeping whichever happened to come first. Row order is not evidence, and the
predecessor's silent last-write-wins is the failure being avoided [S6].

Every matcher in this repository does publish confidence, so the fallback should not
fire. It exists because the array is optional in the type and a future producer may
omit it.

## The grid is in working-resolution pixels

`grid_px` is a distance in the pixels of the scene's working resolution, so **a value
is only meaningful at the resolution it was chosen for**, and a model built through
this module at one working resolution cannot be compared with one built at another.
That is the same hazard the loader's resize carries, and the reasoning there applies
unchanged: two models built at different working resolutions are not comparable.

The measured default was chosen at one resolution on one corpus. Carrying it to a
scene loaded at a different size means carrying a different physical tolerance, and the
reading to re-check after any such change is `multiview_fraction`.

## It cannot tell you whether the merge was correct

`conflict_rate` sees two matches wanting one cell. `cycle_merge_rate` sees two scene
points fused into one track — the failure that actually corrupts a solve — and it sees
it only where the view graph closes a triple. **On a graph with no triples, neither
reading can detect a fused point**, and nothing downstream reports it either until a
reconstruction comes out wrong. A sequential capture through this module is therefore
unverifiable at this stage, which is a reason to pair it with exhaustive matching
rather than a reason to avoid it.

## No scene, no geometry of its own

It consumes matches alone — no images, no intrinsics, no poses. It cannot drop a
correspondence for being geometrically wrong, cannot calibrate, and the `inlier_ratio`
it publishes is a measurement it takes rather than a filter it applies. Every geometric
decision stays with the matcher upstream and the reconstructor downstream.
