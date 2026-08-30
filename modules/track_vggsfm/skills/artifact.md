---
module: FeatureTrackVGGSfM
module_version: 1.5.0
curated_at: 2026-08-11
---

# Reading a FeatureTrackVGGSfM artifact

## Layout

`tracks/v1`: `observations` with `obs` (track_id, frame_idx, x, y), `track_count`,
and a `visibility` array — one value per observation, the tracker's predicted
visibility at that frame. `FeatureTrackUnionFind` writes no visibility, because
chaining verified matches produces no such number.

Coordinates are in the scene's working resolution, and every one lies inside the
image: the tracker extrapolates outside the frame rather than refusing, and those
predictions are dropped. `observations_outside_frame` counts them.

## `duplicate_track_rate` is redundancy, not error

0.45 on the reference run: deduplication merged 7329 raw tracks into 4033. Each
query frame re-finds points other query frames already had, so the rate rises with
`query_frame_num` by construction.

**Near zero is the thing to worry about**, not high. It means the query frames see
disjoint parts of the scene, which usually means there are too few of them.

## `inconsistent_rate` is always 0.0 here

Not a health signal. Each query point yields at most one position per frame, so a
track cannot contradict itself the way a union-find track can. Comparing this
module's `inconsistent_rate` with `FeatureTrackUnionFind`'s compares a structural
impossibility with a measurement.

## `mean_visibility` is over ALL predictions, not the kept ones

It is computed before thresholding, across every query point and every frame — so
it reads the *query selection*, not the quality of what survived. 0.35 for a
central query set, 0.23 for one that includes the ends.

## `split_rate` beside `duplicate_track_rate`

They are not the same number and the difference is the point.

- **`duplicate_track_rate`** is what deduplication REMOVED, at this module's own
  `dedupe_eps_px`.
- **`split_rate`** is what the table as written still holds apart, at a tolerance
  **fixed by `tracks/v1`** so it is comparable with every other tracker.

Read together they say whether `dedupe_eps_px` is set right. A high `split_rate`
with deduplication on means the module's tolerance is tighter than the type's test
and duplicates are surviving.

`split_rate` is also the number that makes this module comparable with a chaining
tracker at all: `inconsistent_rate` is structurally zero here and carries no
information, and this is its dual.

## `trifocal_transfer_px` — the only metric here that measures position

Everything else in `tracks/v1` is about length, coverage or self-consistency, and
this module's characteristic weakness is precision — the positions are predictions
at reduced resolution, not detected keypoints. No other metric can see that.

It is a held-out three-view prediction: relative pose and a third camera are fitted
from half the tracks common to a frame triple, and the *other* half's points are
predicted into the third view and measured there. Nothing about a measured track's
third-view observation took part in the fit.

**What one pixel is.** A single measurement is one observation of one track in one
image: this module says the point is at (x, y) there, and geometry fitted from
*other* tracks says it should be at (x', y'). The measurement is the distance
between those two, in that image's pixels at the scene's working resolution. The
metric is the median over every held-out measurement, so a reading of 2.5 means
"typical observation sits 2½ px from where the rest of the table says it belongs",
and the same tracker on the same scene at half the resolution reads about half.

**This is the number to compare against a chaining tracker**, and the one that
should move when the model's working resolution does. Null on an uncalibrated
scene.

## Metrics that mislead

**`track_count` is lower than a union-find tracker's and that is expected.** 4033
against 4702 on the same scene, with tracks that are 35% longer and three times as
likely to reach five views. Read `track_survival_5`.

**`track_count` also moves with `dedupe_eps_px` for reasons unrelated to quality.**
7329 without deduplication, 4033 with. Two runs are not comparable across it.

**`avg_track_length` rises when deduplication merges**, because merging
concatenates: 3.46 without, 3.85 with. That is not the tracker getting better.

**Nothing here measures positional accuracy.** Visibility is a confidence about
*whether* a point is seen, not *where*. The first number that measures where is the
triangulator's reprojection error.
