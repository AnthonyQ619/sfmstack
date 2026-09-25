---
module: PoseMapAnything
module_version: 1.0.0
curated_at: 2026-09-25
---

# What it cannot tell you

## Accuracy is initialisation-grade

These poses are trained to be right about geometry, not to minimise reprojection
error on your scene. They are a starting point and a second opinion. **They are not
a deliverable.** If the comparison says to take the feed-forward path, take the
whole branch — the poses on their own are not the remedy.

## Two learned estimators can be wrong together

This is the failure mode that limits the whole design, and it is worth stating
plainly here because it is not obvious from the module's purpose.

`PoseMapAnything` and `PoseVGGT` are independent of the *matcher*. They are not
independent of *each other*: they share a training distribution, and on a scene far
outside it they can agree tightly and both be wrong. Measured on a vegetated
exterior: the two estimators sat within a few per cent of each other and both
disagreed with the delivered model by an order of magnitude more — and the
delivered model was the better reconstruction, beating the feed-forward branch on
both accuracy and completeness.

So a disagreement is a reason to **measure the alternative**, never a reason to
discard what you have. `plan/pose.md` carries the rule; this is the module-level
reason it exists.

## Chunking does not stitch

Each forward pass gets its own world frame and its own scale, and this module does
not align them. Poses in different chunks are not comparable to each other, and a
chunked answer cannot serve as a second opinion at all, because the comparison needs
one frame. `chunks` above 1 raises an error diagnostic for exactly this reason; the
fix is to sample fewer images, not to chunk them.

## The licence is not commercial

The default checkpoint `facebook/map-anything` is **CC-BY-NC 4.0 — not usable
commercially.** `facebook/map-anything-apache` is the Apache-2.0 alternative and is
selected by a build arg on `docker/runtime-mapanything/Dockerfile`. The code itself
is Apache 2.0. This is recorded, not enforced.

## What it has no opinion about

No seed pair, no inlier count, no per-image confidence, no statement about which
images were hard. When registration is not 1.0 it means images were dropped before
the forward pass — not that registration failed, because the model poses everything
it is shown.
