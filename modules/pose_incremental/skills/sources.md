---
module: PoseEssentialToPnP
module_version: 1.4.0
curated_at: 2026-09-14
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
| escaped points counted and never judged; the mean-gain guard and the adjusters' tail rule both mislabelled runs whose finished models were accurate | a pose-stage experiment over every configuration in the campaign store where the old guard fired, each solved through refinement and scored against reference geometry (2026-09); recorded in [evidence/second-solve-2026-09](../../../skills/evidence/second-solve-2026-09.md) |
| the second solve — escaped points as the trigger, a fixed width rather than a search, kept unless it fails or is vetoed (or, against an accepted first solve, gives up more cameras than the band allows), never chosen on reprojection error | the same experiment, plus an upward window sweep over the configurations where points escaped; the trigger was tested on configurations where nothing escaped, and the stopping rules against reference geometry |
| an image PnP refused is retried once against the finished structure, at the same `min_pnp_inliers`; a camera placed this way can be less accurate than its neighbours | a retry experiment over every configuration of the window sweep, first and second solves each run with and without the retry and scored against reference geometry (2026-09): refusals were common and recoveries rare; the retry never lowered accuracy with missing cameras counted as failures, and lowered it once on registered cameras alone; recorded in [evidence/second-solve-2026-09](../../../skills/evidence/second-solve-2026-09.md) |
| registration is part of the second-solve decision only against a first solve the verifier accepted | the same experiment: refusing any loss discarded corrections worth more than the cameras given up, and on a capture whose correspondences support more than one stable model it left nothing to keep once the first solve was vetoed |
| the tolerance is the floor of this stage's `registered_fraction` band | a cost trade-off, not a finding: every loss observed was a small share of the capture and the solve that gave it up was the better model; nothing near the band's edge was tested |
| the `trade_off` readings — lost cameras' structure still covered, relative-rotation change on shared cameras | direct observation in the same experiment: where the second solve corrected the model the rotation change was several degrees, where it did not it was near zero; the lost cameras whose structure was poorly covered sat at the edge of the capture |
| 28 as the default width, 40 as the last resort | the sweep favoured 40 by a small margin and found no harm in it; 28 is the default as a cost trade-off, not a finding |
| 5 healthy bands; numeric values in 7 parameters' advice | **nothing** — see the audit section in `tuning.md` |
