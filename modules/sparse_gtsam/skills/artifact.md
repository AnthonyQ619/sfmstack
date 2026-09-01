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

## The four readings that see what the means hide

Every producer of `sparse_model/v1` publishes these, so they are comparable across
modules in a way a module's own metrics are not. Each exists because a scalar the
type already published was concealing something:

- **`min_frame_points`** — the emptiest registered camera. `registered_images`
  counts a camera holding almost no structure exactly like a well-covered one, and
  a whole-model `point_count` cannot be moved by one starved view. This is the
  reading that predicts a view failing downstream while every headline looks fine.
- **`two_view_fraction`** — the share of points seen in exactly two views. Those
  are exactly determined, four residuals against three unknowns, so their residual
  is near zero *by construction* rather than because they are good. On a
  two-view-dominated cloud they drag the mean down and the model reads better than
  it is.
- **`p95_reprojection_error`** — separates a uniformly mediocre model from a good
  model carrying a few bad points. The two want opposite responses, and the mean
  cannot tell them apart.
- **`p05_triangulation_angle`** — the weak end of the parallax distribution. A
  point on near-parallel rays sits at an ill-determined depth while reprojecting
  beautifully into the views that placed it, so it is invisible to every
  reprojection metric, and a median cannot see a tail. Where this reading is low,
  the cloud's SHAPE is uncertain in a way its error does not report.

`mean_reprojection_error` here is the **per-point** mean. It is worth knowing why
that is stated: producers of this type once published three different populations
under the one name — points, observations, and a frame that was not published at
all — and the spread was wide enough to invert a head-to-head comparison. An
observation mean weights long tracks, and long tracks are the higher-error points.

**Take them before choosing what comes next.** They describe the artifact rather
than the process that made it, so they are the honest basis for comparing this
module's output against another producer's — which the module-specific metrics,
measuring different things under similar names, are not.

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
