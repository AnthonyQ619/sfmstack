---
module: SparseMapAnything
module_version: 1.0.0
curated_at: 2026-08-11
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

On DTU it removed **nothing** — the pixels it rejects are the ambiguous ones,
which are also the low-confidence ones, and this module picks the
highest-confidence observation per track. Expect it to matter on a scene with sky,
or one where tracks sit on object silhouettes.

`rejected_outside_frame` is a **different** number with a different fix: those
observations fell outside the centre crop upstream's resolution table imposes.

## Single-view points are real structure and unverified

A point resting on one observation was placed from one depth prediction and
checked against nothing. `single_view_points` is the count. No geometric
triangulator can produce these; nothing verified them either.

## Metrics that mislead

**`mean_depth_confidence` is not comparable to `SparseVGGT`'s.** Same name,
different scale — 13.97 against 60.60 on the same scene. Both unbounded
self-reports.

**`depth_scale` is not quality.** It is the unit conversion, and it changes with
the pose source, not with how good the reconstruction is.

**`depth_scale_spread` can be small for the wrong reason.** It measures agreement
between the depth and the poses, and conditioning makes the depth agree with the
poses by construction. See
[limitations](limitations.md#conditioning-can-make-the-poses-look-right-when-they-are-wrong).

**`mean_reprojection_error` is not comparable to a geometric triangulator's.**
That one minimised this quantity when placing each point; this one predicted a
depth and then measured it. Comparing them compares the objective, not the result.

**`point_count` is not comparable across `max_reprojection_error`** — and this
module is far more sensitive to that threshold than a geometric triangulator, for
the same reason.
