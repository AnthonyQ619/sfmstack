---
module: PoseEssentialToPnP
module_version: 1.0.0
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
