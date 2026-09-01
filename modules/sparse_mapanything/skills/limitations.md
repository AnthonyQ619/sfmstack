---
module: SparseMapAnything
module_version: 1.1.0
curated_at: 2026-08-11
---

# What SparseMapAnything cannot do

## One scale for the whole scene

The module relates MapAnything's depth unit to the poses' unit with a single
scalar. That is exact only if the ratio is constant across the scene, and
`depth_scale_spread` is the measurement of whether it is — 0.0059 on the reference
run, which is very tight.

When it is large, no scalar fits: the cloud comes out locally right and globally
distorted, near surfaces pulled in and far ones pushed out. Nothing downstream can
undo it, because the information needed to undo it is not in the artifact.

**Escape:** a geometric triangulator, which needs no depth prior.

```
find(produces="sparse_model/v1", consumes="tracks/v1")
```

## Conditioning can make the poses look right when they are wrong

The model accepts the supplied poses and predicts depth consistent with them. If
those poses are wrong, the depth is wrong *in the same way*, and
`depth_scale_spread` — which measures agreement between the two — stays small. The
metric that would catch the problem is the one conditioning defeats.

This is why `conditioned` is a metric and why the tuning skill says to run it both
ways: a spread that is worse conditioned than unconditioned is the signal, and it
is the only one this module has.

## It cannot estimate its own poses here

MapAnything can reconstruct without poses, and this module does not expose that.
`poses` is required, so the module stays interchangeable with the other three
triangulators, and so the output frame has exactly one meaning.

A no-pose path would put the cloud in MapAnything's own frame, which is a
different contract wearing the same type. That silent switch is the failure mode
`SparseVGGT` was written to avoid.

**Escape when there are no poses:** `PoseVGGT` first, or `SparseGlobalCOLMAP`,
which estimates poses internally by design.

## The output is not metric, even though the model is

MapAnything predicts metric depth. That metric information is discarded here,
because the cloud is placed in the supplied poses' frame and those are in
arbitrary SfM units. `is_metric_scale` is hardcoded false for the same reason —
telling the model the poses are metric makes it rescale its depth to honour a
false claim, and measured, that moved the scale from 1.9495 to 1.3205 and worsened
the spread.

A pipeline that wants metric output would need a module that keeps MapAnything's
frame rather than adopting the poses'. That module does not exist here.

## Single-view points are unverified

A track seen once still gets a 3D point, because depth was predicted rather than
intersected. That is a real capability no geometric triangulator has, and nothing
checked those points against a second view. `single_view_points` is the count, and
`min_track_len: 2` turns the capability off.

## Accuracy is the depth prior's

On a calibrated, well-textured scene it is worse than ray intersection on every
axis — 3047 points at 1.060 px against 4671 at 0.280 px on the reference run. It
is not competing there. It is for the case where the correspondences are too few
or too weak for intersection to work at all.

## Only posed views contribute

An image with `valid=False` in the pose artifact takes no part: its observations
cannot place a point, and it is not shown to the model either. Coverage follows the
pose estimator's `registered_fraction`.

## The centre crop loses a few pixels

Upstream's resolution table maps each aspect ratio to a fixed size and centre-crops
to reach it — 4:3 becomes 518x392, which trims about 5 pixels off the long side.
Observations landing there are dropped rather than clamped to the border, which
would sample an unrelated depth. `rejected_outside_frame` counts them: 40 of 4703
tracks on the reference run.
