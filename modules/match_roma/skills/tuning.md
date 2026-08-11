---
module: FeatureMatchRoMa
module_version: 1.0.0
curated_at: 2026-08-10
---

# Tuning FeatureMatchRoMa

The first thing to set is not in this module: the TRACKER's `merge_eps_px`.
Detector-free output cannot chain into tracks without it, and no setting here
compensates. See [limitations.md](limitations.md#no-feature_index).

Then, in order: `graph_components`, `inlier_ratio`, `mean_certainty`,
`matches_per_pair`.

## Reference run

DTU scan1, 8 contiguous images, `max_edge: 1024`, `pairing: sequential`,
`window: 2`, `setting: outdoor`, GPU, in a container:

| metric | value |
|---|---|
| `pairs_matched` | 13 |
| `matches_per_pair` | 4951.8 |
| `min_matches_per_pair` | 4710 |
| `inlier_ratio` | 0.99 |
| `mean_certainty` | 0.997 |
| `planarity` | 0.419 |
| runtime | 19.8 s |

Downstream, through `FeatureTrackUnionFind` at `merge_eps_px: 4.0` and
`PoseEssentialToPnP`: 13195 tracks, 8/8 images registered, 0.33 px.

**Note what that same run says about the tracker:** `inconsistent_rate` 0.20 and
`merge_headroom` −0.21. Both say 4 px is past the useful tolerance for RoMa at
1024 px — the dense field is precise enough that a narrower merge works, unlike
LoFTR where 1.5 px was too tight. The reconstruction succeeded anyway, which is
exactly why the conflict rate is worth reading rather than only the final error.
Try 2–3 px here.

## Nothing matched

1. **`min_certainty` to 0.** It removes correspondences before geometry ever sees
   them, so it is the first suspect whenever the count is the problem.
2. **`min_matches`.** RoMa produces thousands on a good pair and very few on a bad
   one; a floor tuned for a sparse matcher discards exactly the marginal pairs
   that would connect the graph.
3. **The other `setting`.** Outdoor is MegaDepth, indoor is ScanNet — different
   training data, not different tuning.

## `inlier_ratio` below 0.4

The band is lower than the sparse matchers' on purpose: RoMa proposes
correspondences in regions a detector would skip, and some are genuinely
ambiguous. Below 0.4:

1. **Raise `min_certainty`** to 0.5–0.7. The certainty is a calibrated uncertainty
   estimate, not a matching score, so this trades count for precision cleanly.
   Watch `certainty_floor_effect`: a large fraction removed with an unchanged
   inlier ratio means the floor is discarding correspondences that were fine.
2. **Check `planarity`.** Near 1.0 the pair is degenerate and verification is
   correct to reject it.
3. **Check the `setting`.**

Do NOT tighten `ransac_threshold` below 2 px. In a dense field that converts a low
inlier ratio into a low match count and hides the cause.

## `graph_components` above 1

Raise `window`. The cost note matters more here than anywhere else: each added
pair is a full dense forward pass, so `window: 1 → 3` roughly triples the runtime,
and `pairing: exhaustive` on 20 images is 190 dense matches. Raise one step at a
time and re-read the metric.

## `max_matches` is nearly free — upstream

It samples an ALREADY COMPUTED field, so raising it does not cost matching time.
It costs downstream: the tracker's union-find and bundle adjustment both pay per
correspondence, and at 5000 per pair a 20-image exhaustive run is a million
correspondences. Sampling is certainty-weighted, so the first 2000 are better than
a random 2000 — lower it when the tracker is the bottleneck.

## `use_custom_corr`

Leave off unless the compiled `local_corr` extension is present in the image. It
is not a pip dependency and pip will not tell you: `roma_outdoor(...)` constructs
successfully and the first forward pass raises `ModuleNotFoundError`. Turning it
on therefore fails a JOB, not a build — which is the worst place to find out.

The fallback is numerically equivalent. The authors quote a substantial speedup
for the kernel; building it into the base image is the obvious next optimisation
and has not been done.

## Cost

19.8 s for 13 pairs at 1024 px on an A6000, with the pure-torch correlation.
Roughly 1.5 s per pair, independent of `max_matches`. Several times LoFTR's cost
for the same pairs. CPU is not a working configuration.
