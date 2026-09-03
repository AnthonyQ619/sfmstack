---
module: FeatureTrackTapir
module_version: 1.5.0
curated_at: 2026-08-11
---

# Reading a FeatureTrackTapir artifact

## Layout

`tracks/v1`: `observations` with `obs` (track_id, frame_idx, x, y), `track_count`,
and `visibility` — one value per observation, holding `(1 − σ(occlusion)) · (1 −
σ(expected_dist))`.

Note what that array contains here against what it contains in
`FeatureTrackVGGSfM`: there it is a single visibility prediction, here it is a
product of two independent ones. Both are genuine 0–1 probabilities; they are not
the same quantity, and a threshold does not carry between the modules.

Coordinates are in scene pixels, mapped back from the model's square frame.
Predictions landing outside the image are dropped, counted by
`observations_outside_frame`.

## `duplicate_track_rate` is redundancy, not error

0.50 on the reference run. Each query frame re-finds points the others already
had, so the rate rises with `query_frame_num` by construction. **Near zero is the
thing to worry about** — it means the query frames see disjoint parts of the scene.

## `inconsistent_rate` is always 0.0 here

Structural, not a health signal. See
[limitations](limitations.md#inconsistent_rate-cannot-detect-anything-here).

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
