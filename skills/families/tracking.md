# Feature tracking — choosing a tracker

Everything that produces `tracks/v1`. Three modules, and they sit at three points
on **one** trade.

---

## The trade

**Track length and positional precision move in opposite directions, and the same
property drives both.**

A **chaining** tracker (`FeatureTrackUnionFind`) builds tracks from verified
two-view matches. A track can only be as long as the view graph's connectivity
allows — it dies at every missing edge — and its observations are *detected*
keypoints in every frame, so they carry the detector's sub-pixel accuracy.

A **predictive** tracker (`FeatureTrackVGGSfM`, `FeatureTrackTapir`) is given
keypoints in a few query frames and predicts where they land everywhere else.
Nothing truncates the track, because there is no view graph to have a hole in. But
the observations are predictions, and every such model runs at reduced resolution,
so the positional error has a floor set by the resampling before the model
contributes any of its own.

```
                    reach                              precision
  chaining          bounded by the view graph          detector sub-pixel
  predictive        bounded by nothing                 bounded by model resolution
```

The ordering is not a coincidence of one dataset. Predicting rather than matching
buys reach and costs precision, and the further a model runs from the image's
native resolution the more of both you get.

---

## Measured — DTU scan1, 8 images at 1024 px

One scene. Same SIFT keypoints into all three; same `PoseEssentialToPnP` and
`SparseTriangulation` behind all three.

| tracker | `avg_track_length` | `long_track_fraction` | `track_survival_5` |
| --- | ---: | ---: | ---: |
| `FeatureTrackUnionFind` | 2.85 | 0.431 | 0.116 |
| `FeatureTrackVGGSfM` | 3.85 | 0.712 | 0.345 |
| `FeatureTrackTapir` | **5.98** | **0.927** | **0.754** |

| tracker | triangulated points | mean error | `yield` |
| --- | ---: | ---: | ---: |
| `FeatureTrackUnionFind` | 4671 | **0.280 px** | 0.993 |
| `FeatureTrackVGGSfM` | 3982 | 0.502 px | 0.987 |
| `FeatureTrackTapir` | 1548 | 1.581 px | 0.566 |

Monotonic, with no crossover on any column.

---

## What this means for reading a `tracks/v1` artifact

**No metric in the type measures the precision axis.** Every one of them —
`track_count`, `avg_track_length`, `long_track_fraction`, `min_frame_observations`,
`frames_covered`, `inconsistent_rate`, `split_rate`, the survival curve — is about
length, coverage or self-consistency. A tracker can look excellent on all of them
and be four pixels off everywhere.

**The first number that sees it is downstream**: the triangulator's
`mean_reprojection_error`, and more usefully its `yield`, which is the fraction of
tracks that survived the geometric filters. Comparing trackers means reading past
the tracker.

---

## Which end to reach for

**Reach for chaining when the matcher works.** A calibrated, well-textured,
sufficiently overlapped capture — the matcher will verify most pairs, the view
graph will be one component, and nothing else here will beat detected keypoints
for precision. Signals: the matcher's `graph_components` is 1,
`largest_component_fraction` is near 1, `inlier_ratio` is high.

**Reach for predictive when the view graph fragments.** Signals from the matcher:
`graph_components` above 1, a low `largest_component_fraction`, or a
`min_matches_per_pair` that collapses on part of the set. Those tracks are short
because they were *cut off*, and a predictive tracker predicts through the gap. Its
lower precision costs less than structure that does not exist.

**Between the two predictive trackers**, the difference is provenance rather than
degree. VGGSfM's tracker comes from an SfM model and has no notion of image order.
TAPIR comes from video and **image order is genuine input** — a shuffled or
unordered collection is a different and harder problem than the one it was trained
on, and `mostly_occluded` on a capture that should be continuous is the symptom.
On an ordered capture TAPIR reaches furthest; on an unordered one, prefer VGGSfM.

---

## What has NOT been measured

**The case the predictive trackers exist for.** Every number above is DTU:
calibrated, well-textured, sequential, turntable — the case chaining is *best* at.
The table says what the predictive trackers cost where the matcher already works.

It does not say what they buy where it does not. On a scene whose view graph
fragments, `FeatureTrackUnionFind`'s tracks would be short for a reason the table
above cannot show, and the ordering on `yield` could compress or invert. That
experiment needs a textureless or weakly-overlapped scene and has not been run.

**Treat the ordering as established and the magnitudes as one data point.**

---

## Related

- Per-module detail: `FeatureTrackUnionFind`, `FeatureTrackVGGSfM`,
  `FeatureTrackTapir` — each module's `SKILL.md` and `tuning.md`.
- The full experiment, with the parameter sweeps behind it:
  [`docs/import_lessons.md`](../../docs/import_lessons.md).
- Why `inconsistent_rate` and `split_rate` are duals, and why one of them is
  structurally zero for the predictive trackers:
  [`docs/module-contract.md`](../../docs/module-contract.md#feature-tracking).
