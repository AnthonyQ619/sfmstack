---
module: FeatureMatchRoMa
module_version: 1.0.0
upstream: romatch 0.1.2 (RoMa, CVPR 2024)
curated_at: 2026-08-10
sources: 3
---

Dense warp plus per-pixel certainty from a DINOv2 backbone, sampled into
correspondences. **Detector-free** — consumes `scene/v1` only. GPU required in
practice.

**Use when** a detector is what is failing: textureless surfaces, large
illumination or viewpoint change, repetitive structure. RoMa proposes
correspondences everywhere and weights them by an estimated certainty rather than
by descriptor distance, so nothing has to be repeatable.

**Prefer LoFTR when** cost matters — same family, several times cheaper. Prefer a
sparse matcher when the scene is well textured; on DTU all three land in the same
place and the sparse ones are far faster.

**Measured on DTU scan1** (8 images at 1024px, `window: 2`, GPU, in containers):
13 pairs, **4951.8 matches per pair**, inlier ratio **0.99**, mean certainty
**0.997**, 19.8 s. Through union-find at `merge_eps_px: 4.0` and the incremental
pose estimator: **8/8 registered at 0.33 px**.

**Two things to know before using it:**

1. **No `feature_index`.** Each pair is matched independently, so a physical point
   has a different sub-pixel position in every pair. The tracker merges by
   proximity, and `merge_eps_px` decides whether tracks chain at all —
   see [limitations.md](limitations.md#no-feature_index).
2. **`use_custom_corr` is off by default.** RoMa's fast local-correlation kernel
   is a compiled CUDA extension pip does not install. With it missing, the model
   *builds* and then raises on the first forward pass. The default here is the
   pure-torch fallback: correct, slower, and it runs.

**Cheapest thing that usually works:** defaults, `window: 2`, and the tracker at
`merge_eps_px` 3–4 px for a 1024 px working resolution.

**Reading the output:** [artifact.md](artifact.md).
