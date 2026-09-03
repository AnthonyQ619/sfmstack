---
module: SparseTriangulation
module_version: 1.1.0
curated_at: 2026-08-07
---

# Sources

## Triangulation

**Hartley and Zisserman, "Multiple View Geometry", 2nd ed., chapter 12.**
`cv2.triangulatePoints` implements the linear DLT method of section 12.2.

H&Z are explicit that the linear method is not optimal — section 12.3 gives the
optimal two-view triangulation that minimises geometric rather than algebraic
error, and 12.5 covers the multi-view case. We use the linear method and then
filter hard on the result, on the grounds that a bundle adjustment follows and
will do the optimisation properly. That reasoning is only valid *because* BA
follows; a pipeline ending here would want the optimal method.

## Best-pair selection

Choosing the widest-baseline observing pair rather than triangulating from all
views is standard in incremental pipelines and is what COLMAP's
`EstimateTriangulation` does in spirit (**Schönberger and Frahm, CVPR 2016**,
section 4.4).

The reasoning: the conditioning of the depth estimate is governed by the widest
angle available, and adding near-coincident views to a multi-view DLT does not
improve it while making the "verify in every view" check circular.

## The angle filter

**Schönberger and Frahm, section 4.4** filter on triangulation angle and
reprojection error, in both directions, exactly as implemented here. The default
of 2° is in the range COLMAP uses (its `min_triangulation_angle` defaults to 1.5°).

The choice of the *widest* angle over all observing pairs, rather than the angle
of the pair used for triangulation, is deliberate: a point can be triangulated
from a mediocre pair and still be well-conditioned by a third view.

## Cheirality

**Hartley and Zisserman, section 9.6.3.** The constraint that a point must lie in
front of every camera that observes it. Implemented as `z > 0` in each observing
camera's frame.

Recorded as a metric rather than a silent filter because its *rate* is diagnostic:
consistent input produces almost none, so a raised rate is evidence about the
poses. On the DTU reference run it is exactly 0.

## Colour sampling

No source; it is a mean over each point's observations, sampled by nearest pixel.
COLMAP's `extract_colors_for_all_images` uses the same idea. Bilinear sampling
would be marginally better and is not worth the code.

## Predecessor code

There is no single predecessor for this module — that is the point of it existing.
Triangulation appeared in:

- `camerapose.py`, `CamPoseEstimatorEssentialToPnP.triangulate_track_best_pair`
  and `update_structure_from_tracks`
- `scenereconstruction.py`, `Sparse3DReconstructionIncremental`
- `scenereconstruction.py`, `SparseSceneEstimationCOLMAPGlobal` (via pycolmap)
- `baseclass.py`, `TriangulationCheck`

with `max_reproj_error` defaulting to 3.0 in one place, 4.0 in another, and
`min_angle` to 1.0 in both. The clouds were not comparable across pose estimators
because the filtering differed, which is the concrete cost of not having this
seam.

## What is asserted without a source

Audited 2026-09-02 against this module's own manifest.

- **Healthy bands with nothing behind them.** `min_frame_points`, `two_view_fraction`, `p95_reprojection_error`, `p05_triangulation_angle`, `point_count`, `observation_count`, and 3 more declare a range and no diagnostic on this module reads them. A band with no diagnostic is a description of the captures measured so far, not a judgement on yours -- and a corpus maximum is the largest of N draws, so the next capture exceeding it is expected rather than anomalous.
- **Numeric tuning advice with no citation in this file.** `min_triangulation_angle_deg`, `min_observations` name specific values in their tuning prose. The reasoning behind them may be sound; the numbers are settings that worked here, not results anyone has published.
- **Scope of the measurements.** What is written here was exercised across 27 runs of this module in a seventeen-capture sweep of benchmark captures, at version 1.1.0. That is the whole evidence base: no capture outside those two benchmark families has been run through it.

## Review triggers

Re-read and re-check this file when any of these happens:

- **This module's version changes from 1.1.0.** These notes were written against it; a metric set or a published band can change with a version and the prose does not follow automatically.
- **A capture unlike the benchmark families appears.** Every band here was fitted on controlled-rig and field captures from two benchmark datasets. Per-frame appearance readings transfer to a larger capture; adjacent-motion readings and anything denominated in pairs do not.
- **A reading crosses one of `min_frame_points`, `two_view_fraction`, `p95_reprojection_error`, and 6 more and nothing fires.** That is this file's known gap, not a defect in the capture -- but it is the signal that the band deserves either a diagnostic or a wider range.
