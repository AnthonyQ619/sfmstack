---
module: MatchQuantize
module_version: 1.0.0
curated_at: 2026-10-10
---

# Reading a MatchQuantize artifact

The output is a `pairwise_matches/v1`, the same type as the input, and a consumer needs
no knowledge that this module ran. **One field is different and it is the whole point.**

## `feature_index` is now present

That absence was the defect; its presence is the repair. A consumer branches on it:
present means merge by identity, absent means merge by proximity. Downstream of this
module the identity path is the one that runs.

The indices are **cell numbers, not detections.** Keypoint *k* of an image is the *k*th
occupied grid cell in that image, in the order the cells were first encountered. They
index nothing outside this artifact — there is no `features/v1` to join against, and
there never was.

## `multiview_fraction` is the reading that matters

The share of correspondence components spanning **three or more images**. Everything
else on the artifact is secondary.

It is **0.0 on the input by construction** [S1] — that is the defect, not a property
of the capture — so any value above zero is work this module did. Near zero on the output
means the grid was too fine to merge anything and the artifact is the input renumbered.
It is computed by union-find over `(image, cell)` nodes, which is the same structure a
downstream correspondence graph builds, so it is the answer that consumer will actually
get rather than a proxy for it.

## `cycle_merge_rate` was null on the way in, and is not any more

The three-view test needs keypoint identity to have something to disagree about, so a
detector-free matcher reports it null. **Supplying that identity is this module's whole
job, which makes the metric the input could not report the one that measures whether
the job was done safely.**

**Do not read it as an over-merge alarm on this module's output** — that was this
page's first reading of it and the measurement contradicts it [S9]. On one capture at
two grid sizes the rate **falls as the grid coarsens**, 0.67 at 1 px against 0.39 at
4 px, which is the reverse of what fusing distinct points into one cell would do; and
pose was unchanged across that swing, 0.9744 against 0.9743.

The reading it supports is that the chains disagree because the MATCHER's estimates
disagree between pairs — the defect binning exists to reduce — and that a coarser cell
absorbs more of that disagreement. No mechanism is claimed, and this rests on one
capture. For whether binning damaged anything, `conflict_rate` is the local view and
the downstream reconstruction is the outcome. `cycle_split_rate` beside it is the cheap
failure: one point carried on two cells, costing track length.

## The view-graph metrics are re-measured, not carried forward

`pairs_matched`, `matches_per_pair`, `min_matches_per_pair`, `min_image_degree`,
`graph_components`, `largest_component_fraction` and `inlier_ratio` all describe **this
artifact's** match set. Binning only ever removes matches — to cell conflicts, to
collapsed duplicates, and to `min_matches` — so a pair the matcher kept can be absent
here, and carrying the input's numbers forward would describe a set that no longer
exists.

`pairs_proposed` is the input's pair count, so `pairs_matched` against it says how much
of the matcher's graph survived binning.

**But they are readings about the matcher's work.** Nothing here improves a
correspondence, so a poor `inlier_ratio` on this output was poor on the input.

## `planarity` is null, deliberately

This module fits no homography. Measuring one here would be a second opinion on the
matcher's geometry rather than a reading about anything this module did, and the type
allows the honest answer.

## The note says what happened to every match

The narrative body records input matches, endpoints, cells produced, matches kept,
conflicts resolved, duplicates collapsed, pairs surviving `min_matches`, and
`multiview_fraction` with its component counts. Those numbers reconcile: endpoints
minus cells is the merging, and input matches minus kept is conflicts plus duplicates.
If they do not reconcile, read the artifact rather than the note.
