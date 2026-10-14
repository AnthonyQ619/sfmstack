---
module: PoseMapAnything
module_version: 1.2.1
curated_at: 2026-10-13
---

# What it cannot tell you

## Accuracy is initialisation-grade

These poses are trained to be right about geometry, not to minimise reprojection
error on your scene. They are a starting point and a second opinion. **They are not
a deliverable.** If the comparison says to take the feed-forward path, take the
whole branch — the poses on their own are not the remedy.

## Its repeat is bit-identical, and the sibling's is not

Measured on one capture: a forced repeat of an identical recipe returned a
**bit-identical** result here, while the other learned estimator moved **0.237 on the
pose metric** between two runs of its own identical recipe. Worth stating because the
reverse is assumed — that a learned forward pass is the non-reproducible part of a
pipeline. On this module it is the reproducible part.

Do not generalise it to the family, and do not generalise it from one capture: what it
licenses is comparing two configurations of THIS module from single runs, which the
sibling does not license.

## The estimators and the learned dense module share a training distribution

This is the failure mode that limits the whole design, and it is worth stating
plainly here because it is not obvious from the module's purpose.

`PoseMapAnything` and `PoseVGGT` are independent of the *matcher*. They are not
independent of *each other*, or of the learned dense module built on the same kind of
data. Measured on a vegetated exterior: the two estimators sat within a few per cent
of each other and both disagreed with the delivered model's camera *positions* by an
order of magnitude more, while its rotations were as good as theirs — and the
geometric cloud still beat the learned dense module on both accuracy and completeness
([evidence](../../../skills/evidence/estimator-outvote-2026-10.md#finding-1--the-two-forms-of-the-reading-fire-on-different-captures)).
Two agreeing estimators say the poses are probably right; they say nothing about how
the learned dense module will do on that scene.

`plan/pose.md` carries the delivery rule. It keeps the geometric cloud when only the
camera-position form of the reading fires, which is this capture's case.

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
