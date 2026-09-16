---
module: DenseMVS
module_version: 1.0.0
upstream: colmap/colmap PatchMatch stereo, via pycolmap-cuda12 4.1.1
curated_at: 2026-08-11
sources: 3
---

## Where to go next

This file is the router. Everything below is orientation; the detail lives in the
other four documents, and this table is how to pick one without fetching all of
them.

| If | Fetch |
| --- | --- |
| a number is out of band, or a diagnostic told you to tune | **`tuning`** — 14 parameters documented, starting with `max_image_size` |
| you need to know whether this module can do the thing at all | **`limitations`** — e.g. "It cannot see what it cannot correlate" |
| you are reading what it wrote | **`artifact`** — the layout of `dense_model/v1` |
| you want to know where a claim came from, or what rests on nothing | **`sources`** — includes an audited list of what is asserted without a source |

**First readings on this module's output:** `point_count`, `views_contributing`, `mean_depth_confidence`.

**Two readings to take on the INPUT, before spending an hour here:** the sparse
model's `min_frame_points` — the thinnest view, which is the one whose depth map
comes back empty and which no whole-model total will show — and the capture's
`highlight_clipped_fraction` from `SceneTriage`, which predicted this module's own
coverage across a batch better than any parameter moved it.

**Diagnostics it can raise:** `sparse_too_thin`, `low_completeness`, `views_dropped`, `no_points`.

## What this module is for


Dense point cloud by **photometric multi-view stereo**: PatchMatch depth/normal
search per pixel, multi-view filtering, then depth-map fusion. CUDA required —
`patch_match_stereo` has no CPU path at all.

**Use when the cloud has to be right.** This is the only dense module here that
verifies its geometry against pixels. Everything it emits was correlated across
views and agreed on by at least `filter_min_num_consistent` of them.

**Use `DenseVGGT` when you want coverage fast.** MVS on 8 DTU views at 1200 px is
131 s against VGGT's 2 s warm, and MVS leaves holes wherever the evidence was
absent. **Those holes are the honest part** — see below.

**It needs a `sparse_model/v1`, not just poses**, because COLMAP derives each
view's depth search range and its source-view set from which images see which
points. The 2D coordinates are never used; the track structure is.

## Measured against DenseVGGT, same scene, same poses

8 DTU views, poses from `PoseEssentialToPnP`, `SparseTriangulation` giving 4671
verified points as the reference. Distances are in the reconstruction's units,
where the object's bounding-box diagonal is 4.6 and the median camera separation
1.7.

| | points | bbox diag | verified→cloud p50 | cloud→verified p95 | cloud >0.2 from anything verified |
|---|---:|---:|---:|---:|---:|
| **DenseMVS** (1200 px) | 122 814 | 4.26 | **0.0077** | **0.223** | **7.5%** |
| DenseVGGT (stride 3) | 179 920 | 7.24 | 0.0142 | 0.585 | 26.6% |

VGGT produced **47% more points** and covered the verified structure **half as
tightly**, in a bounding box **70% larger**. A quarter of its cloud sits far from
anything triangulation confirmed; MVS's equivalent share is 7.5%.

Not all of that difference is error — some is genuine surface SIFT never found.
The difference that matters is that MVS's extra points were photometrically
verified and VGGT's were predicted. A dense reconstructor that never leaves a hole
is not more complete; it is less willing to say it does not know.

## First numbers to read

1. **`depth_map_completeness`** — the fraction of pixels that survived filtering.
   This is the MVS health metric. 0.65 on the reference run. Near zero means the
   filters rejected everything, and *which* filter is the diagnosis:
   [tuning.md](tuning.md#nothing-survives-the-filters).
2. **`views_contributing` against `input_registered_images`** — a gap means views
   were photometrically rejected, which is a different problem from being
   unregistered.
3. **`fusion_ratio`** — valid depth pixels per fused point, ~32 on the reference
   run. Near 1 means fusion merged nothing and each view left its own copy of the
   surface.

## Plan for the runtime

Cost is roughly `views × pixels × source_views × num_samples × num_iterations`,
and `geom_consistency` doubles it by running the whole search twice.

| setting | 8 views | points | completeness |
|---|---:|---:|---:|
| 600 px, `geom_consistency: false` | 31 s | 46 562 | 0.717 |
| 600 px | 75 s | 47 172 | 0.679 |
| 1200 px | 131 s | 128 327 | 0.650 |

Scale linearly in views and quadratically in `max_image_size`. A 50-view set at
2000 px is an hour or more, not a minute — `timeout_s` is 6 hours for that reason.

**That rule was measured on one idle machine, and contention dominates it.** Across
a batch run on shared devices it under-predicted by between about one-and-a-half and
six times, and half the agents in that batch recorded the gap independently. Treat
it as a floor for planning, not an estimate.

**Reading the output:** [artifact.md](artifact.md) ·
**Tuning:** [tuning.md](tuning.md) · **Limits:** [limitations.md](limitations.md)

## Provenance

**Run over one full batch, and scored against reference geometry.** Every capture
in that batch chose this module; the claims about its runtime under contention, its
holes being photometric, and `fusion_min_num_pixels` come from it and are recorded
in `skills/evidence/dense-batch-2026-09.md`. Everything else here is still isolated
testing or carried from the predecessor codebase. Claim-by-claim citations: the
`sources` skill.
