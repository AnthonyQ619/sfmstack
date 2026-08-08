---
module: FeatureMatchLoFTR
module_version: 1.0.0
curated_at: 2026-08-08
---

# Tuning FeatureMatchLoFTR

## The first thing to set is not in this module

The tracker's `merge_eps_px`. This module emits no `feature_index`, so the tracker
merges endpoints by proximity, and its default tolerance is wrong for this input.

Measured, DTU scan1, 5 contiguous images at 640px, exhaustive pairing, only the
tracker's tolerance changing:

| `merge_eps_px` | tracks | avg len | long_track% | conflict | registered | final error |
|---:|---:|---:|---:|---:|---:|---:|
| 1.5 | 3667 | 2.08 | 0.078 | 0.002 | **0.60** | 0.350 |
| 3.0 | 3221 | 2.21 | 0.195 | 0.007 | 0.80 | 0.437 |
| 6.0 | 2528 | 2.32 | **0.286** | 0.059 | 0.80 | 0.508 |
| 12.0 | reconstruction fails | | | | | |

Why the default fails here: with a detector, the same keypoint is *reused* in every
pair it appears in, so its coordinates recur exactly. With LoFTR every pair is
estimated independently, so one physical point lands at slightly different
sub-pixel positions in each pair — and the tolerance has to cover that spread.

Raise until `long_track_fraction` stops improving, then stop. The cost shows up as
`inconsistent_rate` and as rising final reprojection error.

## Reference run

Same scene, `setting: outdoor`, `max_matches: 3000`, `min_confidence: 0.2`:

| metric | value |
|---|---|
| `pairs_matched` | 9 of 10 |
| `inlier_ratio` | ~0.8 |
| `graph_components` | 1 |
| `planarity` | 0.331 |
| `mean_match_score` | 0.454 |

Downstream at `merge_eps_px: 3.0`: 4/5 images registered, 2914 points, 0.437px
after bundle adjustment.

## `setting`

Try both before concluding anything. `outdoor` is trained on MegaDepth (buildings,
landmarks, wide baselines); `indoor` on ScanNet (rooms, close range, low texture).
Using the wrong one typically halves the match count with no other symptom, which
makes it easy to misread as a hard scene.

`mean_match_score` is the tell: a low value with a healthy `inlier_ratio` usually
means the wrong model rather than a hard capture.

## `min_confidence` — the quality dial

LoFTR is semi-dense and emits many low-confidence correspondences in ambiguous
regions. Those are exactly the ones that become contradictory tracks, and they
matter more here than with a sparse matcher because proximity merging has no
identity check to fall back on.

Raise toward 0.4-0.5 when the tracker reports `high_conflict_rate`. Lower toward
0.1 only when pairs are failing `min_matches` outright.

## `resize_long_edge` — the cost lever

Attention cost grows with the coarse grid area, so this is the parameter that
actually controls runtime. LoFTR was trained around 640-840px; setting 840 on a
1600px scene is often a large speedup with little accuracy loss.

Coordinates are rescaled back to scene pixels here, so downstream is unaffected —
but detections found at 640px carry 640px localisation precision however they are
rescaled, which will appear as higher reprojection error two stages later.

## `max_matches`

Semi-dense output can reach tens of thousands per pair. The tracker's union-find
and the bundle adjustment both pay for that, for very little gain past a few
thousand well-distributed correspondences. 8000 is generous; 2000-4000 is
reasonable when downstream cost is the problem.

## Cost

The reference run is CPU, because this Docker daemon cannot pass a GPU through.
LoFTR on CPU is not a working configuration for anything real — this module more
than any other here needs the toolkit installed. See `docs/design/DECISIONS.md`.

`exhaustive` on more than ~15 images is a serious cost even on GPU. Raise `window`
first.
