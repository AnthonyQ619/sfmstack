---
module: PoseEssentialToPnP
module_version: 1.0.0
curated_at: 2026-08-07
---

# Tuning PoseEssentialToPnP

Work in this order. A weak seed pair cannot be repaired by anything later, so it
comes first.

1. Did it seed well? `init_pair_angle` should be comfortably above `init_min_angle_deg`.
2. `registered_fraction` == 1.0?
3. `mean_reprojection_error` below ~1px, and `median_triangulation_angle` above 3°?
4. Only then look at `points_triangulated` / `track_utilization`.

## Reference run

DTU scan1, 12 contiguous images (`sampling: head`), `max_edge: 1024`, SIFT at
defaults, FeatureMatchNN `pairing: exhaustive`, everything here at defaults:

| metric | value |
|---|---|
| `init_pair_angle` | 25.0° (seeded on images 0 and 8) |
| `registered_fraction` | 1.0 (12/12) |
| `points_triangulated` | 6893 |
| `track_utilization` | 0.983 |
| `mean_reprojection_error` | 0.441 px |
| `median_triangulation_angle` | 15.46° |
| runtime | 2.0 s |

Note the seed pair: images **0 and 8**, not 0 and 1. The scorer deliberately
prefers parallax over match count, and on a turntable capture the adjacent pair
has the most matches and the least baseline. If you see it seeding on adjacent
frames on a capture with real motion, that is worth investigating.

## `registered_fraction` below 1.0

Some image had fewer than `min_pnp_inliers` 2D-3D correspondences, or PnP RANSAC
could not find a consistent pose.

Check, in this order:

1. **The tracker's `min_frame_observations`** for the missing frames. A frame the
   tracker barely covers cannot be registered — that is a matching problem two
   stages upstream, not a PnP problem.
2. **The matcher's `window` / `graph_components`.** A frame in its own component
   shares no structure with the model and can never register.
3. **`min_pnp_inliers`** last. Lowering it registers more images by accepting
   weaker evidence, and an image registered at the wrong pose is worse than an
   image left out — it contributes wrong observations to every point it sees.

## `mean_reprojection_error` above 2

- Raise `min_triangulation_angle_deg`. Points from near-parallel rays have huge
  depth uncertainty and drag every pose that later registers against them. This is
  usually the fix.
- Tighten `max_reprojection_error` so bad points are discarded rather than kept.
- Then run global bundle adjustment. This module is greedy and never revisits a
  point once accepted; BA is what corrects the accumulated drift. On the reference
  run BA took 0.376 → 0.253px, a 33% reduction, on a scene whose per-stage numbers
  already looked healthy.

## `median_triangulation_angle` below 3

The structure is poorly conditioned in depth. This can coexist with excellent
reprojection error — a point far along a near-degenerate ray reprojects perfectly
into both views that created it and is still in the wrong place.

Raise `min_triangulation_angle_deg` to 3-5. Expect `points_triangulated` to fall;
that is the trade, and it is the right one if you intend to measure anything.

No parameter recovers missing parallax. See
[limitations](limitations.md#degenerate-captures).

## Local BA — what it buys, measured

Registration is interleaved with a bundle adjustment over the last
`local_ba_window` cameras in **registration order**. This is drift control, not
polish: each new pose is estimated against structure that earlier poses
triangulated, so an error early becomes the frame everything later lives in.

Measured on DTU scan1 at `max_edge: 1024`, `pairing: exhaustive`, everything else
at defaults. `final err` is after `BundleAdjustmentGlobal`:

| stack | images | `local_ba` | registered | pose err | final err | points | pose time |
|---|---:|---|---:|---:|---:|---:|---:|
| SIFT + NN | 16 | off | 16 | 0.647 px | 0.236 px | 8749 | 3.0 s |
| SIFT + NN | 16 | **on** | 16 | **0.551 px** | 0.248 px | 8878 | 10.2 s |
| SIFT + NN | 49 | off | 49 | 0.728 px | 0.250 px | 18405 | 11.1 s |
| SIFT + NN | 49 | **on** | 49 | **0.654 px** | 0.262 px | 19235 | 27.1 s |
| SuperPoint + LightGlue | 16 | off | 16 | 1.068 px | 0.657 px | 1627 | 0.9 s |
| SuperPoint + LightGlue | 16 | **on** | 16 | **0.843 px** | 0.669 px | 1672 | 2.5 s |
| SuperPoint + LightGlue | 49 | off | **34** | 0.945 px | 0.628 px | 1014 | 0.9 s |
| SuperPoint + LightGlue | 49 | **on** | **48** | 0.888 px | **0.600 px** | 1380 | 2.0 s |

Read the last two rows first. On the full learned sequence, local BA is the
difference between **34 and 48 of 49 images registered** — drift compounded until
PnP could no longer find `min_pnp_inliers` correspondences, and registration
stalled. That is the failure this parameter exists to prevent, and it is invisible
in every other metric: the 34-image model's reprojection error (0.945 px) is
*better* than the 48-image model's (0.888 px is close, and a smaller model is an
easier one). `registered_images` is the metric that catches it.

