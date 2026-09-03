---
module: FeatureTrackUnionFind
module_version: 1.4.0
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

## `unmergeable_input` is not a diagnostic, and used to be listed as one

The manifest declared it and the module never emitted it, because when detector-free matches arrive with merge_eps_px at 0 -- the module RAISES, because endpoints cannot be merged by proximity with a zero tolerance. A raise is the right behaviour — there is no artifact to hang a diagnostic on — but a diagnostic listed in the contract and unreachable in practice is worse than none: a reader planning against `sfm_describe_module` sees a failure mode they can catch and read, and will instead get an exception. The declaration is gone; the raise and its message are unchanged, and the message says more than the diagnostic did.

## What is asserted without a source

Audited 2026-09-02 against this module's own manifest.

- **Healthy bands with nothing behind them.** `avg_track_length`, `split_rate`, `track_survival_5` declare a range and no diagnostic on this module reads them. A band with no diagnostic is a description of the captures measured so far, not a judgement on yours -- and a corpus maximum is the largest of N draws, so the next capture exceeding it is expected rather than anomalous.
- **Numeric tuning advice with no citation in this file.** `min_track_len`, `probe_merge_headroom`, `merge_eps_px` name specific values in their tuning prose. The reasoning behind them may be sound; the numbers are settings that worked here, not results anyone has published.
- **Scope of the measurements.** What is written here was exercised across 84 runs of this module in a seventeen-capture sweep of benchmark captures, at version 1.4.0. That is the whole evidence base: no capture outside those two benchmark families has been run through it.

## Review triggers

Re-read and re-check this file when any of these happens:

- **This module's version changes from 1.4.0.** These notes were written against it; a metric set or a published band can change with a version and the prose does not follow automatically.
- **A capture unlike the benchmark families appears.** Every band here was fitted on controlled-rig and field captures from two benchmark datasets. Per-frame appearance readings transfer to a larger capture; adjacent-motion readings and anything denominated in pairs do not.
- **A reading crosses one of `avg_track_length`, `split_rate`, `track_survival_5` and nothing fires.** That is this file's known gap, not a defect in the capture -- but it is the signal that the band deserves either a diagnostic or a wider range.
