---
module: PoseFill
module_version: 1.0.0
upstream: none -- a similarity fit, implemented here
curated_at: 2026-09-25
sources: 2
---

## Where to go next

| You want | Read |
| --- | --- |
| whether to run it, and what it is for | this file |
| the three parameters and which one matters | `tuning.md` |
| what the output is and what the `filled` mask is for | `artifact.md` |
| what one similarity cannot absorb | `limitations.md` |
| what any claim here rests on | `sources.md` |

## What it is for

A geometric solve registers the cameras its correspondences support and leaves the
rest out. Those frames are still frames the capture contains, and every pair
touching one is unanswered. This module carries them across from a
correspondence-free estimator so one model covers the whole capture.

It is the executable half of the fill rule in
[`plan/pose.md`](../../../skills/plan/pose.md). Read that rule before running this:
**the trigger is a verifier reading firing TOGETHER WITH cameras the view graph
cannot justify — not a low registration count on its own.** Where the core is
holding its cameras on evidence it actually has, filling is a downgrade, and there
is a corpus capture promoted specifically to say so.

## When to run it

After the pose stage, before triangulation, when all of these hold:

- the core left cameras out, or a veto took them out
- a correspondence-free estimator (`PoseVGGT`, `PoseMapAnything`) has run on the
  whole scene
- the two tables share at least six cameras

Then: `PoseFill` → `SparseTriangulation` → `BundleAdjustmentGlobal` with the filled
indices in `fixed_image_indices`. That last part is not optional; see below.

## What it does

Fits scale, rotation and translation from the estimator's frame into the core's, on
the cameras they both place, and writes one pose table: the core's rows untouched,
the missing rows carried across, and a `filled` mask saying which is which.

The similarity is what removes the scale difference. A feed-forward estimator
answers in its own frame at its own scale; after the fit there is one frame and one
scale, and triangulation downstream never sees two.

**It cannot be used as a swap.** With no shared cameras there is nothing to fit on
and the module refuses. If the core registered almost nothing, the answer is the
feed-forward model on its own, said plainly.

## Then freeze the fill

Refining a filled camera drags it using exactly the correspondences that were too
thin to register it — the single largest effect in the campaign behind this rule,
and it runs against the obvious expectation. Refine the core, hold the fill fixed,
and say in the report which cameras are which.

## What decides whether to deliver it

`shared_residual`: how far apart the two tables put the cameras they share, after
the fit, as a fraction of the model's span. The filled cameras themselves cannot be
checked — no correspondences, no reference — so this is the only reading that
prices the operation, and it fires an error diagnostic when the fit has not found a
common frame. See `limitations.md`.
