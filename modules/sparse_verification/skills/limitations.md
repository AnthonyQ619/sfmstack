---
module: SparseVerification
module_version: 1.0.0
curated_at: 2026-09-12
---

# What held-out verification cannot tell you

It tests whether a model contradicts pairwise evidence it was not fit on.
Everything it cannot do follows from the words *pairwise* and *contradicts*.

## What a contradiction means

*Symptom:* `contradicted_by_held_out_evidence`, with `heldout_residual_px` many
times the inlier threshold.

The model's relative poses disagree with correspondences the matcher found and
the model never used. The model's own residuals cannot show this: the solve
minimised them over the evidence it kept, so a model that settled into a wrong
configuration reports those as small as a correct one does, and can report them
smaller.

The measured cause was not a bad match set. One capture's identical
correspondences, solved repeatedly, gave a correct model on some solves and a
drifted one on others. A capture can have more than one stable answer, and which
one a single solve lands in is not under the agent's control.

*What to do:*

1. **Solve again from the same inputs** before changing anything. A second solve
   that reads clean here is the model to keep.
2. **Do not choose between the two solves on reprojection error, registration or
   the health profile.** A self-consistent wrong model satisfies all of them.
3. **Read the per-pair array.** A contradiction confined to the pairs that span
   one part of the capture locates where the solve went wrong.
4. If every solve is contradicted, the evidence itself is inconsistent with any
   single geometry. Look upstream — the matcher's `cycle_merge_rate`, the
   tracker's `inconsistent_rate` — rather than at the solver.

## When nothing is held out

*Symptom:* `nothing_held_out`, and `heldout_residual_px` is null.

No pair had enough correspondences that the model did not already use. The model
is **unverified**, which is a different state from verified and must not be read
as it.

*What to do:* run this module yourself with another matcher's
`pairwise_matches/v1` of the same scene as `matches`. A different matcher's
correspondences were never in this model's objective at all, so every one of them
is held out. Lowering `min_held_out_per_pair` also produces a reading, but one
whose pairs rest on a handful of correspondences each.

## It cannot see an error the evidence allows

The check is epipolar: for each pair it asks whether correspondences lie on the
lines the model's relative pose predicts. A pose error that moves points *along*
those lines, or that every pair's correspondences are equally consistent with, is
invisible to it.

Measured on a shallow subject viewed from a modest baseline: a model a few
degrees wrong against reference geometry and a nearly exact model of the same
capture read the same — on their own matches, and on each other's. So a clean
reading is not evidence that a model is right, and two clean models are not
evidence that they agree. Where the capture is shallow relative to its distance
from the camera, rotation and translation can trade against each other with
little change to any pair's epipolar geometry; that is the likeliest explanation
and it has not been tested.

## It cannot measure accuracy

It measures consistency with evidence. There is no ground truth anywhere in the
pipeline, and this does not supply one. Its value is narrower and real: it is the
one reading a wrong but self-consistent model cannot pass by construction,
because the evidence it uses was never in that model's objective.

## Held-out is not the same as clean

The held-out correspondences are everything the model did not use, and that
includes matches the pipeline *rejected* as outliers, not only ones it never
considered. They are not a clean sample. That is why the reading is a median per
pair and a weighted median across pairs: a minority of outliers on a pair does
not move its median. A pair where outliers are the majority can read badly on a
correct model; the weighting keeps such pairs from deciding the result, but the
per-pair array will show them.

A detector-free dense matcher leaves nearly all of its output unused, so its test
set is large. A detector pipeline leaves a smaller share, but a substantial one,
and the reading has separated correct from drifted models on both.

## It runs on refined models only

Before the final bundle adjustment every model reads badly on held-out evidence,
correct or not, because the greedy pose stage has not yet been reconciled. The
adjustment is what pulls a correct model onto the evidence it never saw and
leaves a drifted one where it was. That is why the service runs this after an
optimization module and nowhere earlier, and why a reading taken on a
triangulator's output is not comparable with one taken after refinement.
