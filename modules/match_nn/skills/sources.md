---
module: FeatureMatchNN
module_version: 1.6.0
curated_at: 2026-09-07
---

# Where FeatureMatchNN's claims come from

**Cite-only, like the evidence tier: this file exists to be referenced, not
browsed.** The provenance summary rides `SKILL.md`; unsourced-band warnings sit
in `tuning.md`; the re-check rule is the one global rule in `SKILLS.md`.

| Claim / content | Rests on |
| --- | --- |
| the 0.8 ratio default: eliminates ~90% of false matches, costs ~5% of correct ones (on a 40000-keypoint database) — which is why loosening it mostly buys false matches; the ratio is a proxy for *distinctiveness*, not correctness, hence its failure on repeated structure | Lowe, IJCV 2004, §7.1 and fig. 11 |
| mutual consistency makes the correspondence a partial bijection — the ratio test is per-query, so several keypoints in A can pick the same one in B; many-to-one matches are what fuse two scene points into one track downstream (see the tracker's `inconsistent_rate`) | standard practice; the mechanism is the citation |
| MAGSAC++ (`USAC_MAGSAC`): marginalises over the inlier threshold, so `ransac_threshold` sets a **scale**, not a hard cut — why the advice is "raise toward 4–6" rather than a precise value | Barath et al., CVPR 2020; `maxIters=10000` kept from the predecessor for continuity |
| `planarity` is homography-inliers / fundamental-inliers — the crude cousin of GRIC (Torr, Zisserman, Maybank, CVIU 1997), chosen for zero free parameters and cross-scene comparability; revisit if it triggers on scenes that reconstruct fine | design decision, recorded |
| brute force means the ratio test's calibration actually applies — with approximate search both terms are approximations; `FeatureMatchFLANN` is the alternative once descriptor counts bottleneck, and it measures its own agreement | Lowe's criterion + this registry's division of labour |
| view graph is a parameter (predecessor matched `(i, i+1)` only); `planarity` measured per pair replaces the predecessor's ask-in-advance `RANSAC_homography` flag — the answer varies within a single scene | predecessor `sfmcore/featurematching.py` |
| `no_pairs` was declared and never emittable — the module RAISES when no pair survives; the declaration is gone, the raise's message says more than the diagnostic did | manifest audit, corrected |
| every measured band and episode | **18 runs** at 1.6.0 in the seventeen-capture sweep; scope pinned by `evidence/CORPUS.txt` |
| 4 healthy bands; numeric values in `pairing`, `window`, `ratio_test`, `ransac_threshold`, `min_matches` advice | **nothing** — see the audit section in `tuning.md` |
