---
module: FeatureTrackUnionFind
module_version: 1.0.0
curated_at: 2026-08-07
---

# Tuning FeatureTrackUnionFind

Read this first: **there is very little to tune here, and that is the point.**
Three parameters, two of which you should usually leave alone. Every measurement
below exists to show you which upstream knob to reach for instead.

## `avg_track_length` is not a quality metric

The most important thing on this page.

**Measured, DTU scan1, 12 images sampled uniformly from 49, max_edge 1024, SIFT
at defaults, FeatureMatchNN window 4.** Only the matcher's `ratio_test` changes;
every parameter of this module is at its default:

| matcher ratio_test | matcher inlier_ratio | track_count | avg_track_length | long_track_fraction | inconsistent_rate |
|-------------------:|---------------------:|------------:|-----------------:|--------------------:|------------------:|
| 0.7 | 0.973 | 2763 | 2.42 | 0.265 | 0.0000 |
| 0.8 | 0.905 | 3716 | 2.54 | 0.320 | 0.0003 |
| 0.9 | 0.559 | 4700 | 2.59 | 0.339 | 0.0034 |
| 1.0 (off) | 0.220 | 5662 | 2.68 | 0.368 | **0.0175** |

Every number in the three columns you care about improves monotonically as the
matcher gets worse. More tracks, longer tracks, more of them reaching a third
view — while the matcher's inlier ratio collapses from 0.97 to 0.22.

The extra length is wrong merges. A false match links two distinct scene points,
union-find dutifully fuses their tracks, and the result is a longer track
describing a point that does not exist. `inconsistent_rate` rises 58x across that
sweep, which is the only column telling the truth.

**The rule: `avg_track_length` is only comparable at constant matcher
`inlier_ratio`.** If a change lengthens tracks and lowers inlier ratio, it made
the reconstruction worse. Never tune toward this metric.

---

## `long_track_fraction` below 0.3

Tracks are not reaching a third view. The cause is nearly always the view graph,
because a track can only span frames that were matched to each other.

**Measured, same scene, only the matcher's `window` changing:**

| matcher window | matcher graph_components | track_count | avg_track_length | long_track_fraction | max_track_length | min_frame_observations |
|---------------:|-------------------------:|------------:|-----------------:|--------------------:|-----------------:|-----------------------:|
| 1 | **2** | 2404 | 2.08 | 0.062 | 5 | 19 |
| 2 | **2** | 2987 | 2.23 | 0.164 | 6 | 19 |
| 4 | 1 | 3716 | 2.54 | 0.320 | 9 | 79 |
| 8 | 1 | 3744 | 2.55 | 0.325 | 9 | 94 |

At window 1, `long_track_fraction` is 0.062 — 94% of "tracks" are a single pair
of observations, contributing nothing beyond what the matcher already said.
Raising the matcher's window to 4 takes it to 0.32 and lifts the weakest frame
from 19 observations to 79.

Note that this is a *matcher* sweep appearing in the *tracker's* tuning file. That
is deliberate: it is the correct fix for this module's most common complaint, and
the numbers only exist as tracker metrics.

**Do not respond by raising `min_track_len`.** Setting it to 3 would take
`long_track_fraction` to 1.0 by definition and `track_count` from 2404 to about
150. The metric would look perfect and the reconstruction would have less to work
with than before.

---

## `track_count` below 200

With `long_track_fraction` healthy: the detector is starving you. Raise
`max_keypoints`, or lower `contrast_threshold` if the detector's `saturation` is
near zero (which means the cap was never binding and contrast was).

With `long_track_fraction` also low: fix the view graph first, per above. It
usually fixes both — the window sweep took `track_count` from 2404 to 3716
without touching the detector.

If `min_track_len` was raised above 2, that is the first thing to undo.

---

## `inconsistent_rate` above 0.1

A merged group was observed twice in the same image. One scene point cannot
project to two places in one view, so at least one of the matches that built that
track is wrong.

**This reads upstream, and there is no fix here.** `on_conflict` decides what to
do about the damage, not how to prevent it. Prevention is in the matcher:

- Lower its `ratio_test` toward 0.7. In the sweep above this took
  `inconsistent_rate` from 0.0175 to 0.0000.
- Confirm its `mutual` check is on. Without it, several keypoints in one image can
  match the same keypoint in another, which is a direct mechanism for fusing
  distinct points.
- On repetitive scenes, a learned matcher — see the matcher's limitations.md.

