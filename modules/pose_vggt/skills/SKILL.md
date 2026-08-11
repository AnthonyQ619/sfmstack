---
module: PoseVGGT
module_version: 1.0.0
upstream: facebookresearch/vggt @ a288dd0, VGGT-1B checkpoint
curated_at: 2026-08-10
sources: 3
---

Feed-forward camera poses **and intrinsics** from images alone. One transformer
pass over the whole set; no matching, no triangulation, no registration order.
GPU required.

**Use when** correspondences are what is failing — weak texture, repetitive
patterns, wide baselines — or when the scene is uncalibrated. It is what
`PoseEssentialToPnP` names when it refuses an uncalibrated scene.

**Prefer PoseEssentialToPnP when** the scene is calibrated and well textured. On
12 DTU frames, triangulating the same SIFT tracks: VGGT poses give 5899 points at
**1.05 px**, the classical poses give 6900 at **0.365 px**. VGGT is
initialisation-grade; follow it with bundle adjustment when precision matters.

**It fills `poses/v1` and only `poses/v1`.** The same forward pass also produces
point maps and depth; those are `SparseVGGT` and `DenseVGGT`. Three modules, three
passes — so each can be swapped for a classical counterpart independently, which
a combined module could not.

**Read `estimated_focal_ratio` first.** On a calibrated scene it is the estimate
over the calibration, and far from 1.0 means the two disagree — with the poses
computed from the estimate. It is also the metric that caught a real bug in this
module's own preprocessing; see [tuning.md](tuning.md#the-preprocessing-that-was-wrong).

**`mean_reprojection_error` is null by construction.** There are no
correspondences to measure against. A number derived from VGGT's own point maps
would report how self-consistent the network is, not how accurate it is.
Triangulate against these poses and read the triangulator's error.

**Cheapest thing that usually works:** defaults. 12 images in ~20 s on an A6000.

**Reading the output:** [artifact.md](artifact.md).
