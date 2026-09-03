---
module: PoseEssentialToPnP
module_version: 1.2.0
curated_at: 2026-08-07
---

# Sources

## The incremental strategy

**Schönberger and Frahm, "Structure-from-Motion Revisited", CVPR 2016** (COLMAP),
sections 4.2-4.4. The order implemented here — seed selection, next-best-view
registration, triangulation, filtering — is theirs.

Two of their contributions are implemented and one is not:

- **Next-best-view by correspondence count.** Implemented. COLMAP's actual scoring
  is richer: it also rewards correspondences *spread across* the image, to avoid
  registering against a cluster in one corner. Ours counts only. Worth upgrading if
  `registered_fraction` is high while `mean_reprojection_error` is poor.
- **Triangulation filtering on angle and reprojection error.** Implemented.
- **Retriangulation and interleaved global refinement.** Not implemented. COLMAP
  alternates BA with re-triangulation of previously failed tracks; we do one
  forward pass and leave refinement to `BundleAdjustmentGlobal`.

## Seed pair selection

The failure mode — the pair with the most matches is usually the pair with the
least baseline — is standard knowledge. **Snavely, Seitz, Szeliski, "Photo
Tourism", SIGGRAPH 2006**, section 4.2 states the requirement as a pair with many
matches *and* a baseline wide enough that a homography does not explain them.

Ours scores `inlier_count × median_parallax` with a hard floor on parallax. Photo
Tourism's criterion (homography inlier fraction) is arguably better and is already
computed one stage upstream as the matcher's `planarity` metric — using it here
would mean consuming `pairwise_matches` as well as `tracks`, a coupling worth
avoiding until it proves necessary.

Observed on DTU scan1, 12 contiguous images: seeds on images **0 and 8** at 25°
median parallax rather than on the adjacent pair. That is the criterion working.

## PnP

`cv2.SOLVEPNP_SQPNP` — **Terzakis and Lourakis, "A Consistently Fast and Globally
Optimal Solution to the Perspective-n-Point Problem", ECCV 2020.**

Chosen over the older EPnP/iterative default because it is globally optimal and
needs no initial guess, which matters when registering an image whose registered
neighbours are far away. Followed by `solvePnPRefineLM` on the inlier set.

The predecessor used the default flags with `iteration_count=200`; we use 10000
RANSAC iterations, because they are cheap relative to the triangulation sweep and
200 is low for the outlier rates real tracks carry.

## Essential matrix

`cv2.USAC_MAGSAC` (**Barath et al., CVPR 2020**), the same estimator the matcher
uses, applied in normalised coordinates with `K = I`. Working in normalised
coordinates is what lets per-image intrinsics differ within one scene.

## Predecessor code

`scene_agent/breadth_agent/src/sfmcore/camerapose.py`,
`CamPoseEstimatorEssentialToPnP` (lines 313-700), plus helper methods on
`CameraPoseEstimatorClass` in `baseclass.py`.

Deliberately not carried over:

- **`init_pair_idx = 0`.** Hardcoded, with an unreachable `if init_pair_idx is
  None` guard immediately below it and a printed warning about the class "currently
  growing forward from that pair".
- **Pairwise track chaining.** It rebuilt tracks from consecutive pairs inside the
  pose estimator; we consume `tracks/v1`.
- **The nested `optimizer` parameter.** It took a `BundleAdjustmentOptimizerLocal`
  *instance* as a constructor argument, making one module's behaviour a function of
  another module's object.

Two bugs in the predecessor's `triangulate_track_best_pair` are why that routine
was reimplemented rather than ported: it references undefined names `kp1` and
`kp2` and would raise `NameError` if reached, and its baseline-scoring loop
(`range(a + 1, len(obs_list) - 1)`) skips the last observation.

## What is asserted without a source

Audited 2026-09-02 against this module's own manifest.

- **Healthy bands with nothing behind them.** `registered_images`, `points_triangulated`, `median_triangulation_angle`, `track_utilization`, `init_pair_angle` declare a range and no diagnostic on this module reads them. A band with no diagnostic is a description of the captures measured so far, not a judgement on yours -- and a corpus maximum is the largest of N draws, so the next capture exceeding it is expected rather than anomalous.
- **Numeric tuning advice with no citation in this file.** `min_triangulation_angle_deg`, `max_reprojection_error`, `min_pnp_inliers`, `min_track_len`, `local_ba_window`, `local_ba_interval`, and 1 more name specific values in their tuning prose. The reasoning behind them may be sound; the numbers are settings that worked here, not results anyone has published.
- **Scope of the measurements.** What is written here was exercised across 109 runs of this module in a seventeen-capture sweep of benchmark captures, at version 1.2.0. That is the whole evidence base: no capture outside those two benchmark families has been run through it.

## Review triggers

Re-read and re-check this file when any of these happens:

- **This module's version changes from 1.2.0.** These notes were written against it; a metric set or a published band can change with a version and the prose does not follow automatically.
- **A capture unlike the benchmark families appears.** Every band here was fitted on controlled-rig and field captures from two benchmark datasets. Per-frame appearance readings transfer to a larger capture; adjacent-motion readings and anything denominated in pairs do not.
- **A reading crosses one of `registered_images`, `points_triangulated`, `median_triangulation_angle`, and 2 more and nothing fires.** That is this file's known gap, not a defect in the capture -- but it is the signal that the band deserves either a diagnostic or a wider range.
