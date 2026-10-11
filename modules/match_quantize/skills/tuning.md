---
module: MatchQuantize
module_version: 1.0.0
curated_at: 2026-10-10
---

# Tuning — MatchQuantize

Sourced claims resolve in [sources.md](sources.md).

Before any section below: **this module has one parameter that matters.** `grid_px`
decides whether anything merges, and the other four are bookkeeping. Read
`multiview_fraction` first, `cycle_merge_rate` second, and treat everything else as
context for those two.

---

## Do not tune `grid_px` on the track yield

**This is the one warning on this page that was earned the expensive way, and it
contradicts the obvious heuristic.**

More multi-view tracks is not better pose accuracy. Counting the tracks a grid
produces is cheap, needs no reconstruction, and points the wrong way: measured across
two detector-free matchers, the grid that maximised the count of three-view
correspondence components was the **worst** grid for pose on three of the captures
where the choice mattered at all [S4]. Going from the finest grid to the coarsest took one
indoor capture from 0.124 to 0.313, a room-rig capture from 0.186 to 0.333, and an
outdoor site capture from 0.094 to 0.158 — while the track count fell the whole way.

The mechanism is not measured and no claim is made about it. The practical rule is:
**tune against the downstream pose reading, or take the default.** A yield curve is
not a substitute, and this module publishes `multiview_fraction` to tell you whether
the merge *worked at all*, not to be maximised.

---

## `multiview_fraction` is zero, or near it

**Read it as:** the merge did not merge. Every correspondence component still spans at
most two images, which is the state the input was already in, so a consumer that needs
three views will get nothing from this output.

**Gradient:**

1. **Raise `grid_px`.** This is the first move and usually the only one. At a grid
   finer than the matcher's own disagreement between pairs, no two endpoints of the
   same physical point land in the same cell and the output is the input renumbered.
2. **Check the view graph before blaming the grid.** A set whose pairs form no closed
   triple cannot produce a three-view track at any grid size — there is no third view
   to agree with. `graph_components` above 1 is the extreme case; a sequential chain
   with no revisits is the ordinary one.
3. If it stays near zero at a coarse grid *and* the graph has triples, the matcher's
   pair-to-pair disagreement is larger than any usable cell. Prefer the incremental
   route, where a tracker merges by proximity with an under-merge metric to steer by.

**Do not** reach for a coarser grid than `conflict_rate` tolerates. Fusing two scene
points into one track is worse than having no track — a wrong multi-view constraint
propagates through a global solve, where a missing one merely costs coverage — and
`conflict_rate` is the reading that sees it. `cycle_merge_rate` does not, on this
input [S9].

---

## `conflict_rate` is high

**Read it as:** binning made two distinct correspondences claim the same endpoint
cell, and they cannot both survive — one cell is one keypoint, and a keypoint matches
at most one keypoint per pair.

**Gradient:**

1. **Lower `grid_px`.** This is the direct cause and the direct fix. The rate rises
   with the grid, monotonically, because a coarser cell captures more distinct
   correspondences.
2. **`conflict_rate` is the reading to use here, and `cycle_merge_rate` is not.** An
   earlier version of this page said to protect the latter, and that was wrong in a
   way worth recording: on this module's output the merge rate FALLS as the grid
   coarsens [S9], so "protect it" steers a reader to a fine grid — which is the
   setting measured to be worse for pose on the captures where the choice matters at
   all [S4]. A conflict is local and this module caused it; the merge rate on this
   input is largely the matcher's own pair-to-pair disagreement, which binning reduces
   rather than creates.
3. Set `on_conflict` deliberately rather than inheriting it. `confidence` keeps the
   match the matcher was most sure of; `drop` discards all of the contenders and costs
   matches on exactly the dense pairs carrying the reconstruction.

---

## The metrics that are not about this module

`inlier_ratio`, `graph_components`, `largest_component_fraction`, `min_image_degree`,
`matches_per_pair` and `min_matches_per_pair` are re-measured on the output rather than
carried forward, because binning only ever removes matches and a pair the matcher kept
can fall under `min_matches` here. **But they are readings about the MATCHER's work,
not this module's** — nothing here improves a correspondence, so a poor `inlier_ratio`
on this output was a poor `inlier_ratio` on the input. Fix it upstream.

`inlier_ratio` is measured at `ransac_threshold`, defaulted to the classical matcher's
value for exactly one reason: that is the only way the two modules' readings are
comparable. Change it and you lose the comparison.

## What here rests on nothing — the manifest audit

Audited against this module's own manifest. **Six metrics carry a band, and not one of
them is a measurement.**

Two are **chosen**: the `multiview_fraction` floor of 0.05 and the `conflict_rate`
ceiling of 0.2. They mark "the merge did something" and "a fifth of the matches went to
conflicts" — judgements about what is worth a reader's attention, not cut points
anything here measured.

Four are **structural**, true by the shape of the problem rather than by observation: a
view graph in more than one component holds images no track can link; an image on a
single edge is one pair from being lost; zero surviving pairs means nothing downstream
runs; and full coverage is one component holding every image. Those are arguments, and
they would read the same on a corpus of one capture or a thousand.

**Nothing in this module bands a quantity it measured**, which is the honest state for
a module whose own sweep was scored on pose downstream rather than on any reading
published here. `cells_per_endpoint` carries no bound at all and is a description of
how much merging happened, not a verdict on it. `matches_per_pair` and `inlier_ratio`
deliberately carry none either: the classical matcher bands both from its own
measurements, and inheriting another module's cut point would be worse than silence.

The `ransac_threshold`, `ransac_confidence` and `min_matches` defaults are **inherited
from the classical matcher for comparability** and were not tuned here. The `grid_px`
default of 4.0 is the one number on this page with a measurement behind it [S3], and
it is a corpus result at one working resolution — not a universal
constant. See [limitations.md](limitations.md#the-grid-is-in-working-resolution-pixels).
