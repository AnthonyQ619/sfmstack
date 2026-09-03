---
module: SparseGlobalCOLMAP
module_version: 1.1.0
upstream: pycolmap 4.1.1 global mapping (GLOMAP)
curated_at: 2026-08-10
sources: 3
---

## Where to go next

This file is the router. Everything below is orientation; the detail lives in the
other four documents, and this table is how to pick one without fetching all of
them.

| If | Fetch |
| --- | --- |
| a number is out of band, or a diagnostic told you to tune | **`tuning`** — 10 parameters documented, starting with `min_num_matches` |
| you need to know whether this module can do the thing at all | **`limitations`** — e.g. "What global cannot recover from" |
| you are reading what it wrote | **`artifact`** — the layout of `sparse_model/v1` |
| you want to know where a claim came from, or what rests on nothing | **`sources`** — includes an audited list of what is asserted without a source |

**First readings on this module's output:** `min_frame_points`, `two_view_fraction`, `p95_reprojection_error`.

**Diagnostics it can raise:** `uncalibrated_scene`, `no_verified_pairs`, `graph_thinned_by_verification`, `partial_registration`, `split_into_models`, `high_reprojection_error`.

## What this module is for


Global reconstruction: rotation averaging over the whole view graph, global
camera positioning, then triangulation and bundle adjustment. CPU-only, no
weights. **It estimates poses itself** — nothing upstream should.

**Use when** the capture is unordered or large, or when `PoseEssentialToPnP`
reports a low `registered_fraction` on a set whose view graph is connected.
Incremental registration stalls when the next image shares too little with what
is already built; global positioning has no such notion.

**Prefer incremental when** you need per-image evidence for a debugging pass, or
the capture is a short ordered sequence where incremental is both fast and easy
to reason about. On one twelve-frame contiguous arc the two land in the same place and
incremental tells you more about how it got there.

**It consumes `pairwise_matches/v1`, not tracks.** Rotation averaging operates on
relative poses between pairs, and a tracker has already discarded which pair an
observation came from. Wiring a tracker in front of this is not a slower path —
it is not a path.

**The three metrics that matter most, in order:**

1. `verified_pairs` against the matcher's `pairs_matched` — this module verifies
   the graph again, more strictly, and the gap is its own rejection.
2. `registered_fraction` — below 1.0, read `largest_component_fraction`, not the
   parameters here. A split graph cannot become one model.
3. `mean_reprojection_error` — and never compare it against a model with a
   different `registered_images`.

**Cheapest thing that usually works:** defaults. On one short contiguous arc of
twelve calibrated frames around a small, well-textured object on a plain backdrop,
at about 1 MP with a classical detector + exhaustive ratio-test matcher, that is
63 of 64 pairs verified, 12/12
cameras, 3608 points, **0.316 px** in 4.5 s — better than the incremental chain's
0.36 px before bundle adjustment, and reached in one module.

**Reading the output:** [artifact.md](artifact.md). It writes a COLMAP sidecar,
so a pycolmap consumer opens the model natively.
