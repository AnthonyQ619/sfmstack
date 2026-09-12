---
module: BundleAdjustmentLocal
module_version: 1.2.0
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
