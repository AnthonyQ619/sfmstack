---
module: PoseFill
module_version: 1.1.0
curated_at: 2026-09-25
---

# What one similarity cannot absorb

## Drift

The fit has seven parameters: one scale, three rotations, three translations. It
assumes the estimator's scale is **consistent along the whole capture**. A learned
model that drifts — scale varying as the trajectory runs — cannot be corrected by
seven parameters, and each filled camera then lands wrong by whatever the drift is
at its own position.

Expect this on a long handheld walk. Do not expect it on a subsampled orbit.

**`shared_residual` is the reading that sees it**, and it is the only one that can.
The filled cameras have no correspondences and no reference, so nothing measures
them directly. What can be measured is whether the two tables were put into a
common frame at all, on the cameras where both have an opinion — and if they were
not, the transform placing the filled cameras does not hold. The
`fit_does_not_agree` diagnostic fires on it at error severity.

When it fires, deliver the core and say in the report which frames are missing.
A refused fill costs the core; a bad fill costs the delivery.

## The fit residual does not price the filled frames

`shared_residual` is computed on the cameras **both tables already place**. It says
whether the two frames were put into correspondence. It says nothing about the
cameras this fill is actually placing, and the two come apart exactly where it
matters: a fill can sit on a clean frame fit and still be placing frames only one
estimator has an opinion about.

An agent met this and had no reading for it — the two estimators agreed across the
overlap and disagreed by tens of degrees on precisely the four frames it was about
to fill. Supply a second estimator as `poses_b` and `filled_agreement_deg` answers
it: the estimators' relative-rotation disagreement restricted to the filled indices.
`filled_frames_disputed` fires on it.

Without `poses_b` the reading is null, and the fill rests on one opinion about the
frames that matter most. That is allowed and it is worth knowing you are doing it.

## It cannot tell you whether the estimator is right

Only whether the estimator agrees with the core where they overlap. Those are
different questions, and a scene outside the estimator's training distribution can
produce a model that agrees on the overlap and is wrong beyond it. Two
correspondence-free estimators agreeing with each other is the stronger reading
there — `sfm_compare`'s `pose_agreement` — and it is worth taking before spending a
run here.

## It is not a swap, and refuses to become one

With fewer shared cameras than `min_shared_cameras` there is nothing to fit the
frame onto, and the module raises rather than guessing. A core that shares fewer
than four cameras with the estimator has not registered enough to be a core; the
answer there is the feed-forward model delivered on its own, said plainly.

## The filled cameras may gain no structure

Triangulation places points from the scene's tracks. A camera left out of the core
because its correspondences were too thin may still be too thin afterwards, and
then it carries a pose and no observations. `min_frame_points` reads 0 for it —
that reading exists on `sparse_model/v1` precisely because `registered_images`
cannot see a posed camera with no structure.

This is not a failure of the fill. The pose is still worth having: every pair
touching that camera now has an answer, which is what the pose metrics measure. But
it does mean the dense stage gains nothing from it — MVS chooses source views per
image and an image holding no structure has nothing to choose from, so its depth
map comes back empty. **The fill is a pose-path gain and dense-neutral.**

## What has not been measured

The fill rule itself is measured, and the campaign file carries it. What this
module adds — the trimmed fit, the residual gate, the `filled` mask — is
implementation, and the gate's default has not been fitted on a campaign. Read
`shared_residual` against what a capture of this kind reads, not against the
default.
