---
module: SparseTriangulationGTSAM
module_version: 1.1.0
curated_at: 2026-09-07
---

# Where SparseTriangulationGTSAM's claims come from

**Cite-only, like the evidence tier: this file exists to be referenced, not
browsed.** The provenance summary rides `SKILL.md`; unsourced-band warnings sit
in `tuning.md`; the re-check rule is the one global rule in `SKILLS.md`.

| Claim / content | Rests on |
| --- | --- |
| the estimator: DLT weights every observation equally, wrong when measurement geometry differs between views; LOST's weighting makes the linear solution statistically optimal without iterating — largest gain with one wide baseline among near-coincident views (a turntable, a slow dolly) | LOST — Henry & Christian, J. Guidance, Control, and Dynamics 2023; <https://arxiv.org/abs/2205.12197> |
| why DLT minimises an algebraic rather than geometric error — the gap LOST closes linearly and `optimize` closes by iterating | Hartley & Zisserman, *Multiple View Geometry*, §12 |
| the `CameraSet` overload carries `useLOST` (the `poses + sharedCal` one does not); argument order `(cameras, measurements, rank_tol, optimize, model, useLOST)`; GTSAM poses are **world_from_cam** vs `poses/v1`'s cam_from_world — inverted in `gtsam_camera`, and getting it wrong produces a plausible cloud mirrored through the origin; cheirality and rank deficiency raise, so both are counted as rejections | `gtsam` 4.2.2, verified |
| `optimize` measured on synthetic four-view, 1.5 px noise: moves LOST by 0.0013 scene units, DLT by 0.00004, converging nearly to the same point — the flag works, and on well-conditioned data has little to do | direct measurement |
| same estimator and far-landmark rejection as the predecessor's `_triangulate_lost`, where `use_lost`/`optimize`/`rank_tol` were hardcoded locals marked "vars to add if this is successful"; here they are parameters and rejections are counted | predecessor `sfmcore/scenereconstruction.py` |
| every measured band and episode | **21 runs** at 1.1.0 in the seventeen-capture sweep; scope pinned by `evidence/CORPUS.txt` |
| 10 healthy bands; numeric values in `max_landmark_distance`, `min_track_len` advice | **nothing** — see the audit section in `tuning.md` |
