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

## The four readings that see what the means hide

Every producer of `sparse_model/v1` publishes these, so they are comparable across
modules in a way a module's own metrics are not. Each exists because a scalar the
type already published was concealing something:

- **`min_frame_points`** — the emptiest registered camera. `registered_images`
  counts a camera holding almost no structure exactly like a well-covered one, and
  a whole-model `point_count` cannot be moved by one starved view. This is the
  reading that predicts a view failing downstream while every headline looks fine.
- **`two_view_fraction`** — the share of points seen in exactly two views. Those
  are exactly determined, four residuals against three unknowns, so their residual
  is near zero *by construction* rather than because they are good. On a
  two-view-dominated cloud they drag the mean down and the model reads better than
  it is.
- **`p95_reprojection_error`** — separates a uniformly mediocre model from a good
  model carrying a few bad points. The two want opposite responses, and the mean
  cannot tell them apart.
- **`p05_triangulation_angle`** — the weak end of the parallax distribution. A
  point on near-parallel rays sits at an ill-determined depth while reprojecting
  beautifully into the views that placed it, so it is invisible to every
  reprojection metric, and a median cannot see a tail. Where this reading is low,
  the cloud's SHAPE is uncertain in a way its error does not report.

`mean_reprojection_error` here is the **per-point** mean. It is worth knowing why
that is stated: producers of this type once published three different populations
under the one name — points, observations, and a frame that was not published at
all — and the spread was wide enough to invert a head-to-head comparison. An
observation mean weights long tracks, and long tracks are the higher-error points.

**Take them before choosing what comes next.** They describe the artifact rather
than the process that made it, so they are the honest basis for comparing this
module's output against another producer's — which the module-specific metrics,
measuring different things under similar names, are not.
