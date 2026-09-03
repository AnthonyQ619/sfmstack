---
module: FeatureMatchLoFTR
module_version: 1.7.0
curated_at: 2026-08-08
---

# Tuning FeatureMatchLoFTR

## The first thing to set is not in this module

The tracker's `merge_eps_px`. This module emits no `feature_index`, so the tracker
merges endpoints by proximity, and its default tolerance is wrong for this input.

Measured on a turntable capture of a compact object, 5 contiguous images at 640px, exhaustive pairing, only the
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

**It resizes both ways, and upward is a real lever here — which is not true of the
sparse detectors.** On a heavily-downscaled capture, upsampling roughly 1.5× raised
matches per pair by half, nearly doubled the worst pair in the set, and lifted both
`inlier_ratio` and `mean_match_score`. Every metric moved the right way at once,
which is rare enough to be worth noticing.

The reason it works here and not there: the sparse detectors suppress within a fixed
pixel radius, so stretching the image pushes the same structure past that radius and
costs detections — measured, and the loss orders monotonically by how wide each one's
radius is. LoFTR has no suppression radius, and its coarse grid scales with the
image, so more pixels means more candidate cells rather than more suppression. **Do
not carry a resize conclusion between this module and a detector.**

The cost is real: attention grows with the coarse grid area, so a 1.5× upsample is
well over 2× the compute. Spend it when pairs are thin on a small capture; it is the
one place in this stack where "give the model more pixels" is measured to work.

*Before this module's 1.1.0 this was downscale-only: a value at or above the
scene's own resolution was ignored while provenance recorded it as applied.*

## `max_matches`

Semi-dense output can reach tens of thousands per pair. The tracker's union-find
and the bundle adjustment both pay for that, for very little gain past a few
thousand well-distributed correspondences. 8000 is generous; 2000-4000 is
reasonable when downstream cost is the problem.

## Cost

The reference run is CPU. LoFTR on CPU is not a working configuration for
anything real -- this module more than any other here needs a reachable GPU.

**The recorded timings may not describe your environment.** They were taken when
this stack could not reach a GPU, and GPU passthrough has since been observed
working -- a run of this module has failed with a CUDA out-of-memory error raised
inside the container, which is only possible with a device attached. So treat any
absolute number here as a lower bound on speed and nothing more, and check
`device` in the artifact's own note for what actually ran.

**Read cost as relative, not absolute.** What transfers is the shape: this stage
grows with the pair count, and the pair count grows with the square of the image
count under exhaustive pairing. What does not transfer is seconds on a machine
whose configuration changed under the file. A recorded wall-clock figure is a fact
about a host, and a skill file is the wrong place to keep one.

**The metrics are unaffected either way** -- inference is deterministic and
device-independent; only the timing and the `expected_duration_s` calibration
differ.

`exhaustive` on more than ~15 images is a serious cost even on GPU. Raise `window`
first.

## `inlier_ratio` below 0.4

Semi-dense output has a lower healthy band than a detector-based matcher (0.4
rather than 0.5) because LoFTR proposes correspondences in regions a detector would
have skipped, and some of those are genuinely ambiguous. Below 0.4, in order:

1. **Raise `min_confidence`.** The most direct dial. 0.2 is the usual default; 0.4
   removes most of the tail at a real cost in `matches_per_pair`, which is fine —
   semi-dense output has matches to spare.
2. **Check `planarity`.** A pair whose homography explains as many inliers as its
   fundamental matrix is degenerate, and no matcher setting fixes it.
3. **Check `setting` against the scene.** `outdoor` weights on an indoor scene
   produce confident matches that fail geometry; see the section above.

Do not respond by lowering `ransac_threshold`. In a semi-dense field that mostly
converts a low inlier ratio into a low match count.

## `graph_components` above 1

The view graph is disconnected and no tracker can bridge it — the fix is `window`
or `pairing: exhaustive`, exactly as in the detector-based matchers. What is
specific here is the cost of that fix: `exhaustive` runs the network once per pair,
so going from `window: 3` to `exhaustive` on 20 images is roughly a 30x runtime
increase rather than the 30x cheap-descriptor-comparison increase it would be in
`FeatureMatchNN`. Widen `window` one step at a time and re-read this metric.

A second cause worth ruling out first: `min_matches` dropping marginal pairs. LoFTR
produces thousands of matches on a good pair and can produce a handful on a bad
one, so a threshold tuned for a detector-based matcher may be discarding the very
pairs that would connect the graph.

## Metrics that mislead

`matches_per_pair` has a much higher healthy floor here (200) than for sparse
matchers (100), because semi-dense output is denser by construction. A few hundred
is thin for LoFTR and healthy for SIFT.

`inlier_ratio` runs lower than a sparse matcher's typical value and that is normal —
semi-dense output includes ambiguous regions by design, and geometric verification
is what removes them.

`long_track_fraction` measured downstream will look terrible until the tracker's
`merge_eps_px` is set correctly, and that is a *tracker* configuration problem, not
a matching one. Check it before concluding this module matched badly.
