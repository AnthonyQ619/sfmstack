---
module: DenseFusion
module_version: 1.1.0
curated_at: 2026-09-16
---

# Reading a DenseFusion artifact

## Layout

`dense_model/v1`: `points` (xyz, rgb), and a `ply/cloud.ply` sidecar when
`write_ply` is on — the same name and writer `DenseMVS` and `DenseVGGT` use, so
whatever opened the original cloud opens this one. No `depth` file, no
`confidence` file, and no `workspace` sidecar — see
[limitations](limitations.md#its-output-cannot-be-re-fused).

## Same frame, same scale as the stereo pass

Fusion places points using the cameras the stereo pass ran with, so the cloud sits
in the sparse model's frame and scale exactly as the input's did. Two settings fused
from one workspace can be compared point for point.

## Telling settings apart

`fusion_min_num_pixels` records the setting on the artifact itself, so a set of
outputs from one workspace can be sorted without reading their lineage.
`point_ratio_to_source` is `point_count` over the input's; read it across the
set in order of the setting, as [tuning](tuning.md#stepping-down-and-when-to-stop)
describes.

## Reproducing the input

Re-fusing at the setting the stereo pass was delivered with returns the delivered
cloud. If it does not, the workspace was altered or the tolerances differ from the
producing run's — check `max_reproj_error`, `max_depth_error` and
`max_normal_error` against the `DenseMVS` step's `fusion_*` parameters.