Healthy values on clean data are very small: 0.0003 at ratio_test 0.8, and exactly
0.0000 at 0.7. Treat anything above 0.01 as worth investigating and above 0.1 as
a matcher that needs replacing.

### `on_conflict`

`drop` (default) discards the whole contradictory track. Correct when you care
about the solution: you know one of its matches is wrong and you cannot tell
which, so keeping any of it puts a wrong observation into bundle adjustment.

`first` keeps the earliest observation per frame and salvages the rest. On real
DTU data the two policies are nearly indistinguishable (3744 vs 3748 tracks at
exhaustive pairing) precisely because `inconsistent_rate` is tiny — which is the
condition under which either is fine. Use `first` only when `track_count` is too
low to start reconstruction at all, and treat needing it as evidence about the
matcher.

---

## `min_frame_observations` below 50

One frame is weak, and it will drop out of the reconstruction regardless of the
totals. The artifact names the frame in the `weak_frames` diagnostic.

Check in this order:

1. The detector's `keypoints_min` — if that frame was starved of keypoints, this
   is downstream of a detection problem (blur, underexposure, textureless view).
2. The matcher's `window` — a frame at the end of a sequence has only half as many
   neighbours as one in the middle, and at window 1 that is a single link. The
   sweep above lifted this from 19 to 79 by widening the window alone.

---

## `merge_eps_px` — detector-free input only

Ignored entirely when the matches carry `feature_index`. For dense matchers it
sets the grid used to decide which endpoints are the same feature.

### Measured twice, and the two measurements disagree. Read both.

**First, on DTU SIFT matches with `feature_index` artificially stripped**, to
exercise the proximity path without a detector-free matcher:

| merge_eps_px | track_count | avg_track_length | long_track_fraction | inconsistent_rate |
|-------------:|------------:|-----------------:|--------------------:|------------------:|
| 0.5 | 3277 | 2.62 | 0.349 | 0.0012 |
| 1.5 | 3264 | 2.62 | 0.350 | 0.0018 |
| 4.0 | 2720 | 2.57 | 0.336 | **0.0617** |

0.5 and 1.5 are indistinguishable, and 4.0 starts over-merging: `track_count`
falls 17% while `inconsistent_rate` jumps 34x. That looks like a clean answer —
"stay at 1-2px" — and it is **wrong for real detector-free input**.

**Second, on genuine LoFTR output** (DTU scan1, 5 contiguous images at 640px,
exhaustive pairing, everything downstream identical):

| merge_eps_px | tracks | avg_track_length | long_track_fraction | conflict | registered | final error |
|-------------:|-------:|-----------------:|--------------------:|---------:|-----------:|------------:|
| 1.5 | 3667 | 2.08 | 0.078 | 0.002 | **0.60** | 0.350 |
| 3.0 | 3221 | 2.21 | 0.195 | 0.007 | 0.80 | 0.437 |
| 6.0 | 2528 | 2.32 | **0.286** | 0.059 | 0.80 | 0.508 |
| 12.0 | — | — | — | — | — | reconstruction fails |

At 1.5px — the value the first experiment endorsed, and the predecessor's default —
tracks barely chain past a single pair (`long_track_fraction` 0.078) and **two of
five images cannot be registered at all**.

**Why the two disagree**, which is the thing worth understanding: with a detector,
the same keypoint is *reused* across every pair it appears in, so its coordinates
recur exactly and any tolerance above zero merges them. With a detector-free
matcher every pair is estimated independently, so the same physical point lands at
slightly different sub-pixel positions in each pair it participates in. The
tolerance has to cover that per-pair estimation spread, which is far larger than
the numerical noise the stripped-SIFT experiment was measuring.

The first experiment was a proxy, and the proxy was not measuring the thing that
matters. Recorded rather than deleted, because the failure mode — a synthetic test
that confirms a wrong default — is worth being able to recognise.

**Practical guidance:** start at 3-4px for a ~640px working resolution and scale
with the resize; that is roughly 8-10px at 1600px. Raise until
`long_track_fraction` stops improving, then stop — the cost appears as
`inconsistent_rate` (0.002 → 0.059 across this sweep) and as rising final
reprojection error, and past some point the reconstruction fails outright.

The signature of **over**-merging is fewer tracks and more conflicts at the same
time. **Under**-merging looks like more tracks, shorter, with conflicts unchanged —
which is exactly the 1.5px row above.
