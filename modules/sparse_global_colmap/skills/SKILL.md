---
module: SparseGlobalCOLMAP
module_version: 1.1.0
upstream: pycolmap 4.1.1 global mapping (GLOMAP)
curated_at: 2026-08-10
sources: 3
---

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
