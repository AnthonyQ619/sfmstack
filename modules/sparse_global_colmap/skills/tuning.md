---
module: SparseGlobalCOLMAP
module_version: 1.1.0
curated_at: 2026-08-10
---

# Tuning SparseGlobalCOLMAP

Work outward from the view graph. Almost everything that goes wrong here went
wrong in the matcher, and this module's own parameters mostly decide how much of
that damage it lets through.

1. `verified_pairs` — against the matcher's `pairs_matched`.
2. `largest_component_fraction` and `registered_fraction`.
3. `mean_reprojection_error` and `mean_track_length`.
4. Only then `ba_num_iterations` and the refine flags.

## Reference run

One capture: a short contiguous arc of twelve calibrated frames around a small,
well-textured object on a plain backdrop, at about 1 MP, classical detector at
defaults, ratio-test matcher at `pairing: exhaustive`, everything here at defaults.

| metric | value |
|---|---|
| `verified_pairs` | 63 of 64 attempted |
| `registered_fraction` | 1.0 (12/12) |
| `point_count` | 3608 |
| `observation_count` | 16335 |
| `mean_track_length` | 4.53 |
| `mean_reprojection_error` | 0.316 px |
| `models_found` | 1 |
| runtime | 4.5 s |

For contrast, the incremental chain on the same input needs
`PoseEssentialToPnP` + `SparseTriangulation` + `BundleAdjustmentGlobal` to reach
0.25 px. Global gets to 0.32 px in one module and a fraction of the time, with a
cloud roughly half the size — it triangulates only tracks reaching
`min_track_len` views, where the incremental path keeps two-view points.

## What `max_epipolar_error` actually admits

The parameter is in working-resolution pixels, but rotation averaging receives the
angle those pixels subtend — the threshold over the focal length in the same pixels.
Every capture behind the numbers on this page is a long lens, so the 1.0 px default
has only ever been read here at about a third of a milliradian; on a wide-angle
camera it is several times that at the identical value, and a step upward costs
correspondingly more. `plan/scene_to_pipeline.md` trap 11 carries the conversion,
both directions of the trade, and what rests on arithmetic rather than measurement.
The thinning diagnostic below now reports the figure for the scene in hand.

## `verified_pairs` is zero

Nothing entered the view graph, so there was nothing to average. In order:

1. **`max_epipolar_error` is in WORKING-resolution pixels.** This is the usual
   cause. 1.0 px is tight; on a scene downscaled to `max_edge: 640` real
   correspondences land further off the epipolar line than that. Try 2–4, and read
   the section above first for what that costs at this scene's focal length.
2. **`min_num_matches` (30) against the matcher's `min_matches_per_pair`.** If the
   matcher's weakest pair is below 30, those pairs never reach verification.
3. **`min_inlier_ratio` (0.25)** last. Lower it only when the matcher's own
   `inlier_ratio` is genuinely low, and expect worse rotations if you do.

## `verified_pairs` far below `pairs_matched`

The module rejected a large share of what the matcher produced. That is often
correct — verification here is stricter than the matcher's — and the diagnostic
that reports it frames its own rejection as something to undo, which on the first
two cases below it is not. Settle which case you are in before loosening anything:

- **The matcher's `planarity` near 1.0 on many pairs.** Those pairs are planar or
  rotation-only and *should* fail. Nothing to fix here.
- **Repeated structure in the scene.** A facade, a row of identical windows, the
  same furniture instanced twice: these produce matches that are confident,
  geometrically consistent, and relate the wrong two places. Verification is the
  only stage that removes them, so here the rejection is the thing doing the work,
  and raising the threshold admits exactly the pairs you needed dropped.
  `limitations.md` carries the mechanism — averaging spreads one wrong relative
  rotation over the whole graph, where incremental localises it. Read
  `repetitiveness` from the scene analysis before touching `max_epipolar_error` at
  all. Note also that a matcher's confidence filter does not substitute for this: a
  wrong match between two copies of the same object is a *confident* one, so
  tightening the matcher removes sound correspondences ahead of the ambiguous ones.

  **What to do instead is genuinely open, and the remedy `limitations.md` names is
  reasoned rather than measured.** That file says to raise `min_inlier_ratio`
  toward 0.5. It is the parameter aimed at this hazard and worth a probe, but be
  clear about why it might not work: it is a threshold on the *same* inlier
  evidence the wrong pairs already satisfy. A match between two copies of one
  object is geometrically consistent, so it earns a high inlier ratio honestly, and
  a filter reading that quantity has no purchase on it. Nothing in this corpus
  isolates the case, so there is no measured cut point. Probe it, read the effect
  rather than assuming it, and if the model does not move, treat this as the shape
  with no parameter behind it: the damage was done in the matcher, and no setting
  in this module recovers a view graph whose wrong pairs outnumber its right ones.
