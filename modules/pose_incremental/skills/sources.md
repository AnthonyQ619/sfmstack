---
module: PoseEssentialToPnP
module_version: 1.2.0
curated_at: 2026-09-07
---

# Where PoseEssentialToPnP's claims come from

**Cite-only, like the evidence tier: this file exists to be referenced, not
browsed.** The provenance summary rides `SKILL.md`; unsourced-band warnings sit
in `tuning.md`; the re-check rule is the one global rule in `SKILLS.md`.

| Claim / content | Rests on |
| --- | --- |
| the incremental order — seed selection, next-best-view, triangulation, filtering | Schönberger & Frahm, CVPR 2016 (COLMAP), §4.2–4.4 |
| next-best-view by correspondence **count** only — COLMAP's scoring also rewards spread across the image; upgrade if `registered_fraction` is high while `mean_reprojection_error` is poor. Retriangulation/interleaved refinement is deliberately NOT implemented — one forward pass, refinement left to `BundleAdjustmentGlobal` | same paper; the gaps are recorded design choices |
| seed pair needs many matches **and** a homography-defying baseline — the most-matched pair is usually the least-baseline pair; ours scores `inlier_count × median_parallax` with a parallax floor (Photo Tourism's homography-inlier criterion is arguably better and already exists upstream as the matcher's `planarity`, but using it would couple this module to `pairwise_matches`) | Snavely, Seitz, Szeliski, "Photo Tourism", SIGGRAPH 2006, §4.2 |
| the criterion observed working: seeds chose images 0 and 8 at 25° median parallax over the adjacent pair, on a 12-image contiguous set | direct observation |
| `SOLVEPNP_SQPNP`: globally optimal, no initial guess — matters when a new image's registered neighbours are far; followed by `solvePnPRefineLM` on inliers; 10000 RANSAC iterations (predecessor used 200 — low for real track outlier rates) | Terzakis & Lourakis, ECCV 2020 |
| essential via `USAC_MAGSAC` in normalised coordinates with `K = I` — what lets per-image intrinsics differ within one scene | Barath et al., CVPR 2020 |
| consumes `tracks/v1` (predecessor rebuilt tracks inside the pose estimator); no hardcoded seed index; no nested optimizer instance; predecessor's `triangulate_track_best_pair` was reimplemented, not ported — it references undefined names (`NameError` if reached) and its baseline loop skips the last observation | predecessor `sfmcore/camerapose.py`, `CamPoseEstimatorEssentialToPnP` |
| every measured band and episode | **109 runs** at 1.2.0 in the seventeen-capture sweep — the most-run module in the registry; scope pinned by `evidence/CORPUS.txt` |
| 5 healthy bands; numeric values in 7 parameters' advice | **nothing** — see the audit section in `tuning.md` |
