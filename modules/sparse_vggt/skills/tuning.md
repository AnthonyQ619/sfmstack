---
module: SparseVGGT
module_version: 1.1.0
curated_at: 2026-08-11
---

# Tuning SparseVGGT

1. `depth_scale_spread` — whether the module's central assumption holds at all.
2. `scale_samples` — whether the scale rests on enough evidence.
3. `mean_depth_confidence`, then `min_confidence`.
4. `single_view_points` — how much of the cloud is unverified.

## Reference run

One capture: a short contiguous arc of twelve calibrated frames around a small,
well-textured object on a plain backdrop, at about 1 MP, classical detector +
exhaustive ratio-test matcher, 7014 tracks, defaults, GPU, in a container.

| poses from | `depth_scale` | `spread` | `samples` | points | error | `mean_track_length` | `yield` |
|---|---:|---:|---:|---:|---:|---:|---:|
| `PoseEssentialToPnP` | 2.1164 | 0.004 | 7014 | 5358 | 0.967 px | 3.21 | 0.764 |
| `PoseVGGT` | 1.0044 | 0.004 | 7014 | 4005 | 1.285 px | 2.67 | 0.571 |

Two things worth reading off that table.

**`depth_scale` of 1.0044 on VGGT's own poses.** Fed poses from the same model
that produced the depth, the estimator recovers unity — the units already agree.
That is the check that the scale machinery is right rather than merely producing a
number, and it is worth re-running if this module is ever changed.

**`depth_scale` of 2.1164 on classical poses.** VGGT's depth unit is about half
the classical estimator's scale unit here, and neither is metric. The scale is a
property of the PAIR, not of either input.

## `depth_scale_spread` above 0.25

The ratio of triangulated depth to predicted depth varies across the scene, so one
scalar does not relate them. The cloud will be locally plausible and globally
distorted — the failure that looks fine in a viewer and is wrong when measured.

1. **Check the pose estimator's `mean_reprojection_error` first.** Wrong poses
   produce a varying ratio, and the fault is not here.
2. **Use `PoseVGGT`** so depth and poses come from the same model, where the ratio
   is 1 by construction.
3. **Or use `SparseTriangulation`,** which needs no depth prior at all.

At 0.004 on both runs above, this is comfortably inside the band; a spread
that size means the depth prior and the geometry genuinely agree.

## Nothing survives

Read the rejection counts in the note before touching a threshold.

- **`rejected_cheirality` dominant.** Points landed behind cameras: the depth prior
  and the poses disagree about which side of the camera the scene is on. Check
  `depth_scale_spread` — this is usually the same problem seen from another angle.
- **`rejected_reprojection` dominant.** The depth is inconsistent with the poses at
  the scale that was fitted. Raise `max_reprojection_error` only after checking the
  spread.
- **`rejected_confidence` dominant.** `min_confidence` is too high. VGGT's
  confidence is unbounded above and near 1 on data it handles well; it is not a
  0–1 probability, so read `mean_depth_confidence` from a run before setting it.

## `min_track_len` — the parameter that is different here

Defaults to **1**, where every geometric triangulator defaults to 2, because this
module can place a point from a single observation. That is the capability, and it
is unverified by construction: nothing checked the point against a second view.

Raise it to 2 when the cloud feeds bundle adjustment, and watch `point_count` fall
by whatever `single_view_points` was. Keep it at 1 when coverage matters more than
verification — the weakly-textured case this module exists for.

## `max_reprojection_error` bites differently here

Same default as the geometric triangulators, deliberately, so the three are
comparable. But a geometric triangulator MINIMISED this error when it placed the
point, and this module did not — it placed the point where the depth prior said
and then measured. The same threshold therefore rejects more, and
`mean_reprojection_error` comes out higher on identical tracks. That is not the
module working badly; it is a more honest quantity.

## Cost

25 s for 12 images on an A6000, most of it the aggregator; a second run against a
warm server is 3 s, since the depth maps are the only per-job work. Cost grows
with image count, not with track count.

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

## What here rests on nothing — the manifest audit

Audited against this module's own manifest. **Eleven healthy bands**
(`min_frame_points`, `two_view_fraction`, `p95_reprojection_error`,
`p05_triangulation_angle`, `point_count`, `observation_count`, and five more)
declare a range no diagnostic reads — descriptions of the captures measured so
far, not judgements on yours, and this module has run **zero times** in a real
pipeline, so they come from isolated testing. The numbers in the
`min_track_len` and `min_confidence` advice are settings that worked in that
isolated testing, not published results.
