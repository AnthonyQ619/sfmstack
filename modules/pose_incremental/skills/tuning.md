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
