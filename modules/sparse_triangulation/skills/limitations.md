---
module: SparseTriangulation
module_version: 1.1.0
curated_at: 2026-08-07
---

# When SparseTriangulation is not the problem

This module is almost never the thing to fix. It performs a closed-form
computation on inputs it does not control, so its metrics are mostly a report on
the poses and the tracks.

## Cheirality failures are a pose problem

*Symptom:* `rejected_cheirality` above ~0.05.

A point landed behind a camera that claims to see it. Triangulation cannot
produce that from consistent input — it means the pose is wrong, or a
sign/frame convention got inverted somewhere.

*Why no parameter helps:* there is no threshold involved. The test is `z > 0`.

*What to check, in order:*
1. The pose artifact's `mean_reprojection_error` and `median_triangulation_angle`.
2. Whether the pose source and this module agree on convention. Everything here is
   **cam-from-world**; a producer emitting world-from-camera would give exactly
   this signature — high cheirality rejection with otherwise plausible numbers.
3. Whether intrinsics are being taken from the right place. If the pose artifact
   carries an `intrinsics` file this module prefers it over the scene's
   calibration, deliberately; mixing a refined K with unrefined poses (or vice
   versa) produces geometrically inconsistent input.

## When triangulation produces nothing

*Symptom:* the module raises rather than producing an artifact.

The error message reports how many tracks had enough registered observations, how
many failed cheirality, and how many failed the angle and reprojection filters —
read it, because the three causes have different fixes.

- **Most failed cheirality:** the poses are wrong. See above.
- **Most failed the angle filter:** the capture has no parallax. Check the
  matcher's `planarity` metric. Lowering `min_triangulation_angle_deg` will
  produce points, and they will be meaningless.
- **Too few had enough registered observations:** check the pose artifact's
  `registered_fraction`. Observations in unregistered images are dropped before
  anything else happens here, so a half-registered model halves the input.

## Two-view clouds

*Symptom:* `mean_track_length` near 2.0.

Not fixable here. The tracks are what they are; see the matcher's `window` and the
tracker's `long_track_fraction`.

Worth knowing what it costs downstream: bundle adjustment on a purely two-view
cloud has no redundancy, so it will report convergence having achieved nothing
except moving points along their rays.

## What would replace this implementation

If the architecture is right and only the triangulation is weak, the upgrades are
known:

- **Multi-view DLT** rather than best-pair DLT. Uses every observation at once
  instead of the widest-baseline two. Slightly better conditioned; marginal on
  clean data, and it makes the "verify in every view" step less meaningful because
  every view already participated.
- **Iterative refinement** of each point against all its observations before the
  filters run — effectively a one-point bundle adjustment. This is what would
  actually move the numbers, and it is also exactly what `BundleAdjustmentGlobal`
  does afterwards for less total effort.
- **Retriangulation of failed tracks** after BA has improved the poses. COLMAP
  does this and it recovers real structure. Not implemented; the honest shape is a
  loop at the orchestrator level (triangulate → BA → triangulate again), which the
  driving agent can already express without any new module.

**That last route does not exist, and this file is the wrong place to have claimed
it.** A bundle adjuster produces `sparse_model/v1`; every triangulator consumes
`poses/v1`; nothing converts between them, so `triangulate → BA → triangulate again`
raises a `WiringError` rather than running. Confirmed by trying it. If you want the
effect, the expressible version is to re-run the TRIANGULATOR with tighter filters
against the original poses and bundle-adjust that instead — which discards the
refinement rather than building on it, and is a materially weaker move. A file whose
job is to say what cannot be done should not be the one inventing a capability.

Any of these keeps the type, so a replacement is discoverable through:

```
sfm_find_alternatives(produces="sparse_model/v1", consumes="poses/v1")
```
