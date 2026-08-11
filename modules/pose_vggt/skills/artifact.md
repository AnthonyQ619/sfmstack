---
module: PoseVGGT
module_version: 1.0.0
curated_at: 2026-08-10
---

# Reading a PoseVGGT artifact

## Layout

`poses/v1`: `poses` (cam_from_world, valid, image_index) plus an **`intrinsics`**
file (K, camera_index) that the type does not require.

## It writes its own intrinsics

VGGT estimates focal length and principal point along with the pose, and they are
what the poses are consistent with. Writing them means a downstream module reads
intrinsics that agree with these cameras instead of silently mixing VGGT's
geometry with the scene's calibration.

Every consumer here prefers a model's own `intrinsics` over the scene's when both
exist, so this propagates. On a calibrated scene, `estimated_focal_ratio` says how
far the two have diverged before you commit to it.

The file is an additive extension: `poses/v1` does not declare it, consumers that
do not know about it are unaffected, and no new type was needed.

## `valid` is all True, and that is not the same claim

Every image gets a pose because the model poses everything it is shown. `valid`
here means "was in the forward pass", not "was registered against evidence" —
unlike `PoseEssentialToPnP`, where `False` means PnP refused. Do not read a
`registered_fraction` of 1.0 from this module as the same kind of success.

## Nulls that are load-bearing

`mean_reprojection_error` and `median_reprojection_error` are **always null**. Not
missing — measured to be unmeasurable. A consumer sorting pose artifacts by error
must handle the null rather than treating it as zero, which would rank this module
best.

`estimated_focal_ratio` is null only on an uncalibrated scene, where there is
nothing to compare against.

## Metrics that mislead

**`registered_fraction` of 1.0 is uninformative here.** It is 1.0 whenever the
module ran. It carries information for the classical estimator and none for this
one.

**`median_camera_separation` is not accuracy.** It is the scale unit's meaning,
written so a downstream threshold in scene units can be derived rather than
guessed.

**`baseline_span` near 1.0 means uniform spacing**, which a turntable produces.
Near 0 means near-coincident cameras. Neither says anything about correctness.

## What is NOT here

**Point maps and depth.** The same forward pass produces both; they belong to
`SparseVGGT` and `DenseVGGT`. Each runs its own pass — see
`docs/design/target-architecture.md` for why that recompute is accepted.

**Any per-image confidence.** VGGT's camera head emits none this module exposes.
