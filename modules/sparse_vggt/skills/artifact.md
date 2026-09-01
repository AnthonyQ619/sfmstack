---
module: SparseVGGT
module_version: 1.1.0
curated_at: 2026-08-31
---

# Reading a SparseVGGT artifact

## Layout

`sparse_model/v1`: `points` (xyz, rgb, error), `observations`, `poses` (copied
through from the input unchanged), and `intrinsics` (whatever K was used).

## The cloud is in the SUPPLIED poses' frame

Not VGGT's. This is the whole design: depth is unprojected with the supplied
cameras, so the output is in their frame and their scale whatever produced them.
`depth_scale` is the scalar that got it there, and it changes with the pose source
— 2.1164 against classical poses, 1.0044 against VGGT's own on the same scene.

## `intrinsics` records which K was used

The module prefers the K the POSE artifact carries over the scene's calibration,
because a pose estimator that estimated intrinsics wrote the ones its cameras are
consistent with. Writing the choice into the artifact means a downstream module
cannot silently disagree about it.

## Single-view points are real structure and unverified

`min_track_len` defaults to 1, so a track seen once yields a point. No geometric
triangulator can do that and nothing here checked it. `single_view_points` is the
count, and it is the part of the cloud that rests entirely on the prior.

## Metrics that mislead

**`mean_reprojection_error` is not comparable to a geometric triangulator's.**
That one placed each point to minimise this error; this one placed the point where
the depth said and then measured. Higher here is expected and is a more honest
number.

**`mean_track_length` below 2.0 is legal here** and impossible in a geometric
triangulator. Read `single_view_points` beside it.

**`depth_scale` is not quality.** It is what makes the two inputs comparable at
all. `depth_scale_spread` is the quality signal.

**`mean_depth_confidence` is unbounded above** and near 1 on data VGGT handles
well. It is not a probability and not comparable to any other module's confidence.

**`rejected_cheirality` here means something different** than in a geometric
triangulator. There it means the poses disagree with each other; here it means the
depth prior and the poses disagree about which side of the camera the scene is on,
which is usually a scale problem wearing a different hat.

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
