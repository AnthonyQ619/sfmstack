---
module: FeatureMatchLoFTR
module_version: 1.0.0
curated_at: 2026-08-08
---

# When LoFTR is not the answer

## It is not a general-purpose upgrade

*Symptom:* it works, it is slow, and the reconstruction is no better than SIFT's.

On DTU scan1 — well-lit, high-texture, turntable — LoFTR is not competitive with a
classical sparse stack, and costs far more. Detector-free matching earns its place
where detectors fail, not everywhere.

*What to do:* use it for the scenes it is for. Textureless surfaces, smooth
material, low-contrast interiors. If the detector's `spatial_coverage` and
`keypoints_min` are healthy, a detector-free matcher is solving a problem you do
not have.

## Tracks chain poorly without tuning the tracker

*Symptom:* `long_track_fraction` near zero, and images that cannot be registered
despite healthy per-pair matching.

*Why:* covered in [tuning.md](tuning.md#the-first-thing-to-set-is-not-in-this-module).
Each pair is estimated independently, so the same physical point lands at different
sub-pixel positions per pair, and the tracker's proximity tolerance has to cover
that.

*What to do:* raise the tracker's `merge_eps_px`. This is the single most important
thing to know about running this module, which is why it is the first section of
both files.

The structural version of the same limitation: proximity merging is a weaker
mechanism than identity merging, and it will always be. A detector-free matcher
that emitted a consistent global point identity — matching to a shared reference
rather than pairwise — would not need it. Nothing here does that.

## Semi-dense is not dense

*Symptom:* expecting a dense depth map and getting a few thousand correspondences.

LoFTR matches on an 8x8 coarse grid and refines the survivors. It is much denser
than a sparse detector and far sparser than optical flow. It produces
correspondences, not a depth map.

*Switch to:* a dense-reconstruction module if what you want is a surface.

## Planar and rotation-only captures

*Symptom:* `planarity` above 0.9.

Identical to every other matcher's limitation and not fixable by any of them.
LoFTR will match a planar scene beautifully and the triangulation will still be
degenerate.

## No GPU

*Symptom:* it works and is unusably slow.

More acute than for any other module here — semi-dense attention over full image
pairs is the heaviest computation in the repo. The measurements in this file exist
only because the scene was cut to 5 images at 640px.

If no GPU is reachable, this module is not a real option, and a textureless scene
is simply not reconstructible with what is available.

## What has not been measured

Recorded so the DTU numbers are not over-read. LoFTR has been run here only on DTU,
which is exactly the wrong scene for it. The comparison that would be informative:

- ETH3D `courtyard` — outdoor, real illumination variation.
- Any genuinely textureless interior, where SIFT's `spatial_coverage` collapses and
  a detector-free matcher should win outright.

The expected result is that LoFTR wins decisively on the second and that DTU stays
a poor showcase. It has not been run.
