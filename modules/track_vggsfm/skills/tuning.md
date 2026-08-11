---
module: FeatureTrackVGGSfM
module_version: 1.0.0
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

DTU scan1, 8 contiguous images at `max_edge: 1024`, SIFT at 4096 keypoints,
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

## `dedupe_eps_px`

The same character as `FeatureTrackUnionFind`'s `merge_eps_px`, and the same trap:
too small leaves one point split across query frames, too large fuses distinct
points. 1.5 px at 1024 px merged 45% of raw tracks on the reference run and raised
`avg_track_length` from 3.46 to 3.85 — merging concatenates, so the surviving
tracks are longer as well as fewer.

**A `duplicate_track_rate` near zero at a sane eps is a warning, not a success.**
It means the query frames are seeing disjoint parts of the scene, which usually
means there are too few of them.

Set it to 0 only to measure what it was doing.

## `visibility_threshold` is a real probability

Unlike the confidences elsewhere in this repository — VGGT's, MapAnything's, both
unbounded — this one is a genuine 0–1 visibility prediction, so 0.5 means what it
looks like.

Raise toward 0.7 to shed observations in frames where the point is occluded or out
of frame; tracks get shorter and what survives is better placed. Lower it only if
`avg_track_length` is collapsing, and check `mean_visibility` first — a low
threshold cannot fix a query set that sees nothing.

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
