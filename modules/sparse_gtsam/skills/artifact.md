---
module: SparseTriangulationGTSAM
module_version: 1.0.0
curated_at: 2026-08-10
---

# Reading a SparseTriangulationGTSAM artifact

## Layout

`sparse_model/v1`: `points` (xyz, rgb, error), `observations`
(frame, point_index, x, y), `poses` (copied through unchanged from the input).

No `intrinsics` file: this module does not refine them, so the scene's calibration
remains authoritative and a consumer reads it from there.

## The poses are copied, not computed

Byte-identical to the `poses/v1` input, including its `valid` array. That is what
makes this module swappable with `SparseTriangulation` — both are pure structure
stages, and comparing two sparse models built from the same poses isolates the
triangulator.

## Observations are UNDISTORTED pixels

The `obs` array holds undistorted coordinates, not the raw pixels the tracker
recorded. That is the convention across this repository: it is what lets a
downstream COLMAP consumer use a PINHOLE camera model, and it is what
`mean_reprojection_error` is measured against.

## Why lower error is not the goal

On DTU this module reports **0.391 px** where the pairwise triangulator reports
**0.365 px**, with 49 more points. Reading that as "worse" is the trap.

The pairwise module triangulates from the widest-baseline pair and then measures
error in every view. LOST fits all views at once, so it lands at a compromise that
is worse in the best-conditioned pair and better overall — and it produces valid
points for tracks whose widest pair alone could not support one. Those extra
points are the harder ones, and they raise the mean.

Judge a triangulator on `point_count` and `median_triangulation_angle` together
with error, never on error alone. Error alone is minimised by keeping only the
easy points.

## Metrics that mislead

**`mean_reprojection_error` is not comparable between models with different
`point_count`.** Same trap as above, and the same one that makes a stalled
reconstruction look accurate.

**`refinement_shift` reads ~0 on healthy data** and that is success, not a broken
metric. It is relative to the scene extent; act on it only when it is large.

**`rejected_distance` is 0 by default** because `max_landmark_distance` is off. A
zero there means the filter did not run, not that nothing escaped.

**`yield` near 1.0** means the filters are barely biting — good on clean data, and
a sign the thresholds are loose if `mean_reprojection_error` is simultaneously
poor.

## What is NOT here

**Per-point provenance.** `track_id` is not written, so a point cannot be traced
back to its `tracks/v1` row. `SparseTriangulation` does write it; if you need that
link, use that module.

**A covariance per point.** GTSAM can produce one and this module does not expose
it. `error` (mean reprojection residual) is the only uncertainty proxy here, and
it is not a substitute — a point with tiny residuals and near-parallel rays has
enormous depth uncertainty and a small `error`.
