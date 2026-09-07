---
module: SparseGlobalCOLMAP
module_version: 1.1.0
curated_at: 2026-09-07
---

# Where SparseGlobalCOLMAP's claims come from

**Cite-only, like the evidence tier: this file exists to be referenced, not
browsed.** The provenance summary rides `SKILL.md`; unsourced-band warnings sit
in `tuning.md`; the re-check rule is the one global rule in `SKILLS.md`.

| Claim / content | Rests on |
| --- | --- |
| the method: joint estimation of camera positions and structure, replacing separate translation averaging — accuracy competitive with incremental at better scalability | GLOMAP — Pan, Barath, Pollefeys, Schönberger, ECCV 2024 |
| why one wrong relative rotation degrades the whole graph rather than one image — the reason `min_num_matches` defaults higher here than in any matcher | Hartley, Trumpf, Dai, Li, "Rotation Averaging", IJCV 2013 |
| `Database.open(path)` (no constructor); `estimate_calibrated_two_view_geometry` wants the FULL per-image keypoint tables + index pairs — pre-selected 0..n points verify a **different** correspondence set with a plausible inlier count; Ceres options at `options.ceres.solver_options`; `update_point_3d_errors()` before `compute_mean_reprojection_error()` or it returns 0.0 | pycolmap 4.1.1, verified (COLMAP — Schönberger & Frahm, CVPR 2016) |
| input is `pairwise_matches/v1`; one COLMAP camera per distinct calibration (multi-camera rigs work); work directory is a tempdir, the COLMAP model preserved as an artifact sidecar | predecessor `sfmcore/scenereconstruction.py`, `SparseSceneEstimationCOLMAPGlobal`, which conflated pairs and tracks and wrote one shared camera |
| every measured band and episode | **8 runs** at 1.1.0 in the seventeen-capture sweep; scope pinned by `evidence/CORPUS.txt` |
| 10 healthy bands; numeric values in 7 parameters' advice | **nothing** — see the audit section in `tuning.md` |
