---
module: FeatureTrackUnionFind
module_version: 1.0.0
curated_at: 2026-08-07
---

# Sources

## Union-find track building

Standard practice rather than a single paper. The clearest statement of the
approach and its failure mode is in **Schönberger and Frahm, "Structure-from-Motion
Revisited", CVPR 2016** (COLMAP), section 4, where the scene graph is built from
verified two-view geometries and tracks follow from its connected components.

COLMAP's important departure from a plain union-find pass is that it does *not*
merge unconditionally. Merges that would make a track inconsistent are refused
during incremental registration, rather than performed and cleaned up afterwards.
This module does the cleanup version, which is why `on_conflict` exists at all —
see [limitations.md](limitations.md#what-would-replace-this-implementation-specifically).

The disjoint-set structure itself: union by size with path halving, giving the
inverse-Ackermann amortised bound (Tarjan 1975). Path halving rather than full
compression because it needs no second pass and is measurably faster in practice.

## Why track consistency matters

**Snavely, Seitz, Szeliski, "Photo Tourism", SIGGRAPH 2006**, section 4.2, states
the constraint plainly: a track containing two keypoints from the same image is
inconsistent and is discarded. That is the origin of the `drop` policy here.

Photo Tourism discards; it does not offer a `first` alternative. That option was
added because the predecessor effectively implemented it by accident — building a
per-frame dictionary and letting the last write win — and reproducing its
behaviour deliberately makes the two comparable. It is not recommended.

## The ratio-test / track-length interaction

Not from a paper. Measured in this repository on DTU scan1; the table is in
[tuning.md](tuning.md#avg_track_length-is-not-a-quality-metric).

Recorded because it contradicts an intuition that is easy to form: that longer
tracks are better tracks. Across a matcher `ratio_test` sweep from 0.7 to 1.0,
`avg_track_length` rises monotonically while the matcher's `inlier_ratio` falls
from 0.97 to 0.22 and `inconsistent_rate` rises 58x. Track length is a quantity
that improves when the pipeline degrades.

## Grid-based proximity merging

The four-offset-lattice construction is a standard trick for approximate
neighbour queries without a spatial index: with grids offset by half a cell in
each axis, any interval shorter than half a cell fits entirely within some cell of
some grid. Applied here in 2D over the four (x, y) offset combinations.

Chosen over a KD-tree because sfmkit's dependency constraint allows numpy and
nothing else — no scipy — and over a single grid because a single grid fails
exactly on the subpixel jitter it needs to absorb. Verified by test: two endpoints
0.5px apart in the same frame merge at `merge_eps_px=1.5` and do not at 0.1.

## Predecessor code

`scene_agent/breadth_agent/src/sfmcore/featuretracking.py`, and the pair-merging
logic inside `DataTypes/featmatchDT.PointsMatched`.

The predecessor conflated three things in one class: a pairwise container, a
multi-view track container, and an observation registry reconciling them. Every
consumer branched on which half happened to be populated. Splitting them into
`pairwise_matches/v1` and `tracks/v1` is what makes this module a single function
rather than a set of mode flags.

`pseudo_merge_eps_px` in `PointsMatched` is the direct ancestor of
`merge_eps_px`, and carried the same default of 1.5px.
