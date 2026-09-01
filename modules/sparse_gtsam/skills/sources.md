---
module: SparseTriangulationGTSAM
module_version: 1.1.0
curated_at: 2026-08-10
---

# Sources

## LOST: Linear Optimal Sine Triangulation
Sean Henry & John A. Christian, *Absolute Triangulation Algorithms for Space
Exploration*, Journal of Guidance, Control, and Dynamics, 2023.
<https://arxiv.org/abs/2205.12197>

The estimator. Its result is that the standard DLT weights every observation
equally, which is wrong whenever the measurement geometry differs between views;
LOST applies the weighting that makes the linear solution statistically optimal,
so it matches the maximum-likelihood answer without iterating.

Read for: why the improvement is largest with one wide baseline among several
near-coincident views, which is exactly the configuration a turntable or a slow
dolly produces.

## GTSAM
Dellaert et al. <https://gtsam.org/> · `gtsam` 4.2.2 on PyPI

Supplies `triangulatePoint3`, the camera set, and the nonlinear refinement.

API notes verified against 4.2.2:

- The `CameraSet` overload is the one carrying `useLOST`; the `poses + sharedCal`
  overload does not accept it.
- Argument order is `(cameras, measurements, rank_tol, optimize, model, useLOST)`.
  `optimize` and `useLOST` are independent: `useLOST=True, optimize=False` is the
  pure linear LOST solution.
- GTSAM poses are **world_from_cam**; `poses/v1` stores **cam_from_world**. The
  inversion is in `gtsam_camera`, and getting it wrong produces a plausible cloud
  mirrored through the origin.
- Cheirality and rank deficiency raise rather than returning a sentinel, so both
  are caught and counted as rejections.

Measured behaviour of `optimize`, on a synthetic four-view configuration with
1.5 px measurement noise: refinement moves the LOST solution by 0.0013 scene
units and the DLT solution by 0.00004, converging to nearly the same point. So the
flag does work; on well-conditioned data it simply has little to do.

## The predecessor
`scene_agent/breadth_agent/src/sfmcore/scenereconstruction.py`,
`Sparse3DReconstructionIncremental._triangulate_lost` and
`_check_landmark_distance`.

Same estimator and the same far-landmark rejection. Differences: there it was one
method inside a class that also estimated poses, maintained tracks and ran bundle
adjustment, with `use_lost`, `optimize` and `rank_tol` hardcoded as locals marked
"vars to add if this is successful". Here they are parameters, the rejections are
counted and reported, and the module does one thing.

## Multiple View Geometry, §12
Hartley & Zisserman.

Background on why the DLT minimises an algebraic rather than a geometric error,
which is the gap LOST closes for the linear case and `optimize` closes by
iterating.
