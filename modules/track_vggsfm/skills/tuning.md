---
module: FeatureTrackVGGSfM
module_version: 1.5.0
curated_at: 2026-08-11
---

# Tuning FeatureTrackVGGSfM

1. `mean_visibility` — did the query frames see the scene?
2. `min_frame_observations` — did every frame get covered?
3. `track_survival_5` — the reason this module exists.
4. `duplicate_track_rate` — how much redundancy the query set carried.

`track_count` is deliberately fourth. It is lower than a union-find tracker's on
the same scene and that is not a defect.

## Reference run

A controlled-rig capture, 8 contiguous images at `max_edge: 1024`, SIFT at 4096 keypoints,
`max_query_points_per_frame: 2048`, on one A6000 in a container:

| metric | dino q5 | midpoint q3 | interval q5 | dino q5, no dedupe |
|---|---:|---:|---:|---:|
| `track_count` | 4033 | 2742 | 3478 | 7329 |
| `avg_track_length` | 3.85 | 3.71 | 2.60 | 3.46 |
| `long_track_fraction` | 0.712 | 0.716 | 0.406 | 0.687 |
| `track_survival_5` | 0.345 | 0.311 | 0.033 | 0.274 |
| `min_frame_observations` | 1449 | 645 | 621 | 2285 |
| `duplicate_track_rate` | 0.450 | 0.385 | 0.405 | 0 |
| `mean_visibility` | 0.348 | 0.350 | 0.231 | 0.348 |
| runtime | 17 s | 5 s | 9 s | 9 s |

## Query frames are the whole game

Everything else on this page is a second-order effect.

**`mean_visibility` is the number that reads the choice.** 0.35 when the query
frames are central, 0.23 when they include the ends. Below 0.3 the
`poor_query_selection` diagnostic fires, and the fix is the selection, never a
threshold.

**Avoid endpoints on a sequential capture.** Tracking from frame 0 of the
reference set leaves each point visible in 1.77 frames; from frame 4, 4.40. An
endpoint sees the least of the scene by construction. `interval` reaches them and
is the weakest of the three here for exactly that reason.

**Try `midpoint` with fewer query frames before raising `query_frame_num`.** Three
central frames matched five dino-ranked ones on every track-quality metric at a
third of the runtime. `dino`'s advantage is that it adapts to an *unordered* set,
where "the middle" means nothing.

**Watch `min_frame_observations`.** A frame no query frame tracks into gets thin
and will not register, whatever the totals say. The fix is a query frame near it —
lowering `visibility_threshold` admits noise everywhere to solve a problem in one
place.

## `dedupe_eps_px` — worth tuning, inside a hard ceiling

The same character as `FeatureTrackUnionFind`'s `merge_eps_px`, and the same trap:
too small leaves one point split across query frames, too large fuses distinct
points. 1.5 px at 1024 px merged 45% of raw tracks on the reference run and raised
`avg_track_length` from 3.46 to 3.85 — merging concatenates, so the surviving
tracks are longer as well as fewer.

**A `duplicate_track_rate` near zero at a sane eps is a warning, not a success.**
It means the query frames are seeing disjoint parts of the scene, which usually
means there are too few of them.

**Ceiling 2.0, enforced by the schema.** `tracks/v1` fixes its duplicate test at
2.0 px, so a merge at 2.0 has already removed everything the type will call a
duplicate — every merge above it fuses tracks the type classifies as **distinct**.
Measured across nine scenes (six field captures with ground-truth poses, three controlled-rig captures), by
6.0 px the median run has lost **74% of its tracks and 81% of its bundle-adjusted
points** at unchanged registration, and the error at a fixed observation count is
worse in about 70% of cases. Wins above 2.0 are the model shrinking: one reached
0.89 px on **44 points**, down from 1120.

