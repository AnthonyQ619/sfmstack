---
module: SparseTriangulation
module_version: 1.1.0
curated_at: 2026-08-07
---

# Tuning SparseTriangulation

Three real parameters. Two of them trade point count against point quality, and
the right setting depends entirely on whether you intend to *measure* with the
result or merely look at it.

## Reference run

One capture: a short contiguous arc of twelve calibrated frames around a small,
well-textured object on a plain backdrop, at about 1 MP, through a classical
detector → ratio-test matcher (exhaustive) → union-find tracker → incremental
poses, all at defaults.

| metric | value |
|---|---|
| `point_count` | 6941 |
| `observation_count` | 22743 |
| `mean_reprojection_error` | 0.376 px |
| `mean_track_length` | 3.28 |
| `median_triangulation_angle` | 15.68° |
| `yield` | 0.99 |
| `rejected_cheirality` | 0.0 |
| runtime | 1.3 s |

99% yield with zero cheirality rejections is what healthy input looks like. Treat
this as the shape to compare against, not as a target to tune toward — on a harder
capture a 40% yield with 0.5px error is a *better* outcome than 99% at 3px.

## `min_triangulation_angle_deg` — the accuracy dial

Points below ~1° have depth uncertainty measured in scene diameters. They
reproject perfectly into the two views that created them and sit in the wrong
place, so they raise `point_count` while lowering the quality of everything that
later registers against them.

- **3-5** before a bundle adjustment you intend to trust.
- **2** (default) as a general working value.
- **Below 1** only to get a denser cloud you do not intend to measure with.

Read `median_triangulation_angle` in the output to see what you actually got. On
the reference run it is 15.7° — far above the 2° floor, so the filter is barely
binding and raising it costs nothing there.

## `max_reprojection_error` — applied as a MAX over views

Not a mean. One bad observation kills the point.

That is deliberate, and it is the main way this differs from a permissive
triangulator. A point with four good observations and one 20px outlier is a point
whose track is wrong; keeping it and letting BA down-weight the outlier works, but
refusing it costs nothing and removes a whole class of quiet corruption.

If `point_count` is too low while `mean_reprojection_error` is already good, this
is the filter that is binding. In working-resolution pixels, so scale it with the
scene's resize — 4px at `max_edge: 1600` is roughly 1.3px at `max_edge: 500`.

## `min_observations` — 2 or 3, and it matters

2 is the geometric minimum. A two-view point has exactly as many constraints as
unknowns, which means **bundle adjustment cannot improve it** — it can only slide
it along its ray. It adds cost to the solve without adding information.

3 is the honest floor for anything you intend to bundle-adjust. Expect
`point_count` to fall substantially; the tracker's `long_track_fraction` predicts
by how much (0.516 on the reference run, so roughly half survive).

## `mean_track_length` near 2.0

The cloud is entirely two-view. Every point is unconstrained beyond the pair that
made it and BA has no redundancy to exploit.

The fix is upstream, in the matcher's `window` — see that module's tuning file,
where a window sweep takes `long_track_fraction` from 0.06 to 0.32. Raising
`min_observations` to 3 here does not create multi-view structure, it just reveals
how little there is.

## `colour_points`

Costs one image decode per frame. Leave it on unless the cloud is a pure
intermediate: the colours are what make a sanity check by eye possible, and a
mis-signed pose is far more obvious in a coloured cloud than in any metric.

Colours are sampled from the **resized** images the scene carries, so a scene
built with `resize: none` needs the dataset reachable from this container too.

## Metrics that mislead

`yield` near 1.0 (0.99 on the reference run) means the filters are barely biting.
Good on clean input; on hard input a high yield means the thresholds are too loose.

`point_count` alone says nothing. 6941 points at 0.376px is a good model; the same
count at 3px with a 1° median angle is a bad one. Read it beside
`median_triangulation_angle`.

`mean_reprojection_error` is measured against the poses that were given, so it
cannot detect a globally wrong-but-self-consistent model. A reconstruction can be
internally consistent and still be the wrong shape.

## What here rests on nothing — the manifest audit

Audited against this module's own manifest. **Nine healthy bands**
(`min_frame_points`, `two_view_fraction`, `p95_reprojection_error`,
`p05_triangulation_angle`, `point_count`, `observation_count`, and three more)
declare a range no diagnostic reads — descriptions of the captures measured so
far, not judgements on yours. The specific numbers in the
`min_triangulation_angle_deg` and `min_observations` advice are settings that
worked here, not published results.
