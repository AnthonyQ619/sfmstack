---
module: SparseVerification
module_version: 1.1.0
curated_at: 2026-09-14
---

# Where the claims in these files come from

There is no upstream library to cite. The epipolar (Sampson) distance is textbook
two-view geometry; everything else here is measured in this stack.

## Measured

The readings behind each point are in
[evidence/second-solve-2026-09](../../../skills/evidence/second-solve-2026-09.md#the-veto),
and the component reading's in
[evidence/view-graph-support-2026-09](../../../skills/evidence/view-graph-support-2026-09.md).

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
- **That the agreeing pairs of a delivered model form one component.** The
  component reading recomputed over every corpus capture that delivered a dense
  reconstruction — studio-rig orbits and site walks, indoor and out. All but one
  read a single component containing every registered camera; the exception read
  two, the second of size one, a camera hanging off the end of a walk. That is the
  whole basis for the `supported_components` and `supported_second_size` ceilings
  of 1, and it is a description of successes rather than a discrimination
  experiment: **no corpus capture reads as pieces, so the corpus fixes the healthy
  end of this reading and says nothing about where the unhealthy end begins.** The
  separation is wide enough that a ceiling had to be chosen rather than fitted.
  Per-capture figures are in the campaign file; carry none of them as a threshold.
- **That the component reading has to use `residual_all_px` and not the held-out
  residual, which is why the more independent quantity is the wrong one here.**
  Built first on the held-out residual, the obvious choice given what the rest of
  this module does, and run over the same set. It fragmented roughly a quarter of
  them — several rig orbits and a site walk, into a handful of components each,
  worst on the capture with the fewest scored pairs. **More than one would have
  raised an error on a capture that delivered.** The cause is sample size, not
  geometry — a held-out median rests on tens of correspondences where the
  all-correspondence median rests on hundreds, and a noisy per-pair median drops
  sound pairs below the threshold and cuts cameras loose. Recomputed on
  `residual_all_px`, the same set gave the all-but-one result above.
  So this reading trades independence for a stable per-pair estimate, and the
  trade is sound because a model in pieces is contradicted by the correspondences
  it KEPT as well as by the ones it did not — independence is what the veto needs,
  not what a connectivity test needs.

- **That the shipped container computes all of this correctly**, and not merely the
  adapter's functions driven in-process. The 1.1.0 image run by hand on two corpus
  captures, chosen as the hardest cases rather than the easiest: the rig orbits the
  discarded held-out design fragmented worst and thinnest, the capture with the
  highest residual and lowest agreeing share, the smallest capture in the corpus,
  and the only one that reads two components. Every one reproduced the in-process
  computation exactly and every one stayed silent, the last correctly treating its
  stray camera as a stray. A model known from reference geometry to be badly wrong
  was run through the same image and did raise the error, so both directions are
  exercised. The artifact sealed with the new
  column present and `residual_all_px` finite on every scored pair where
  `residual_px` is NaN on half of them, which is the sample-size problem that
  design was discarded for, visible in one artifact.

## Reasoned, not measured

- **That the component count sees a failure the weighted median cannot.** This is
  an argument about what the two quantities are — an average over pairs cannot
  express whether a subgraph is connected — together with the measured fact above
  that correct models read one component. It is not a measured demonstration of a
  piecewise model being caught here where the residual missed it: producing one on
  a corpus capture would mean deliberately corrupting a view graph, which has not
  been done.
- **That repeated structure is the cause to suspect.** Carried from
  `SparseGlobalCOLMAP`'s limitations file, which states the mechanism, plus the
  observation that a self-matching pair satisfies an inlier-ratio filter honestly.
  No capture in this corpus isolates repeated structure sharply enough to test it.
- **`heldout_residual_mrad`** is a unit conversion of the px reading by the
  capture's focal length. It is deliberately given no band: across the corpus it
  spans more than an order of magnitude, from a small fraction of a milliradian to
  under two, and the capture at the top of that range sits well inside the px
  ceiling it is actually judged by — so any mrad band tight enough to be useful
  would fail a capture this module passes. Nothing has been swept across focal
  lengths; see `plan/scene_to_pipeline.md` trap 11 for what rests on arithmetic.

## What rests on nothing

- The default `inlier_threshold_px` is the pose estimator's, not fitted here.
- The default `min_held_out_per_pair` is a judgement, not a measured optimum.
- The coincidence radius that decides "used" is the trackers' widest default
  merge radius, chosen so it always recognises a tracker's own output; it was
  not tuned.
- The explanation offered for the blind spot — rotation trading against
  translation on a shallow subject — is the likeliest one and has not been
  tested.