**Inside 0–2 it is worth sweeping, and it cannot be guessed.** The best value
landed at 0.0, 0.5, 1.0, 1.5 and 2.0 on different scenes, and the *direction* of
the effect flips — on a repetitive building frontage more merging helped monotonically; on
a glazed-elevation traverse any merging at all cost ~60% of the pose accuracy. Nothing upstream
predicts which: not `trifocal_transfer_px`, not the track statistics, not the
scene. Getting it right rather than leaving it at 1.5 is worth a median ~8%
(VGGSfM) to ~25% (TAPIR) on rotation error.

**Sweep against a reconstruction, and throw away rows that registered fewer
images.** Raising this deletes tracks; deleting tracks removes the 2D–3D links PnP
needs; an image below `min_pnp_inliers` is never registered. A smaller model scores
better on every aggregate, so a row with fewer registered images — or fewer points
— is not a better row.

**0 is not the safe default either.** Deduplication off cost TAPIR **9.86°** of
median rotation error on a fast traverse past a glazed elevation against 1.63° with a tolerance set, and
broke a 16-image `courtyard` reconstruction outright. Both ends fail.

See [`docs/import_lessons.md`](../../../docs/import_lessons.md).

## `visibility_threshold` is a real probability

Unlike the confidences elsewhere in this repository — VGGT's, MapAnything's, both
unbounded — this one is a genuine 0–1 visibility prediction, so 0.5 means what it
looks like.

**Raising it does not buy precision.** That is the intuition the parameter invites
— shed the occluded observations and what remains is better placed — and it has
been tested against `trifocal_transfer_px`, which is the metric that would show
it. Across every capture where the comparison was legal (same query selection,
same `dedupe_eps_px`, equal `trifocal_triples`), raising the threshold discarded
observations, shortened tracks, thinned the weakest frame, and left transfer error
unchanged or **worse** — never better, on any capture, in either dataset family
tried.

**The mechanism is why, and it is not a property of these captures.** Predicted
*visibility* and positional *error* are different quantities. The model's
confidence that a point is in view says nothing about whether it put that point in
the right place, so the observations a higher threshold removes are not
disproportionately the mispredicted ones. You pay coverage and get no accuracy
back.

**So treat it as a floor to leave alone.** Lower it only if `avg_track_length` is
collapsing, and check `mean_visibility` first — no threshold fixes a query set
that sees nothing.

## Nothing survives

The error message reports `mean_visibility` and the chosen query frames. If it is
low, the query selection is the cause and no threshold change will help.

If it is healthy and nothing survived anyway, check the detector produced
keypoints in the chosen query frames at all — this module tracks what the detector
found, and a query frame with no keypoints contributes nothing.

## Memory and time

`max_query_points_per_frame` first: 2048 points over 8 images at 1024 px peaked at
6.9 GiB. It is linear in both time and memory.

`max_points_num` is a pure memory control — the result is identical whatever it is
set to, only the chunking changes.

`fine_tracking: false` is a speed check, not a setting. The coarse tracker works
on a stride-8 feature map, so without refinement the positions are several pixels
off and triangulation inherits all of it.

## Reading `trifocal_transfer_px`

The only metric here that measures where the observations are rather than how many
there are, and this module's characteristic weakness is exactly that. Read it
against a chaining tracker's on the same scene: the gap is what predicting rather
than matching costs.

**It is the number that should move when the working resolution does.** Where a
resolution parameter exists it is the one to reach for; where it does not, this
metric is a property of the model rather than a knob.

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

## What here rests on nothing — the manifest audit

Audited against this module's own manifest. The `avg_track_length`,
`min_frame_observations`, `split_rate` and `track_survival_5` bands have no
diagnostic reading them — descriptions of the captures measured so far, not
judgements on yours. The numbers in the `query_selection`, `query_frame_num`,
`max_query_points_per_frame`, `visibility_threshold`, `min_track_len`,
`fine_tracking` advice (and two more) are settings that worked in isolated
testing, not published results — and this module has run **zero times** in a
real pipeline.
