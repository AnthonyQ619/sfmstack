---
module: FeatureTrackUnionFind
module_version: 1.0.0
produces: tracks/v1
curated_at: 2026-08-07
---

# Reading a FeatureTrackUnionFind artifact

## Layout

```
data/observations.npz
    obs           (N, 4) float32   [track_id, frame_idx, x, y]
    track_count   scalar int64
```

One row per observation. A track seen in five views occupies five rows. This is
the form triangulation and bundle adjustment both want, so no reshaping is needed
downstream.

`track_id` is dense in `[0, track_count)`. Slicing one track is
`obs[obs[:, 0] == t]`.

Coordinates are in **resized** image pixels — the scene's `size_current`, not
`size_original`. Multiply by the scene's per-image `scale` for original-resolution
values, and note that the scale is per image, not per scene.

## Invariants this artifact guarantees

**No track appears twice in the same frame.** With `on_conflict: drop` the
offending tracks are removed entirely; with `first` only one observation per frame
survives. Either way `(track_id, frame_idx)` is unique across the whole table.

This is worth stating explicitly because it is the invariant the predecessor
violated silently — it built a per-frame dict and let the last write win, so a
contradictory track quietly contributed one arbitrary observation of a point that
did not exist.

**Every track has at least `min_track_len` observations**, counted *after* the
conflict policy is applied. A track truncated by `on_conflict: first` is
re-measured against the filter.

## How nodes are formed

The merge is over *nodes*, and what a node is depends on the input.

**With `feature_index` (detector-based matchers).** A node is a row of the
features artifact's keypoint table. Merging is exact: two correspondences share a
node exactly when they cite the same integer. No tolerance, no parameter,
nothing to tune.

**Without it (detector-free matchers).** There is no keypoint table, so each
endpoint starts as its own node and nearby endpoints in the same frame are
clustered first, in a separate union pass, before any match is merged.

The clustering uses four grids of `merge_eps_px`, offset by half a cell in x, y,
and both. A single grid is not enough: two endpoints 0.1px apart that straddle a
cell boundary would land in different cells and never merge, which is exactly the
subpixel jitter a dense matcher produces on one physical point. With four offset
grids, any two points within `merge_eps_px / 2` on each axis are guaranteed to
share a cell in at least one of them. Points up to about `1.4 x merge_eps_px`
apart may also merge.

**Why clustering is a separate pass rather than extra edges in the main one:** a
node must mean "one feature in one frame". If proximity-merged endpoints stayed
distinct nodes, every *successful* proximity merge would put two nodes from the
same frame into one group — which is the exact signature this module reports as a
contradiction. Clustering first keeps `inconsistent_rate` meaning what it says.

## What is NOT here

**Per-observation confidence.** `tracks/v1` has an optional `visibility` array and
this module does not write it. A node participates in several matches with
different confidences and there is no principled way to reduce them to one number;
a learned tracker reports a real per-observation confidence, and writing a
fabricated one here would make the two indistinguishable downstream.

**Which matches built each track.** The merge is destructive. If you need the
provenance, the match artifact is still in the store and is named in this
artifact's `inputs`.

**Anything about 3D.** These are 2D observations grouped by identity. No
triangulation, no depth, no reprojection error — those belong to whatever consumes
this.

## Metrics that mislead

`avg_track_length` rises both when the pipeline improves and when the matcher gets
much worse. It is only comparable at constant matcher `inlier_ratio`. See
[tuning.md](tuning.md) for the measured case — this is the single most misleading
number in the pipeline.

`max_track_length` above what the view graph can support is evidence of transitive
over-merging, not of good tracking.

`inconsistent_rate` is measured over *merged groups*, before the length filter —
so it describes the merge, not the surviving tracks. A track dropped for being
contradictory still counts in the numerator, which is what makes the number a
report on the matcher rather than on the output.