- **A heavily downscaled scene.** Raise `max_epipolar_error`.
- **`inlier_ratio` healthy and `planarity` low, yet pairs still dropped.** Raise
  `max_epipolar_error` one step and watch `mean_reprojection_error`: if error
  stays flat while `verified_pairs` rises, the threshold was too tight.

## `registered_fraction` below 1.0

There is no `min_pnp_inliers` to relax here. The camera was not placed because
the graph could not place it.

1. **`largest_component_fraction`.** Below 1.0, the graph is split and no
   parameter in this module can join it — widen the matcher's `window` or use
   `pairing: exhaustive`.
2. **`models_found` above 1.** Same cause, seen from the other side: the pipeline
   built several reconstructions and only the largest is returned.
3. **`min_num_matches`** last. Lowering it admits thin pairs, which may connect a
   stray image at the cost of a worse rotation everywhere.

## `mean_reprojection_error` above 2

1. **`ba_num_iterations`** 3 → 5 or 6. These are pipeline rounds, not Ceres
   iterations: each re-triangulates and re-filters between solves, so raising it
   does more than letting one solve run longer.
2. **Raise `min_num_matches`** toward 60–100. A thin pair contributes a badly
   conditioned relative rotation, and rotation averaging spreads that error over
   the whole graph rather than confining it to one image. This is the lever with
   no equivalent in incremental SfM.
3. **`min_tri_angle_deg`** 1.0 → 2–3 if the cloud looks stretched in depth while
   the error looks fine.

## `mean_track_length` near `min_track_len`

Nothing chained beyond the floor. The view graph is the constraint, not this
module — widen the matcher's `window`. Lowering `min_track_len` to 2 raises
`point_count` and lowers this metric further; it does not add information.

## The refine flags

`refine_focal_length` off when the scene carries real calibration. On when the
intrinsics came from an EXIF guess — and then compare the `intrinsics` file in the
output against what you supplied before trusting anything metric.

`refine_principal_point` stays off. The principal point is weakly observable and
refining it absorbs error that belongs to the pose: reprojection error improves
while the reconstruction gets worse, which is the most misleading failure mode
available in this module.

## Cost

4.5 s for 12 images and 64 pairs. Cost grows with the number of VERIFIED PAIRS,
not with the image count, so the matcher's `pairing` dominates: exhaustive on 100
images is 4950 pairs and a different order of magnitude. This is still the cheap
option — the same set through incremental registration pays a bundle adjustment
per handful of images.

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

## What here rests on nothing — the manifest audit

Audited against this module's own manifest. **Ten healthy bands**
(`min_frame_points`, `two_view_fraction`, `p95_reprojection_error`,
`p05_triangulation_angle`, `median_triangulation_angle`, `point_count`, and
four more) declare a range no diagnostic reads — descriptions of the captures
measured so far, not judgements on yours, fitted on eight runs. The specific
numbers in the `min_num_matches`, `min_track_len`, `max_epipolar_error`,
`min_inlier_ratio`, `min_tri_angle_deg`, `ba_num_iterations` advice (and one
more) are settings that worked here, not published results.

**Two sections here rest on something other than this module's runs.** The
angular reading of `max_epipolar_error` is arithmetic — a pixel tolerance over a
focal length is an angle — over focal lengths read from the corpus calibrations
rather than measured from any run; it now lives in `plan/scene_to_pipeline.md`
trap 11, with the same caveat, because a module tuning topic is pulled and a
reader who does not fetch it never sees the correction. The repeated-structure
bullet restates `limitations.md` in the place the thinning diagnostic sends a
reader, and then downgrades that file's `min_inlier_ratio` remedy from a
prescription to a probe. **That downgrade is an argument, not a measurement**: the
filter reads the same inlier evidence a self-matching object already satisfies, so
in principle it has no purchase on it. No capture in this corpus isolates repeated
structure sharply enough to test the claim either way, which is the honest reason
no cut point is given rather than an omission.
