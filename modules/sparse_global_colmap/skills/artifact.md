---
module: SparseGlobalCOLMAP
module_version: 1.1.0
curated_at: 2026-08-10
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

## What is NOT here

**Per-image residuals.** The metrics are aggregates over the model. The COLMAP
sidecar has per-point error if you need to go deeper.

**A track table.** This module builds tracks internally from the view graph and
does not emit `tracks/v1`; the `observations` array is the multi-view structure
that survived, which is not the same thing.
