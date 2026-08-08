---
module: PoseEssentialToPnP
module_version: 1.0.0
upstream: OpenCV essential matrix + SQPnP, the COLMAP incremental strategy
curated_at: 2026-08-07
sources: 4
---

Incremental structure-from-motion: seed on a well-conditioned pair, then
repeatedly register whichever image has the most 2D-3D correspondences.
CPU-only, deterministic given fixed RANSAC seeds, no weights.

**Use when** the scene is calibrated and the tracks are healthy. It is the
classical baseline and the only pose estimator here that needs nothing but
OpenCV.

**Prefer something else when** the scene is uncalibrated (VGGT and MapAnything
estimate intrinsics and do *better* without a supplied K), or when the capture is
degenerate — planar, pure rotation, or too sparsely sampled to have parallax. See
[limitations](limitations.md).

**It consumes `tracks/v1`, not pairs.** That is the main departure from the
predecessor and it changes the failure mode: this module cannot be run without a
tracker, but a single unregisterable frame no longer truncates everything after
it. It gets `valid=False` and the run continues.

**Scale is arbitrary and unrecoverable.** The seed pair's baseline is fixed to
unit length, so every distance downstream is in that unit. Nothing in an image-only
pipeline can fix this; it needs a known length in the scene or metric depth.

**The two metrics that matter most, in order:**

1. `registered_fraction` — below 1.0, some images have no pose. Consumers must
   honour the `valid` array; `poses/v1` makes it mandatory for exactly this reason.
2. `median_triangulation_angle` — low means the structure is poorly conditioned in
   depth *even when reprojection error looks fine*. The two genuinely disagree,
   and this one is the more honest.

**Cheapest thing that usually works:** defaults. On DTU scan1 (12 contiguous
images, SIFT + exhaustive NN matching) that gives 12/12 registered, 6893 points,
0.44px mean reprojection error and 15.5° median parallax in 2 seconds.

**Reading the output:** [artifact.md](artifact.md). This module does not refine
globally — run [BundleAdjustmentGlobal](../../ba_global/skills/SKILL.md) after it.
