---
module: PoseMapAnything
module_version: 1.0.0
curated_at: 2026-09-25
---

# What comes out

A `poses/v1` artifact: `cam_from_world` (3×4, OpenCV convention), `valid`, and
`image_index`, one row per image in the scene.

## The frame and the scale are its own

`camera_poses` comes back camera-to-world in MapAnything's world frame at
MapAnything's scale, and is inverted here to the cam-from-world the type declares.

**Nothing about this is metric.** `is_metric_scale` is never asserted, and the
scale unit means whatever the network decided it means for this scene. Anything
downstream that takes a *distance* — notably `SparseTriangulationGTSAM`'s
`max_landmark_distance` — has to be told what the unit is, and
`median_camera_separation` is the metric that says so. It is not an accuracy
reading; it is a unit conversion.

This is also why a comparison against another model must be made **by a similarity
fit**, never by differencing coordinates. Two correct answers in different frames at
different scales differ everywhere.

## It writes its own intrinsics

`poses/v1` declares no intrinsics file, so the estimate is saved as a sidecar array
under the same slot, which the additive-extension rule allows — the same thing
`PoseVGGT` does, for the same reason.

Intrinsics are recovered per view in the model's preprocessed frame and mapped back
to the scene's working resolution. `preprocess_inputs` resizes uniformly and
centre-crops, which is affine, so the model's own returned `K` and the scene's
image size give the scale and offset directly. **The mapping is derived from the
returned intrinsics, not reimplemented from the resize convention.** That is
deliberate and it is the direct lesson of the VGGT anisotropic-squeeze bug: derive
the convention, do not assume it, and the code stays correct if the upstream
resolution table changes.

`estimated_focal_ratio` is that estimate over the scene's calibration. Far from 1.0
on a *calibrated* scene means the two disagree and the poses were computed with the
estimate, not with your calibration. On an uncalibrated scene it is null, because
there is nothing to compare against.

## What is deliberately absent

`mean_reprojection_error` and `median_reprojection_error` are **always null**. The
model has no correspondences, and a reprojection error computed from its own point
maps would report how self-consistent the network is rather than whether it is
right — a number that looks like the one the rest of the pipeline reports and does
not mean the same thing. To get a real one, triangulate against these poses and read
the triangulator's error.
