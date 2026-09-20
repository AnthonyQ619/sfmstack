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

## `browse/cloud_views.png` — the one reading that is not a scalar

Three orthographic views of the delivered cloud, side by side in one image, written
whenever `write_cloud_views` is on. Fetch it with
`sfm_artifact_image(<artifact id>, 'browse/cloud_views.png')`.

**Two of the panels look from the plane the cameras occupy. The third looks down that
plane's axis — a direction no input image had.** That third panel is the one worth
spending attention on: a backdrop or support surface fused into the subject, a shell of
stray points standing off the true surface, and a surface reconstructed more than once
in slightly different places all sit *behind* the cloud from every camera and are only
visible from off the ring.

**Why an image is here at all.** Every other reading this module publishes is a single
number, and no single number separates a clean surface from a clean surface wrapped in
floaters. A cloud can carry a healthy point count, a healthy view count and a
plausible confidence while being visibly wrong.

**Read it as a check on the numbers, not as a measurement.** It is framed on the bulk
of the cloud, so points far outside that bulk sit at the frame edge or outside it; a
cloud that looks tidy here can still carry strays the frame does not reach. Nothing in
it is a quantity, and nothing in it should be quoted as one.

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
