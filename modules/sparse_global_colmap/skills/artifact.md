---
module: SparseGlobalCOLMAP
module_version: 1.1.0
curated_at: 2026-08-31
---

# Reading a SparseGlobalCOLMAP artifact

## Layout

`sparse_model/v1`: `points` (xyz, rgb, error), `observations` (frame, point, x, y),
`poses` (cam_from_world, valid, image_index), and `intrinsics` (K, camera_index).
A COLMAP binary model is written as a sidecar under `data/colmap`.

## The poses are this module's own

Unlike `SparseTriangulation`, whose pose block is copied from its `poses/v1`
input, this module estimated them. Nothing upstream produced them and nothing
downstream needs to.

`valid` is not decoration. A camera the global solve could not place is `False`
and its `cam_from_world` row is the identity — a placeholder, not a pose. Every
consumer must honour the flag.

## Why `intrinsics` is written

Bundle adjustment may refine focal length, so the model can disagree with the
scene's calibration. Writing the refined K means a downstream module reads
intrinsics consistent with these poses instead of silently mixing the two.

With both refine flags off it equals the scene's calibration, and writing it
anyway costs nothing and removes a branch from every consumer.

## Colours are read from the pixels

COLMAP samples the images itself. The scene artifact stores resized copies under
`data/images` with sequential filenames, so the module passes COLMAP those paths
rather than the scene's display names — passing display names produces a
uniformly grey cloud with no error anywhere.

## Metrics that mislead

**`mean_reprojection_error` is not comparable across models with different
`registered_images`.** A smaller model is an easier one. Compare it only against a
model with the same camera count.

**`point_count` is not comparable against `SparseTriangulation`'s** without
reading `min_track_len` beside it. This module defaults to 3 and the triangulator
to 2, so the incremental path routinely produces twice the points, most of them
two-view. `mean_track_length` is what tells the two clouds apart.

**`verified_pairs` alone says nothing.** Its meaning is entirely in the gap
between it and the matcher's `pairs_matched`.

**`models_found` of 1 is necessary, not sufficient** — one model containing half
the images is still a split scene, and `registered_fraction` is what reports that.

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

**Per-image residuals.** The metrics are aggregates over the model. The COLMAP
sidecar has per-point error if you need to go deeper.

**A track table.** This module builds tracks internally from the view graph and
does not emit `tracks/v1`; the `observations` array is the multi-view structure
that survived, which is not the same thing.
