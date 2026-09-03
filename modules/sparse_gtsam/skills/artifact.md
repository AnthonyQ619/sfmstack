---
module: SparseTriangulationGTSAM
module_version: 1.1.0
curated_at: 2026-08-31
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

On the small-object arc above this module reports **0.391 px** where the pairwise
triangulator reports
**0.365 px**, with 49 more points. Reading that as "worse" is the trap.

The pairwise module triangulates from the widest-baseline pair and then measures
error in every view. LOST fits all views at once, so it lands at a compromise that
is worse in the best-conditioned pair and better overall — and it produces valid
points for tracks whose widest pair alone could not support one. Those extra
points are the harder ones, and they raise the mean.

Judge a triangulator on `point_count` and `median_triangulation_angle` together
with error, never on error alone. Error alone is minimised by keeping only the
easy points.

## What is NOT here

**Correction: `track_id` IS written.** This section used to say it was not, and
that a reader needing per-point provenance should use `SparseTriangulation`
instead. The `points` group carries `track_id` and has for some time — check the
artifact's own `files` block. The claim was wrong in the worst possible direction,
because pairing on `track_id` is exactly what this module's `tuning.md` instructs a
reader to do before comparing the two triangulators, and believing this paragraph
would have sent them away from the module to get a field it already ships.

**A covariance per point.** GTSAM can produce one and this module does not expose
it. `error` (mean reprojection residual) is the only uncertainty proxy here, and
it is not a substitute — a point with tiny residuals and near-parallel rays has
enormous depth uncertainty and a small `error`.
