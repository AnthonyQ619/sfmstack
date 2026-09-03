---
module: FeatureMatchRoMa
module_version: 1.6.0
upstream: romatch 0.1.2 (RoMa, CVPR 2024)
curated_at: 2026-08-10
sources: 3
---

## Where to go next

This file is the router. Everything below is orientation; the detail lives in the
other four documents, and this table is how to pick one without fetching all of
them.

| If | Fetch |
| --- | --- |
| a number is out of band, or a diagnostic told you to tune | **`tuning`** — 8 parameters documented, starting with `setting` |
| you need to know whether this module can do the thing at all | **`limitations`** — e.g. "No `feature_index`" |
| you are reading what it wrote | **`artifact`** — the layout of `pairwise_matches/v1` |
| you want to know where a claim came from, or what rests on nothing | **`sources`** — includes an audited list of what is asserted without a source |

**First readings on this module's output:** `pairs_proposed`, `pairs_matched`, `matches_per_pair`.

**Diagnostics it can raise:** `no_pairs_matched`, `broken_chain`, `low_inlier_ratio`, `detector_free_output`.

## What this module is for


Dense warp plus per-pixel certainty from a DINOv2 backbone, sampled into
correspondences. **Detector-free** — consumes `scene/v1` only. GPU required in
practice.

**Use when** a detector is what is failing: textureless surfaces, large
illumination or viewpoint change, repetitive structure. RoMa proposes
correspondences everywhere and weights them by an estimated certainty rather than
by descriptor distance, so nothing has to be repeatable.

**Prefer LoFTR when** cost matters — same family, several times cheaper. Prefer a
sparse matcher when the scene is well textured; inside the classical detector's
envelope all three land in the same
place and the sparse ones are far faster.

**Measured on a turntable capture of a compact object** (8 images at 1024px, `window: 2`, GPU, in containers):
13 pairs, **4951.8 matches per pair**, inlier ratio **0.99**, mean certainty
**0.997**, 19.8 s. Through union-find at `merge_eps_px: 4.0` and the incremental
pose estimator: **8/8 registered at 0.33 px**.

**Two things to know before using it:**

1. **No `feature_index`, and RoMa wants a TIGHTER `merge_eps_px` than LoFTR.**
   Each pair is matched independently, so a physical point has a different
   sub-pixel position in every pair and the tracker merges by proximity. The
   tolerance that works is *specific to this module*: at 1024 px, 4 px is already
   over-merged (`inconsistent_rate` 0.20, `merge_headroom` −0.21) where LoFTR at
   1.5 px was under-merged. **Start at 2–3 px for RoMa**, and see
   [tuning.md](tuning.md#the-tracker-tolerance-this-module-needs).
2. **`use_custom_corr` is off by default.** RoMa's fast local-correlation kernel
   is a compiled CUDA extension pip does not install. With it missing, the model
   *builds* and then raises on the first forward pass. The default here is the
   pure-torch fallback: correct, slower, and it runs.

**Cheapest thing that usually works:** defaults, `window: 2`, and the tracker at
`merge_eps_px` 3–4 px for a 1024 px working resolution.

**Reading the output:** [artifact.md](artifact.md).
