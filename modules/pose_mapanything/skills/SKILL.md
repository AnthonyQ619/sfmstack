---
module: PoseMapAnything
module_version: 1.0.0
upstream: facebook/map-anything, MapAnything package 1.1.4 @ 3d10cf7
curated_at: 2026-09-25
sources: 4
---

## Where to go next

This file is the router. Everything below is orientation; the detail lives in the
other four documents, and this table is how to pick one without fetching all of
them.

| You want | Read |
| --- | --- |
| whether to run it at all, and what it costs | this file |
| what the four parameters do and which to leave alone | `tuning.md` |
| what the poses are, and what they are not | `artifact.md` |
| what it cannot tell you, and where it is silently wrong | `limitations.md` |
| what any claim here rests on | `sources.md` |

## What it is for

A second correspondence-free pose estimator. It consumes `scene/v1` — images and
nothing else — and returns a pose for every image, plus its own estimate of the
intrinsics.

**It is not here because it might beat `PoseVGGT`.** It is here because one
correspondence-free opinion cannot break a tie. Every other producer of poses in
this registry stands downstream of the matcher: `PoseEssentialToPnP` needs tracks,
`SparseGlobalCOLMAP` needs pairwise matches, and `SparseVGGT` and
`SparseMapAnything` take poses as *input*, so they are conditioned on the geometry
you might want to check. That left exactly one module whose answer owes the matcher
nothing.

The failure this addresses is the one no correspondence-based reading can see. On a
capture with repeated or near-symmetric structure, the matcher can be confidently
wrong in a globally consistent way. The model then agrees with its own evidence at
every baseline, and every reading built on that evidence agrees with it too —
registration is full, reprojection error is low, held-out correspondences verify.
Two independent estimators agreeing with *each other* and disagreeing with the
model is a reading the rest of this registry cannot produce.

## When to run it

**Not on every capture.** It is a GPU pass over the whole set and it delivers
nothing you would ship — its poses are initialisation-grade. Run it when you want
the comparison, which is when you are about to deliver and want to know whether the
model agrees with anything outside its own evidence, or when a health reading is
stuck and you need to rule out the reference (`health/bounce.md`).

Run it **alongside `PoseVGGT`, not instead of it.** Either one alone gives a
disagreement with no scale to read it against: you cannot tell whether the model is
wrong or the estimator is wandering. Two of them give you both numbers, and the
question becomes answerable.

## What it costs

Around 90 seconds on a full set on a modern GPU, 24 GB of RAM, one forward pass.
Weights are baked into the image and the container runs offline — **do not mount a
host `HF_HOME` over `/opt/weights/hf`**, which hides them and sends the run to the
Hub.

## What it gives up

The same as `PoseVGGT`: no seed pair, no inlier count, no per-image diagnostic, and
both reprojection-error metrics null, because there are no correspondences to
measure against. Frame and scale are its own and nothing about the output is metric.
