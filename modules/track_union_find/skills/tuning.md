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

**Measured, a controlled-rig capture, 12 images sampled uniformly from 49, max_edge 1024, SIFT
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

## `inconsistent_rate` above 0.05

A merged group was observed twice in the same image. One scene point cannot
project to two places in one view, so at least one of the matches that built that
track is wrong.

**This reads upstream, and there is no fix here.** `on_conflict` decides what to
do about the damage, not how to prevent it. Prevention is in the matcher, and
**which knob depends on the matcher family** — a point that used to be missing
here and sent three readers to parameters their matcher does not have:

- **Learned matcher (LightGlue, SuperGlue): raise `filter_threshold`.** There is
  no `ratio_test` and no `mutual` on these modules — both are artefacts of
  nearest-neighbour descriptor search, and a joint matcher does not do one. Its
  documented 0.2–0.3 is where to start, not a ceiling: settled values across a
  sweep of captures ran 0.4 to 0.85, and on several the inherited value was
  already inside the old band and still producing a badly contradictory table.
- **Classical matcher (NN, FLANN): lower `ratio_test` toward 0.7, and confirm
  `mutual` is on.** Without mutual, several keypoints in one image can match the
  same keypoint in another, which is a direct mechanism for fusing distinct points.
- On repetitive scenes where neither dial is enough, a different matcher — see the
  matcher's limitations.md.

**Where to stop, which is the part that is easy to get wrong.** This rate keeps
falling long after tightening has begun buying it by deleting the graph. Stop when
the graph starts paying: watch `pairs_matched` against `pairs_proposed`,
`min_image_degree`, and this module's `max_track_length`. On one capture the
threshold that finally cleared the band cost two cross-half pairs and a degree,
with `graph_components` still reading 1 — the completeness metrics do not see it.

**Do not read `inlier_ratio` as evidence that the tightening worked.** It rises
monotonically as you tighten and therefore confirms whatever you just did; across
one sweep it ran 0.906 → 0.975 while the conflict rate was still three times its
ceiling.

**On absolute levels: do not carry them between captures.** A reference run on a
window-4 sequential graph reported 0.0003 at `ratio_test` 0.8; the same nominal
setting on an exhaustive graph over a different subject read 0.0113, thirty-eight
times higher, with nothing wrong. The band (≤0.05, which is also where the
diagnostic fires) is the comparison; another capture's number is not.

### `on_conflict`

`drop` (default) discards the whole contradictory track. Correct when you care
about the solution: you know one of its matches is wrong and you cannot tell
which, so keeping any of it puts a wrong observation into bundle adjustment.

`first` keeps the earliest observation per frame and salvages the rest.

**The two policies cannot be compared on `trifocal_transfer_px`, and the earlier
claim that they are "nearly indistinguishable" was measured on track counts
alone.** Counts do stay close — 3744 vs 3748 on one capture, +55 and +63 on two
others. But the transfer error moved by −27%, +40% and +43% on three captures,
in *both directions*, because `first` changes which tracks exist: it salvages long
tracks, so the held-out sample population is different and the two medians are
over different sets. Neither number is evidence about position.

Keep `drop` on the argument the policy is made of, not on a metric: you know one
observation in that group is wrong and you cannot tell which. Use `first` only
when `track_count` is too low to start reconstruction at all, and treat needing it
as evidence about the matcher.

---

## `min_frame_observations` below 50

One frame is weak, and it will drop out of the reconstruction regardless of the
totals. The artifact names the frame in the `weak_frames` diagnostic.

Check in this order:

1. The detector's `keypoints_min` — if that frame was starved of keypoints, this
   is downstream of a detection problem (blur, underexposure, textureless view).
2. The matcher's pairing. Under `pairing: sequential` a frame at the end of a
   sequence has only half as many neighbours as one in the middle, and at
   `window` 1 that is a single link; the sweep above lifted this from 19 to 79 by
   widening the window alone. **Under `pairing: exhaustive` — which is what a plan
   should already have specified — every pair exists and `window` is inert**, so
   raising it produces a byte-identical artifact. There the frame is thin because
   it genuinely shares little with the rest, and the reading to check is the
   matcher's `min_image_degree` and which pairs on that frame survived.

