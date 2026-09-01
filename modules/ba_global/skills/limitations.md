---
module: BundleAdjustmentGlobal
module_version: 1.1.0
curated_at: 2026-08-07
---

# What bundle adjustment cannot fix

BA is a *local* optimiser of a *given* problem. It moves cameras and points to
reduce reprojection error from where they already are. Everything it cannot do
follows from those two words.

## It cannot escape a bad local minimum

*Symptom:* `error_reduction` near zero with `reprojection_error_after` still high.

*Why no parameter helps:* the solve is a descent from the initial estimate. If the
poses are qualitatively wrong — a frame registered backwards, a model folded on
itself — there is no downhill path to the right answer. More iterations, a
different loss, and a looser tolerance all descend into the same basin.

*What to do:* fix the poses. Check `PoseEssentialToPnP`'s `init_pair_angle` and
`median_triangulation_angle`, and the matcher's `planarity`.

## It cannot fix wrong correspondences

*Symptom:* error stays high, and the tracker reported a raised `inconsistent_rate`.

A track that fuses two distinct scene points is a *contradiction*, not a noisy
measurement. BA will place the point somewhere between the two, satisfying neither,
and report convergence. The robust loss helps at the margins and does not solve it.

*What to do:* the tracker's `on_conflict` and the matcher's `ratio_test`. See the
measured sweep in the tracker's tuning file, where loosening `ratio_test` improves
every track statistic while `inlier_ratio` collapses — those extra tracks are
exactly the ones BA cannot use.

## It cannot recover scale

The reconstruction is a similarity-equivalent class. BA fixes the gauge (this
module pins two cameras) and optimises within it; it does not and cannot produce
metric scale.

Nothing in an image-only pipeline can. It needs a known length in the scene, metric
depth, or GPS.

## It cannot improve a two-view point

*Symptom:* `points_optimized` is large, `error_reduction` is small, and the input
cloud has `mean_track_length` near 2.0.

A two-view point is exactly determined. BA slides it along its ray to trade one
view's residual against the other's, which changes the number without adding
information.

*What to do:* `min_track_length: 3` to stop paying for them, and fix the real
problem upstream — the matcher's `window` is what creates multi-view tracks.

## It does not remove outliers

This module optimises the point set it is given and writes back the same points.
It does not delete anything. COLMAP's mapper interleaves BA with filtering and
retriangulation; a single BA call does not.

*What to do:* filter in `SparseTriangulation` (`max_reprojection_error`,
`min_triangulation_angle_deg`), or run triangulate → BA → triangulate again, which
the driving agent can express without any new module.

**That last route does not exist, and this file is the wrong place to have claimed
it.** A bundle adjuster produces `sparse_model/v1`; every triangulator consumes
`poses/v1`; nothing converts between them, so `triangulate → BA → triangulate again`
raises a `WiringError` rather than running. Confirmed by trying it. If you want the
effect, the expressible version is to re-run the TRIANGULATOR with tighter filters
against the original poses and bundle-adjust that instead — which discards the
refinement rather than building on it, and is a materially weaker move. A file whose
job is to say what cannot be done should not be the one inventing a capability.

## When to use a different scope

*Symptom:* the solve is slow and you are calling it repeatedly inside a
registration loop.

Global BA over everything, every few frames, is quadratic misery on a long
sequence. `BundleAdjustmentLocal` refines a window and holds the rest constant,
which is the right tool inside the loop; global BA is the right tool once, at the
end.

```
sfm_find_alternatives(produces="sparse_model/v1", consumes="sparse_model/v1")
```

## A note on the pycolmap boundary

Everything here depends on the array-to-`Reconstruction` translation being correct.
Two conventions are load-bearing and silently wrong if broken:

- **cam-from-world**, matching COLMAP. A world-from-camera producer upstream would
  give plausible-looking BA output and a wrong model.
- **undistorted pixels**, hence PINHOLE cameras. A producer writing distorted
  observations would have distortion applied twice.

`reprojection_error_before` is the guard: it is computed by COLMAP from the
translated model and should match what the triangulator independently reported
(0.3763 vs 0.376 on the reference run). A large disagreement there means the
translation is wrong, not that the model is bad.