Two honest qualifications:

- **`local_ba_gain_px` is four times larger on the learned stack** (0.34-0.39 px
  per solve vs 0.08-0.17 px classical), which is the quantitative form of the
  reason this matters most with learned detectors and trackers: their matches are
  dense and confident enough that PnP reports healthy inlier counts on a pose that
  is already drifting.
- **After global BA the final error is a wash on the sets that fully register.**
  Where every image registers either way, global BA absorbs the difference —
  0.236 vs 0.248 px classical at 16 images, with the *on* run carrying 1.5% more
  points, which is most of that gap. Local BA is not buying final accuracy on a
  short well-connected set. It is buying the model that global BA gets to start
  from, and on the long learned sequence that is 14 more cameras.

So: leave it on, and do not expect the final number to move on an easy scene.

## `local_ba_gain_px` at or below zero

The solves are running and not lowering window reprojection error.

- **If `mean_reprojection_error` is already low, this is the healthy end state.**
  There is no drift to remove. It is an `info` diagnostic, not a warning, for
  exactly this reason.
- **With `local_ba_robust_loss: true` the metric can go slightly negative and the
  solve still be correct.** Ceres is minimising the Cauchy cost; this metric reports
  the raw mean. A solve that pulls the bulk of the residuals down while letting a
  few outliers grow does the right thing and reads as a small negative here.
- **If it is strongly negative** (worse than about -0.05 px consistently), suspect
  the window instead: `local_ba_window` below ~5 leaves almost no freedom after the
  two fixed cameras, so the solve can only move structure.

Turning `local_ba` off because this metric is near zero saves runtime and gives up
the protection on the frames where it *would* have mattered. Prefer raising
`local_ba_interval`.

## Local BA is not converging

Ceres hit `local_ba_max_iterations` (default 25). Unlike the global module, this is
often not worth fixing by raising the cap — the solve runs tens of times and a
partial solve still removes most of the drift.

Act on it when it fires on *most* runs rather than a few:

1. **Narrow `local_ba_window`.** A wide window is a harder problem per solve, and
   the drift it corrects is mostly local anyway. 8 → 6 is usually enough.
2. **Then raise `local_ba_max_iterations`** to 50. Watch runtime: this multiplies
   by the number of registrations.
3. **Check `local_ba_loss_scale`.** A scale far above the residuals makes the loss
   effectively quadratic and lets outliers dominate the solve, which is a common
   way to make it converge slowly.

## `track_utilization` low

With good reprojection error, the filters are simply strict — fine. With bad
reprojection error, the tracks are wrong; check the tracker's `inconsistent_rate`
and the matcher's `inlier_ratio` before touching anything here.

## Cost

The reference run is 2.0s for 12 images and 7014 tracks. The dominant costs are
the seed search (quadratic in image count, though only over pairs with enough
shared tracks) and the triangulation sweep after each registration, which is re-run
from scratch every round. Past ~100 images that sweep dominates; the fix would be
incremental rather than full re-triangulation, which is a code change, not a
parameter.
