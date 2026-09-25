---
module: PoseFill
module_version: 1.0.0
curated_at: 2026-09-25
---

# What comes out

A `poses/v1` artifact covering every image in the scene: `cam_from_world` (3×4,
OpenCV), `valid`, `image_index` — plus a `fill` sidecar carrying `filled` and
`shared_cameras`, which the additive-extension rule allows and which is the same
place `PoseVGGT` and `PoseMapAnything` put their intrinsics.

## The frame is the core's

The core's rows are copied through untouched, so the output frame and scale are the
core's, not the estimator's. Anything that consumed the core's poses can consume
these. The estimator's rows are mapped in by the fitted similarity: a rotation
composed with the fit's rotation, and a translation that absorbs the fit's scale
and offset. The result is a proper rotation block — nothing about the output tells
a filled camera from a registered one by its coordinates alone.

That is the point, and it is also the hazard, which is why the mask exists.

## The `filled` mask, and why downstream depends on it

A filled camera rests on **no correspondences**. Every reading built on
correspondences will therefore find it unsupported — correctly, and misleadingly,
because it was never claimed to be supported.

Concretely: `SparseVerification` builds connected components over the cameras whose
held-out correspondences agree with the model. A filled camera is in no agreeing
pair, so it becomes its own component. Fill four cameras and the model reports four
stray cameras, which trips `model_not_supported_by_its_own_evidence` at error
severity — a veto that `plan/pose.md` says ends the matter. **A correctly executed
fill would be discarded by construction.**

So the mask is not bookkeeping. `SparseVerification` reads it and excludes those
cameras from the stray count; `SparseTriangulation` and the bundle adjusters carry
it into `sparse_model/v1` so `filled_images` can be read beside
`registered_images`. Anything that writes a merged pose table and omits the mask
produces a model the rest of the stack is obliged to reject.

## What `registered_fraction` means afterwards

It reaches 1.0 on a successful fill, so rules that key on LOW registration stop
applying once this has run — `plan/pose.md`'s "global reconstruction instead when
`registered_fraction` is low", for one. That is correct: the capture is now fully
posed. It also hides the matcher weakness underneath, which is exactly why
`filled_images` is published and why the report has to name the filled frames.

## What it does not write

No points, no observations, no tracks, no intrinsics. It is a pose table. The
structure comes from `SparseTriangulation` against the scene's own tracks, which is
what makes the filled cameras carry real observations wherever correspondences
reach them rather than none at all.
