---
module: SparseGlobalCOLMAP
module_version: 1.1.0
curated_at: 2026-08-10
---

# Sources

## GLOMAP: Global Structure-from-Motion Revisited
Pan, Barath, Pollefeys, Schönberger — ECCV 2024.
<https://lpanaf.github.io/eccv24_glomap/>

The method this module runs. Its claim, which matches what is measured here, is
accuracy competitive with incremental COLMAP at substantially better scalability.
The change from earlier global pipelines is that it estimates camera positions and
3D structure jointly rather than positioning cameras first.

Read for: why global positioning replaces separate translation averaging, and the
failure modes of rotation averaging on a graph with wrong edges.

## COLMAP / pycolmap
Schönberger & Frahm, *Structure-from-Motion Revisited*, CVPR 2016.
<https://colmap.github.io/> · <https://github.com/colmap/pycolmap>

pycolmap 4.1.1 supplies `global_mapping`, the database, and two-view estimation.

API notes that cost time here, all verified against 4.1.1:

- `pycolmap.Database` has no constructor; it is `Database.open(path)`.
- `estimate_calibrated_two_view_geometry(camera1, points1, camera2, points2,
  matches, options)` takes the FULL per-image keypoint tables in `points1/2` and
  index pairs in `matches`. Passing pre-selected points with 0..n indices verifies
  a different correspondence set and reports a plausible inlier count for it.
- Ceres options are one level down: `options.ceres.solver_options`, not
  `options.solver_options`.
- `Reconstruction.update_point_3d_errors()` must be called before
  `compute_mean_reprojection_error()`, which otherwise returns 0.0.

## Rotation averaging
Hartley, Trumpf, Dai, Li, *Rotation Averaging*, IJCV 2013.

Background for why a single wrong relative rotation degrades the whole graph
rather than one image, which is the substantive difference from incremental SfM
and the reason `min_num_matches` defaults higher here than in any matcher.

## The predecessor
`scene_agent/breadth_agent/src/sfmcore/scenereconstruction.py`,
`SparseSceneEstimationCOLMAPGlobal`.

Same pipeline. Differences: it took a `PointsMatched` object that conflated pairs
and tracks, wrote a single shared camera for the whole scene, and kept its work
directory as an option. Here the input is `pairwise_matches/v1`, one COLMAP camera
is written per distinct calibration so a multi-camera rig works, and the work
directory is a tempdir because the COLMAP model is preserved as an artifact
sidecar instead.
