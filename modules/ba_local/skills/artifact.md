---
module: BundleAdjustmentLocal
module_version: 1.1.0
produces: sparse_model/v1
curated_at: 2026-08-31
---

# Reading a BundleAdjustmentLocal artifact

## Layout

Identical to [`BundleAdjustmentGlobal`'s](../../ba_global/skills/artifact.md):

```
data/points.npz         xyz, rgb, error, track_id
data/observations.npz   obs [frame_idx, point_index, x, y]
data/poses.npz          cam_from_world, valid, image_index
data/colmap/            cameras.bin, images.bin, points3D.bin  (sidecar)
```

Same type in and out, so it chains — running it repeatedly with different anchors
is a legitimate workflow and each run produces a separate, comparable artifact.

## Poses outside the window are unchanged

Bit-for-bit. They were constants in the solve. So a diff between input and output
poses tells you exactly which cameras the window covered — which is sometimes
easier to check than reading `cameras_refined`.

Points, however, are **not** all unchanged: `refine_points3D` is on, so any point
visible in a refined camera moved, including points also seen by fixed cameras.

## `point_index` is renumbered

Points under `min_track_length` (default 3 here, not 2) are dropped and the rest
renumbered densely from 0. `point_index` in the output does not correspond to
`point_index` in the input; `track_id` is what survives.

Note this means chaining local BA runs progressively discards short-track points at
each step. Two runs at `min_track_length: 3` do not drop more than one does — the
filter is idempotent — but a run at 3 following a run at 2 does.

## The window is not recorded as an array

`cameras_refined` and `cameras_fixed` are counts. Which cameras were in the window
follows from `anchor` and `window_size` in `produced_by.params`, plus the model's
registered set — reproducible, but not directly readable.

If that matters, diffing the input and output pose arrays gives it exactly.

## Metrics that mislead

`reprojection_error_after` is the **whole model**, most of which was deliberately
not optimised. It understates what the module did. `window_error_after` is the one
to judge on: 0.3536 against 0.3842 on the reference run.

`converged` at the default `max_iterations: 50` is frequently 0 with no practical
consequence — the reference solve reached an identical answer converged or not.
Read it together with whether `window_error_after` is where you want it.

`cameras_refined` can be less than `window_size` when the model is small, because
two cameras must stay fixed to pin the gauge.

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

**Measured on the model this module ships, not the one it was handed.** A solve
moves structure, so the input's conditioning is stale as soon as it finishes. This
matters more here than anywhere else in the type: a refined model is normally the
LAST `sparse_model/v1` in a pipeline, so it is what a dense stage reads, and if the
refiners omitted these the questions would have no answer at the point where
something is about to be built on them.
