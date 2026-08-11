---
module: FeatureTrackVGGSfM
module_version: 1.0.0
curated_at: 2026-08-11
---

# What FeatureTrackVGGSfM cannot do

## Coverage follows the query frames

Nothing is tracked *to* a frame that no query frame can see. A capture that turns a
corner, or one where the query set lands on one side of an object, leaves the rest
thin — and the totals will look fine while one frame carries almost nothing.

`min_frame_observations` is the metric, `thin_frame` is the diagnostic, and the fix
is always a query frame near the starved one rather than a lower threshold.

## It cannot beat the detector

Query points are the detector's keypoints. A frame where the detector found nothing
contributes no query points, and structure no detector ever fired on is not tracked
by anything here.

**Escape:** a detector-free matcher, which finds correspondences without keypoints.

```
find(produces="pairwise_matches/v1", consumes="scene/v1")
```

## Positions are predicted, not matched

A matched keypoint sits where the detector put it in both frames; a tracked one
sits where the network says it should be. Measured on DTU that costs about 0.2 px
of triangulation error — 0.502 against 0.280. On a scene where the matcher works,
this trades precision for length. On one where it does not, there is no trade.

## Uniform resolution only

Every image is stacked into one tensor and tracked across the stack, so the module
refuses a mixed-resolution scene rather than silently resizing. Re-run
`SceneLoader` with a fixed resize.

## Memory scales with the scene's resolution

No downscaling happens here: the tracker runs at the scene's working resolution so
that query points need no coordinate mapping, and there is therefore no mapping to
get wrong. The cost is that a 4K scene is a 4K forward pass.
`max_query_points_per_frame` is the knob, and it trades points rather than pixels.

## No per-observation score

The vendored tracker calls `refine_track` with `compute_score=False`, so the score
head is not run and there is no score threshold to set. Visibility is the only
per-observation number, and it is written into the artifact.

## `inconsistent_rate` cannot detect anything here

Each query point yields at most one position per frame, so a track cannot be
observed twice in the same image. The metric is required by `tracks/v1` and is
structurally zero for this module.

Its counterpart failure — one physical point split across several tracks — is what
this module actually does wrong, and `duplicate_track_rate` measures it. The two
trackers are blind to opposite halves of the same problem.

## Cost grows quadratically with the image count

Every query frame's points are tracked into every frame, so at a fixed *fraction*
of frames used as queries the cost is quadratic. A 200-image set is not a matter of
raising `query_frame_num` — keep the query count fixed and accept that coverage
thins, or reach for a sequential matcher and union-find.
