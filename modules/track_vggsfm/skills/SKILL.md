---
module: FeatureTrackVGGSfM
module_version: 1.5.0
upstream: VGGSfM v2 tracker, via facebookresearch/vggt @ a288dd0 (vendored)
curated_at: 2026-08-11
sources: 3
---

Learned multi-view tracking. Keypoints from a few selected query frames are
propagated to every other frame in one forward pass. GPU required.

**It consumes `features/v1`, not `pairwise_matches/v1`.** No matcher runs — the
chain is scene → detect → track, three stages instead of four.

## Why reach for it: longer tracks

8 DTU views, SIFT keypoints, everything downstream identical:

| | tracks | `avg_track_length` | `long_track_fraction` | `track_survival_5` |
|---|---:|---:|---:|---:|
| `FeatureTrackUnionFind` | 4702 | 2.85 | 0.431 | 0.116 |
| **`FeatureTrackVGGSfM`** | 4033 | **3.85** | **0.712** | **0.345** |

**Three times as many tracks reach five views.** A matcher's track dies at every
missing view-graph edge; this predicts through the gap. That is the whole reason
the module exists, and `track_survival_5` is where it shows up — not in
`track_count`, which is lower.

## Why not: less precise positions

Same tracks through `PoseEssentialToPnP` and `SparseTriangulation`:

| tracker | registered | pose error | points | tri error | `yield` |
|---|---:|---:|---:|---:|---:|
| `FeatureTrackUnionFind` | 8/8 | 0.291 px | 4671 | **0.280 px** | 0.993 |
| `FeatureTrackVGGSfM` | 8/8 | 0.465 px | 3982 | 0.502 px | 0.987 |

A matched keypoint sits where the detector put it in *both* frames; a tracked one
sits where the network predicts. On a calibrated, well-textured scene where the
matcher works, that costs about 0.2 px. Length is the trade against precision.

## Query frames are the whole game

| selection | frames | `mean_visibility` | `avg_track_length` | `track_survival_5` | time |
|---|---|---:|---:|---:|---:|
| `dino`, 5 | [dino-ranked] | 0.348 | 3.85 | 0.345 | 17 s |
| `midpoint`, 3 | 3, 4, 5 | 0.350 | 3.71 | 0.311 | **5 s** |
| `interval`, 5 | 1, 2, 4, 6, 7 | 0.231 | 2.60 | 0.033 | 9 s |

`interval` reaches the ends of the set and pays for it. **An endpoint of a
sequential capture sees the least of the scene** — tracking from frame 0 of this
set leaves each point visible in 1.77 frames against 4.40 from frame 4. The
predecessor forced frame 0 into every query set; this does not.

`midpoint` with three query frames matched `dino` with five at a third of the
runtime. Try it before raising `query_frame_num`.

## Two things about the metrics

**`inconsistent_rate` is structurally zero here.** Each query point yields at most
one position per frame, so a track cannot contradict itself. It is reported
because the type requires it and it carries no information about this module.

**`duplicate_track_rate` is the metric that does.** 0.45 on the reference run —
deduplication merged 7329 raw tracks down to 4033. That is redundancy, not error:
five query frames re-find each other's points. The predecessor shipped all 7329,
so a well-seen point entered bundle adjustment up to five times.

## `dedupe_eps_px` is the one knob here worth sweeping — and it has a hard ceiling

**Bounded at 2.0 by the schema.** `tracks/v1` fixes its duplicate test at 2.0 px, so
above that the merge is fusing tracks the type itself calls **distinct**. Nine scenes
say what that costs: by 6.0 px the median run has lost 74% of its tracks and 81% of
its bundle-adjusted points at unchanged registration, and the errors that look
better up there are smaller models, not better ones.

**Inside 0–2 it moves the reconstruction and cannot be predicted.** The best value
landed at every point on that range across nine scenes, and the direction flips —
on one scene more merging helped monotonically, on another any merging cost ~60% of
the pose accuracy. Worth a sweep when the scene matters; worth leaving at 1.5 when
it does not.

**Never compare sweep rows that registered different numbers of images.** Raising
this deletes tracks, which removes the 2D–3D links PnP needs to register an image
at all. A smaller model wins every aggregate metric it is scored on.

Full numbers and the failure at 0: [tuning.md](tuning.md#dedupe_eps_px--worth-tuning-inside-a-hard-ceiling).

**Reading the output:** [artifact.md](artifact.md) ·
**Tuning:** [tuning.md](tuning.md) · **Limits:** [limitations.md](limitations.md)
