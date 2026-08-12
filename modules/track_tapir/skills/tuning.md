---
module: FeatureTrackTapir
module_version: 1.0.0
curated_at: 2026-08-11
---

# Tuning FeatureTrackTapir

1. `input_size` — the one parameter that decides whether the output is usable.
2. `mean_occlusion` beside `mean_confidence` — they diagnose different problems.
3. `min_frame_observations` — did every frame get covered?
4. `duplicate_track_rate` — how redundant the query set was.

## Reference run

DTU scan1, 8 contiguous images at `max_edge: 1024`, SIFT at 4096 keypoints,
`query_selection: midpoint`, `query_frame_num: 3`, on one A6000 in a container:

| metric | 256 | **384** | interval, 256 | `min_confidence: 0.3` |
|---|---:|---:|---:|---:|
| `track_count` | 2629 | 2736 | 3131 | 2694 |
| `avg_track_length` | 5.95 | 5.98 | 5.58 | 5.93 |
| `long_track_fraction` | 0.924 | 0.927 | 0.875 | 0.913 |
| `track_survival_5` | 0.738 | 0.754 | 0.658 | 0.731 |
| `duplicate_track_rate` | 0.534 | 0.503 | 0.440 | 0.540 |
| `mean_confidence` | 0.729 | 0.709 | 0.685 | 0.729 |
| `mean_occlusion` | 0.217 | 0.235 | 0.252 | 0.217 |
| runtime | 8 s | 5 s | 3 s | 3 s |

## `input_size` — and why the track metrics will not tell you

Track statistics barely move across it. Reconstruction moves a great deal:

| `input_size` | tri points | tri error | `yield` |
|---:|---:|---:|---:|
| 256 | 887 | 1.715 px | 0.337 |
| **384** | 1548 | 1.581 px | **0.566** |
| 512 | 1445 | **1.434 px** | 0.539 |
| 768 | 1433 | 1.470 px | 0.525 |

At 256, one model pixel is four scene pixels across on a 1024-wide scene. The
tracks are just as long and just as connected; they are 4 px off, and the
triangulator's `max_reprojection_error` rejects them. **`yield` is the metric that
sees this and no track metric does.**

384 is the default. 512 buys a slightly lower error for a slightly lower yield —
take it if the points feed bundle adjustment and precision matters more than
count. 768 is worse than 384 on every track metric: the model is being run far
from the resolution it was trained at.

**The corollary:** on a scene loaded at 512 px rather than 1024, `input_size: 256`
is proportionally less lossy. Set it relative to the scene's working resolution,
not in absolute terms.

## Read `mean_occlusion` and `mean_confidence` together

They separate two problems the other trackers cannot distinguish:

| `mean_occlusion` | `mean_confidence` | reading |
|---|---|---|
| high (>0.5) | low | The points leave view. Change the query selection. |
| low | low | The model sees them and cannot localise them. Raise `input_size`. |
| low | high | Healthy — 0.24 and 0.71 on the reference run. |

Lowering `min_confidence` in the second case admits observations the model has
already said are badly placed, which is exactly the tail the triangulator rejects.

## Query frames and image order

`midpoint` is the default because TAPIR tracks **bidirectionally in time**: one
central query frame reaches both ends of a sequence, which is why
`query_frame_num` is 3 here against `FeatureTrackVGGSfM`'s 5.

`interval` produced *more* tracks (3131 against 2736) and *worse* ones — shorter,
less connected, lower confidence. It reaches the ends of the set, and an endpoint
sees the least.

**Image order matters here and nowhere else in this repository.** TAPIR models a
trajectory over time. If the scene's image order does not match the capture order,
the model is being shown discontinuous motion, and `mostly_occluded` on a
walk-through is the symptom.

## Nothing survives

The error message reports both `mean_confidence` and `mean_occlusion`, and names
which of the two failure modes applies. Follow that rather than lowering the
threshold blindly.

If both look healthy and nothing survived, check the detector produced keypoints
in the chosen query frames — this module tracks what the detector found.

## `min_confidence` is conservative by construction

It thresholds `(1 − σ(occlusion)) · (1 − σ(expected_dist))`, a product of two
probabilities, so both have to be high. 0.5 therefore rejects more than a
single-factor 0.5 would. Dropping it to 0.3 on the reference run gained 65 tracks
and cost 0.02 of `long_track_fraction` — it is not a strong knob, which is a sign
the model's confidence is well separated rather than borderline.

## `dedupe_eps_px`

Same mechanism as `FeatureTrackVGGSfM`'s. It works in **scene pixels**, not
TAPIR's square, so a value carries between the two trackers even though they run
at different resolutions. 0.50 of raw tracks merged on the reference run.

## Reading `trifocal_transfer_px`

The only metric here that measures where the observations are rather than how many
there are, and this module's characteristic weakness is exactly that. Read it
against a chaining tracker's on the same scene: the gap is what predicting rather
than matching costs.

**It is the number that should move when the working resolution does.** Where a
resolution parameter exists it is the one to reach for; where it does not, this
metric is a property of the model rather than a knob.
