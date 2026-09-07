---
module: FeatureDetectionORB
module_version: 1.0.0
curated_at: 2026-09-07
---

# Where FeatureDetectionORB's claims come from

**Cite-only, like the evidence tier: this file exists to be referenced, not
browsed.** The provenance summary rides `SKILL.md`; unsourced-band warnings sit
in `tuning.md`; the re-check rule is the one global rule in `SKILLS.md`.

| Claim / content | Rests on |
| --- | --- |
| orientation for FAST corners via intensity centroid; learned BRIEF sampling pattern (max variance, min correlation) | Rublee, Rabaud, Konolige, Bradski, "ORB", ICCV 2011 |
| the descriptor is designed for in-plane rotation and modest scale change, **not** affine invariance — read §7.2 before deciding ORB is failing | the paper, explicitly |
| paper's ~2-orders speedup over SIFT reads closer to **one** order here on 1024px images | measured in this pipeline |
| ANMS via Square Covering: binary-search a covering radius, keep the strongest per cell, O(n log n); the `exp1`–`exp4` closed-form bracket in the adapter is the paper's derivation | Bailo et al., Pattern Recognition Letters 2018 |
| why suppression matters for ORB specifically: `nfeatures` truncation keeps the highest-response corners, FAST responds where texture is already dense, so default selection worsens clustering — measured `spatial_coverage` 0.734 → 0.850 at identical count on a controlled-rig capture | direct measurement |
| Harris scoring over FAST scoring, because SSC's selection depends on the ranking being meaningful | `cv2.ORB_HARRIS_SCORE`; reasoning, not citation |
| defaults `fast_threshold=20`, `edge_threshold=31`, `WTA_K=2`; suppression **on** by default (predecessor's default was off — backwards given the measured coverage); `detect_multiplier` explicit (predecessor's absolute budget could silently no-op suppression); the cap is a real cap (SSC overshoot trimmed by response) | predecessor `sfmcore/features.py`, `FeatureDetectionORB` + `anms_ssc` |
| **everything about behaviour in a real pipeline** | **nothing** — run zero times in the sweep; isolated testing and the predecessor only |
| 1 healthy band; numeric values in 7 parameters' advice | **nothing** — see the audit section in `tuning.md` |
