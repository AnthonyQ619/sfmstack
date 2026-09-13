---
module: SparseVerification
module_version: 1.0.1
curated_at: 2026-09-12
---

# Where the claims in these files come from

There is no upstream library to cite. The epipolar (Sampson) distance is textbook
two-view geometry; everything else here is measured in this stack.

## Measured

- **That self-consistent wrong models pass every self-reported reading.** A
  capture solved several times from identical correspondences, with the solves in
  separate stores so none was served from cache. The wrong models registered
  every frame and reported lower reprojection error than the correct ones.
- **That the held-out reading separates them.** The same solves, scored here:
  correct models read a fraction of a pixel, the drifted ones many times the
  inlier threshold, and a solve off by a fraction of a degree in between and
  under it. The ordering matched reference geometry.
- **That it reads correct models as consistent across pipeline kinds.** Every
  finished model of a sixteen-capture campaign — detector-based and
  detector-free matchers, incremental and global reconstructors, distorted and
  undistorted captures, fixed and refined intrinsics — read well under the
  threshold.
- **That it is blind to an error the evidence allows.** The one model in that
  campaign that was a few degrees wrong against reference geometry read as
  consistent, and read the same as a nearly exact model of the same capture on
  both models' matches.
- **That it needs a refined model.** Scored at the pose stage, before the final
  bundle adjustment, correct and drifted models were separated by far less than
  after it.
- **The three designs that failed first** — frame-order pair selection,
  co-visibility weighting, and comparison against each pair's own two-view fit —
  are described, with why each failed, in the adapter's module docstring.

## What rests on nothing

- The default `inlier_threshold_px` is the pose estimator's, not fitted here.
- The default `min_held_out_per_pair` is a judgement, not a measured optimum.
- The coincidence radius that decides "used" is the trackers' widest default
  merge radius, chosen so it always recognises a tracker's own output; it was
  not tuned.
- The explanation offered for the blind spot — rotation trading against
  translation on a shallow subject — is the likeliest one and has not been
  tested.
