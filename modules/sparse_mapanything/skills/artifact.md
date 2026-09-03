---
module: SparseMapAnything
module_version: 1.1.0
curated_at: 2026-08-31
---

# Reading a SparseMapAnything artifact

## Layout

`sparse_model/v1`: `points` (xyz, rgb, error), `observations`, `poses`, and
`intrinsics`.

The `poses` are **copied from the input unchanged**, and the `intrinsics` are the
ones the unprojection used — not MapAnything's own recovered values, even when the
model was allowed to recover them. Writing the model's would describe a camera the
points were not placed with.

## The cloud is in the SUPPLIED poses' frame and scale

Not MapAnything's, and conditioning the model on those poses does not change that
— the measured scale is 1.9496 conditioned against 1.9485 not. `depth_scale` is
the scalar that got it there and it is always measured, never assumed.

## `conditioned` splits the run into two populations

Every number here moves with it. On the reference run, turning conditioning on
took `yield` from 0.467 to 0.648 and `mean_depth_confidence` from 9.82 to 13.97.
Two artifacts with different `conditioned` values are not comparable on any metric
except by intent.

## The model masks its own output

MapAnything returns a mask combining an ambiguity mask (sky and similar) and an
edge mask at depth discontinuities. `rejected_masked` counts tracks it removed
entirely.

On a small object against a plain backdrop it removed **nothing** — the pixels it
rejects are the ambiguous ones,
which are also the low-confidence ones, and this module picks the
highest-confidence observation per track. Expect it to matter on a scene with sky,
or one where tracks sit on object silhouettes.

`rejected_outside_frame` is a **different** number with a different fix: those
observations fell outside the centre crop upstream's resolution table imposes.

## Single-view points are real structure and unverified

A point resting on one observation was placed from one depth prediction and
checked against nothing. `single_view_points` is the count. No geometric
triangulator can produce these; nothing verified them either.
