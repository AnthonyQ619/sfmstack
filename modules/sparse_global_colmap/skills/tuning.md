---
module: SparseGlobalCOLMAP
module_version: 1.1.0
curated_at: 2026-08-10
---

# Tuning SparseGlobalCOLMAP

Work outward from the view graph. Almost everything that goes wrong here went
wrong in the matcher, and this module's own parameters mostly decide how much of
that damage it lets through.

1. `verified_pairs` — against the matcher's `pairs_matched`.
2. `largest_component_fraction` and `registered_fraction`.
3. `mean_reprojection_error` and `mean_track_length`.
4. Only then `ba_num_iterations` and the refine flags.

## Reference run

One capture: a short contiguous arc of twelve calibrated frames around a small,
well-textured object on a plain backdrop, at about 1 MP, classical detector at
defaults, ratio-test matcher at `pairing: exhaustive`, everything here at defaults.

| metric | value |
|---|---|
| `verified_pairs` | 63 of 64 attempted |
| `registered_fraction` | 1.0 (12/12) |
| `point_count` | 3608 |
| `observation_count` | 16335 |
| `mean_track_length` | 4.53 |
| `mean_reprojection_error` | 0.316 px |
| `models_found` | 1 |
| runtime | 4.5 s |

For contrast, the incremental chain on the same input needs
`PoseEssentialToPnP` + `SparseTriangulation` + `BundleAdjustmentGlobal` to reach
0.25 px. Global gets to 0.32 px in one module and a fraction of the time, with a
cloud roughly half the size — it triangulates only tracks reaching
`min_track_len` views, where the incremental path keeps two-view points.

## `verified_pairs` is zero

Nothing entered the view graph, so there was nothing to average. In order:

1. **`max_epipolar_error` is in WORKING-resolution pixels.** This is the usual
   cause. 1.0 px is tight; on a scene downscaled to `max_edge: 640` real
   correspondences land further off the epipolar line than that. Try 2–4.
2. **`min_num_matches` (30) against the matcher's `min_matches_per_pair`.** If the
   matcher's weakest pair is below 30, those pairs never reach verification.
3. **`min_inlier_ratio` (0.25)** last. Lower it only when the matcher's own
   `inlier_ratio` is genuinely low, and expect worse rotations if you do.

## `verified_pairs` far below `pairs_matched`

The module rejected a large share of what the matcher produced. That is often
correct — verification here is stricter than the matcher's — but check which:

- **The matcher's `planarity` near 1.0 on many pairs.** Those pairs are planar or
  rotation-only and *should* fail. Nothing to fix here.
- **A heavily downscaled scene.** Raise `max_epipolar_error`.
- **`inlier_ratio` healthy and `planarity` low, yet pairs still dropped.** Raise
  `max_epipolar_error` one step and watch `mean_reprojection_error`: if error
  stays flat while `verified_pairs` rises, the threshold was too tight.

## `registered_fraction` below 1.0

There is no `min_pnp_inliers` to relax here. The camera was not placed because
the graph could not place it.

1. **`largest_component_fraction`.** Below 1.0, the graph is split and no
   parameter in this module can join it — widen the matcher's `window` or use
   `pairing: exhaustive`.
2. **`models_found` above 1.** Same cause, seen from the other side: the pipeline
   built several reconstructions and only the largest is returned.
3. **`min_num_matches`** last. Lowering it admits thin pairs, which may connect a
   stray image at the cost of a worse rotation everywhere.

## `mean_reprojection_error` above 2

1. **`ba_num_iterations`** 3 → 5 or 6. These are pipeline rounds, not Ceres
   iterations: each re-triangulates and re-filters between solves, so raising it
   does more than letting one solve run longer.
2. **Raise `min_num_matches`** toward 60–100. A thin pair contributes a badly
   conditioned relative rotation, and rotation averaging spreads that error over
   the whole graph rather than confining it to one image. This is the lever with
   no equivalent in incremental SfM.
3. **`min_tri_angle_deg`** 1.0 → 2–3 if the cloud looks stretched in depth while
   the error looks fine.

## `mean_track_length` near `min_track_len`

Nothing chained beyond the floor. The view graph is the constraint, not this
module — widen the matcher's `window`. Lowering `min_track_len` to 2 raises
`point_count` and lowers this metric further; it does not add information.

## The refine flags

`refine_focal_length` off when the scene carries real calibration. On when the
intrinsics came from an EXIF guess — and then compare the `intrinsics` file in the
output against what you supplied before trusting anything metric.

`refine_principal_point` stays off. The principal point is weakly observable and
refining it absorbs error that belongs to the pose: reprojection error improves
while the reconstruction gets worse, which is the most misleading failure mode
available in this module.

## Cost

4.5 s for 12 images and 64 pairs. Cost grows with the number of VERIFIED PAIRS,
not with the image count, so the matcher's `pairing` dominates: exhaustive on 100
images is 4950 pairs and a different order of magnitude. This is still the cheap
option — the same set through incremental registration pays a bundle adjustment
per handful of images.
