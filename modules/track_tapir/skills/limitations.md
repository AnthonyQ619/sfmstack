---
module: FeatureTrackTapir
module_version: 1.0.0
curated_at: 2026-08-11
---

# What FeatureTrackTapir cannot do

## Positions are coarse, and the track metrics hide it

The model runs at a small square resolution and everything it predicts inherits
that. Measured on 8 DTU views at 1024 px, against the same tracks through the same
triangulator: 1548 points at 1.581 px with `yield` 0.566, against
`FeatureTrackUnionFind`'s 4671 at 0.280 px with `yield` 0.993.

**Every track metric looks excellent while this is true** — `avg_track_length`
5.98, `long_track_fraction` 0.927, `track_survival_5` 0.754, all far ahead of every
other tracker here. Length and precision are separate axes, and this module is at
one end of both.

**Escape when precision is what matters:**

```
find(produces="tracks/v1", consumes="pairwise_matches/v1")
```

## Image order is input

TAPIR reasons about a point's trajectory over time. The set is fed in scene order,
so that order is a real parameter of the problem — unlike for a matcher, or for
`FeatureTrackVGGSfM`, neither of which has any notion of sequence.

On a shuffled or genuinely unordered collection the model is being shown motion
that does not exist, and it will still return tracks. `mostly_occluded` on a
capture that should be continuous is the symptom worth acting on.

## Coverage follows the query frames

Nothing is tracked into a frame no query frame can reach. `min_frame_observations`
is the metric, `thin_frame` is the diagnostic, and the fix is a query frame near
the starved one rather than a lower threshold.

## It cannot beat the detector

Query points are the detector's keypoints. Structure no detector fired on is
tracked by nothing here.

**Escape:** a detector-free matcher.

```
find(produces="pairwise_matches/v1", consumes="scene/v1")
```

## The resize is anisotropic

Images are squeezed into a square, so a 4:3 scene is distorted before the model
sees it. That costs tracking quality on a non-square capture.

It does **not** cost correctness. TAPIR predicts positions, not intrinsics, so the
inverse map is exact and the round trip through scene pixels is lossless. This is
the same operation that was a genuine bug in the VGGT modules, and the difference
is worth being explicit about: a model that predicts `fx == fy` cannot express what
an anisotropic squeeze does to a camera. There is no camera here.

## Uniform resolution only

Every image is stacked into one video tensor, so the module refuses a
mixed-resolution scene rather than silently resizing.

## `inconsistent_rate` cannot detect anything here

One query point yields one position per frame, so a track cannot contradict
itself. The metric is required by `tracks/v1` and is structurally zero.
`duplicate_track_rate` is the failure this module actually has — the same physical
point split across query frames — and it is the one `FeatureTrackUnionFind`'s
metric is blind to.

## Not the tapnet the package advertises

The image installs `tapnet` with `--no-deps` and adds only `dm-tree` and
`einshape`, because the package is JAX-first and none of that stack is on the
torch code path. Anything in `tapnet` outside `tapnet.torch` will fail to import
here. That is deliberate: the alternative is a 2 GB JAX install sitting unused
beside torch, with two frameworks competing for the same GPU allocator.