---

## `merge_eps_px` — detector-free input only

Ignored entirely when the matches carry `feature_index`. For dense matchers it
sets the grid used to decide which endpoints are the same feature.

### Measured twice, and the two measurements disagree. Read both.

**First, on rig-capture SIFT matches with `feature_index` artificially stripped**, to
exercise the proximity path without a detector-free matcher:

| merge_eps_px | track_count | avg_track_length | long_track_fraction | inconsistent_rate |
|-------------:|------------:|-----------------:|--------------------:|------------------:|
| 0.5 | 3277 | 2.62 | 0.349 | 0.0012 |
| 1.5 | 3264 | 2.62 | 0.350 | 0.0018 |
| 4.0 | 2720 | 2.57 | 0.336 | **0.0617** |

0.5 and 1.5 are indistinguishable, and 4.0 starts over-merging: `track_count`
falls 17% while `inconsistent_rate` jumps 34x. That looks like a clean answer —
"stay at 1-2px" — and it is **wrong for real detector-free input**.

**Second, on genuine LoFTR output** (a controlled-rig capture, 5 contiguous images at 640px,
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
with the resize. Raise until `merge_headroom` reaches zero, then stop.

---

## `merge_headroom` above 0.03

`inconsistent_rate` detects **over**-merging and is structurally blind to the
opposite error: splitting one physical point into several tracks produces no
same-frame duplicate and no contradiction of any kind. It cannot see under-merging
at all.

`merge_headroom` is its counterpart. The module rebuilds the tracks at **twice**
`merge_eps_px` and reports how much `long_track_fraction` would rise. Measured on
the two cases above:

| case | eps | `inconsistent_rate` | `merge_headroom` | reading |
|---|---:|---:|---:|---|
| stripped SIFT | 1.5 | 0.004 | **+0.003** | plateau — tolerance is not binding |
| stripped SIFT | 3.0 | 0.030 | −0.017 | past the useful range |
| stripped SIFT | 6.0 | **0.196** | −0.108 | over-merged |
| real LoFTR | 1.5 | 0.002 | **+0.114** | **under-merged** |
| real LoFTR | 3.0 | 0.009 | +0.097 | still under-merged |
| real LoFTR | 6.0 | 0.059 | −0.227 | headroom closed |

Read the two together:

- **near zero on both** — a well-set tolerance.
- **positive headroom** — under-merged. Raise `merge_eps_px`.
- **high `inconsistent_rate`** — over-merged. Lower it.

Note the LoFTR 1.5px row: `inconsistent_rate` is 0.002, an apparently *excellent*
score, on the setting that leaves three of five images unregisterable. That is the
blind spot, and it is why a second metric exists rather than a tighter threshold on
the first one.

Note also the stripped-SIFT 1.5px row: headroom +0.003. Had this metric existed
when that experiment was run, it would have said the experiment contained nothing
to measure.

A cheaper probe on *cluster count* was tried first and discarded: cluster counts
are dominated by endpoints seen in a single pair, which dilutes the signal to
nothing exactly where it is needed. It reported 0.056 on the known-bad LoFTR
setting and fired its diagnostic on the over-merged one instead — precisely
backwards. Measuring the effect on track structure is the only thing that works.

`probe_merge_headroom: false` turns the second pass off. It roughly doubles this
module's runtime, which is negligible next to any matcher.

## Reading `trifocal_transfer_px`

The only metric here that measures where the observations are rather than how many
there are. It should be low for this module and stay low — the observations are the
detector's keypoints and the matcher verified them pairwise — so a value that is
*not* low is a signal about the matcher or the calibration rather than about
chaining.

It cannot be tuned from this module. Nothing here moves an observation; the
positions come from the detector and the merge only decides which ones belong
together.
