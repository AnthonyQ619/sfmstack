---
module: SparseTriangulationGTSAM
module_version: 1.1.0
curated_at: 2026-08-10
---

# Tuning SparseTriangulationGTSAM

The filters are the same as `SparseTriangulation`'s and behave the same way, so
that file's guidance transfers. What is specific here is the estimator and the
distance bound.

1. `mean_track_length` — below ~2.2, use the cheaper module and stop.
2. `yield` and the four `rejected_*` counts — they say WHICH filter is biting.
3. `median_triangulation_angle` — the honest conditioning signal.
4. `refinement_shift` — whether the linear solve was well posed at all.

## Read the gain at the right place, and against the right baseline

Comparing this module with `SparseTriangulation` on an overall median will tell you
nothing, and will usually tell you nothing in a confident tone. Two-view points are
the same computation in both, and they are typically the majority — on union-find
tracks, 2678 of 4558 paired points. **Split by observation count before comparing:**
identical at 2, ~5% better at 3–4, 12–21% better at 5+.

And compare the same points. The two keep different sets, so pair on `track_id`;
an unpaired comparison after bundle adjustment reports this module as *worse*,
because it retained more points and the extra ones are the hard ones — measured at
roughly five times the model's mean error on the points only this module keeps. How
MANY extra points is bounded by what the pairwise path was discarding; see SKILL.md.
On one capture those extras were the model's worst 2%, so more is not automatically
better here.

**`optimize: false` is worth trying and usually free.** On every scene measured it
matched `optimize: true` to four decimals at half the runtime (1.38 s against
2.91 s). `refinement_shift` is how you check that on your own data — near zero
means the linear solve had already arrived and the refinement is pure cost.

## Reference run

One capture: a short contiguous arc of twelve calibrated frames around a small,
well-textured object on a plain backdrop, at about 1 MP, classical detector + ratio-test matcher
`pairing: exhaustive`, poses from `PoseEssentialToPnP`, everything here default:

| metric | value |
|---|---|
| `point_count` | 6949 |
| `observation_count` | 22784 |
| `mean_track_length` | 3.28 |
| `mean_reprojection_error` | 0.391 px |
| `median_triangulation_angle` | 15.53° |
| `refinement_shift` | 0.000000 |
| runtime | 2.0 s |

## `refinement_shift` at or near zero

The nonlinear refinement did not move the linear solution. **This is the healthy
reading** — LOST is designed to land close to the optimum, and on well-conditioned
data it does.

It is genuinely measuring something. On a synthetic four-view configuration with
1.5 px of measurement noise, refinement moves the LOST answer by 0.0013 scene
units and the plain-DLT answer by 0.00004 — the two start in different places and
converge to nearly the same one. On a well-conditioned small-object capture the
median relative shift is below 1e-6 of
the scene extent, which rounds to zero at the reported precision.

Act on it when it is **large** (above ~0.05 of the scene extent): the linear
solutions were poorly conditioned, and the fix is `min_triangulation_angle_deg`,
not more refinement.

## Nothing survives

Every track was rejected. Read the `rejected_*` counts before touching a
threshold — they say which filter did it:

- **`rejected_cheirality` dominant.** Points landed behind cameras. This is
  almost always wrong POSES, not thresholds. Check the pose estimator's
  `mean_reprojection_error` and `registered_fraction` first; the module raises a
  `bad_poses_suspected` warning past 20%.
- **`rejected_angle` dominant.** The capture has too little baseline for the
  threshold. Lower `min_triangulation_angle_deg` toward 1.0 and accept worse depth.
- **`rejected_reprojection` dominant.** Either the tracks are wrong (check the
  tracker's `inconsistent_rate`) or the threshold is too tight for the working
  resolution. It is in WORKING pixels.
- **`solve` failures in the note dominant.** Rank-deficient systems: the observing
  views are near-coincident. Same fix as `rejected_angle`.

## `median_triangulation_angle` below 3

The structure is poorly conditioned in depth. This can coexist with excellent
reprojection error — a point far along a near-degenerate ray reprojects perfectly
into the views that created it and is still in the wrong place.

Raise `min_triangulation_angle_deg` to 3–5, and consider `max_landmark_distance`:
the angle filter catches most escaping points and the distance bound catches the
ones that squeak past it.

## `max_landmark_distance`

**Scale is arbitrary.** The pose estimator fixes the seed pair's baseline to 1.0,
so this parameter is a multiple of that baseline and not a distance in metres. A
value that works on one reconstruction is meaningless on another with a different
seed pair.

Leave it at 0 until you have looked at the cloud. On a turntable capture where the
cameras sit roughly one baseline apart, 50–200 bounds the scene generously. Set it
too tight and `rejected_distance` eats real structure silently — it is the one
filter here whose threshold has no natural units.

## `use_lost` and `optimize`

Both on. Turning `use_lost` off turns this module into a multi-view DLT, which is
still more than the pairwise path uses but throws away the weighting that is the
reason to be here. The honest way to find out what LOST buys on your data is to
run both on the *same* tracks and poses and compare `point_count` — the artifact
ids differ by that one parameter, so the comparison is exact.

## Cost

2.0 s against 1.5 s for the pairwise module on 12 images and 7014 tracks — about
1.3x here, and it grows with `mean_track_length` because LOST solves over every
observing view. On a long sequence with deep tracks expect 3–5x. That is still
small next to matching, and the module is not where a slow pipeline is slow.
