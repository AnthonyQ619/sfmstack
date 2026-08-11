---
module: SparseMapAnything
module_version: 1.0.0
curated_at: 2026-08-11
---

# Tuning SparseMapAnything

1. `depth_scale_spread` — do the learned depth and the supplied poses agree up to
   one scalar at all?
2. `yield` — how much of the tracker's work survived.
3. `conditioned` — because every other number moves with it.
4. Only then `mean_reprojection_error`.

## Reference run

DTU scan1, 8 contiguous images at `max_edge: 1024`, SIFT tracks, poses from
`PoseEssentialToPnP`, on one A6000 in a container:

| metric | conditioned | not conditioned |
|---|---:|---:|
| `point_count` | 3047 | 2198 |
| `yield` | **0.648** | 0.467 |
| `mean_reprojection_error` | 1.060 | 1.023 |
| `depth_scale` | 1.9496 | 1.9485 |
| `depth_scale_spread` | **0.0059** | 0.0071 |
| `mean_depth_confidence` | 13.97 | 9.82 |
| `rejected_outside_frame` | 40 | 39 |
| `rejected_masked` | 0 | 0 |
| runtime | 30 s cold, 3 s warm | 3 s |

## `condition_on_poses` — the first thing to try, and the first thing to suspect

**On, when the poses are good.** 39% more surviving structure for nothing.

**Off, when the poses are suspect.** Conditioning on a wrong pose propagates that
error into the depth, and the two then agree with each other rather than with the
scene — `depth_scale_spread` looks *fine* while the cloud is wrong, because the
spread measures self-consistency.

The diagnostic procedure: run it both ways. If the spread is **worse** conditioned
than not, the poses are the problem, not the model. That comparison is the reason
`conditioned` is reported as a metric rather than left in the parameters.

## `min_confidence` — read the metric first, and do not carry it from SparseVGGT

MapAnything's confidence is unbounded above and starts near 1, so it is not a
probability. Its magnitude differs from VGGT's by nearly a factor of five on the
same scene: **13.97 here, 60.60 in `SparseVGGT`**. A threshold copied across
rejects everything.

The procedure is the same as for `SparseVGGT`: run once at 0, read
`mean_depth_confidence`, set the threshold as a fraction of it. Note it also moves
with `condition_on_poses` — 9.82 to 13.97 — so a threshold tuned unconditioned is
too low once conditioning is on.

## Nothing survives

The error message names the dominant rejection filter. In order of likelihood:

**`confidence`** — almost always a threshold carried over from `SparseVGGT`. Set
`min_confidence: 0` and re-read.

**`reprojection`** — the depth and the poses disagree. Check `depth_scale_spread`
first: if it is small the depth is consistent with the poses and
`max_reprojection_error` is simply tight; if it is large, no single scale fits and
the fix is upstream.

**`masked`** — MapAnything rejected the regions the tracks are in. Expected on sky
and on object silhouettes. `use_model_mask: false` keeps them, at the cost of
points sampled across depth discontinuities.

**`outside`** — observations fell outside the model's centre crop. 40 of 4703 on
the reference run, which is the few pixels upstream's resolution table trims off
the long side. A large number means the scene's aspect ratio is far from anything
in that table.

**`short`** — the tracker, not this module.

## The cloud is smaller than SparseTriangulation's and that is not a bug

3047 against 4671 on the reference run. A geometric triangulator *placed* each
point to minimise reprojection error; this one predicted a depth and then measured
the error, so the same `max_reprojection_error: 4.0` rejects far more. Raising the
threshold recovers points of correspondingly lower quality — it does not make the
two comparable.

## Memory

`memory_efficient_inference: true` before `max_images_per_pass`. The first trades
speed for peak memory and changes nothing about the result; the second changes
what the model can attend to and therefore the depth it predicts.
