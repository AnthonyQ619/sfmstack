---
module: SparseVGGT
module_version: 1.0.0
curated_at: 2026-08-11
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
