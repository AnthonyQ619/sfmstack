---
module: SparseTriangulation
module_version: 1.1.0
curated_at: 2026-09-07
---

# Where SparseTriangulation's claims come from

**Cite-only, like the evidence tier: this file exists to be referenced, not
browsed.** The provenance summary rides `SKILL.md`; unsourced-band warnings sit
in `tuning.md`; the re-check rule is the one global rule in `SKILLS.md`.

| Claim / content | Rests on |
| --- | --- |
| linear DLT triangulation; H&Z are explicit it is not optimal — used here **because** bundle adjustment follows and does the optimisation properly; a pipeline ending here would want §12.3's optimal method | Hartley & Zisserman, *Multiple View Geometry* 2nd ed., ch. 12 (`cv2.triangulatePoints` = §12.2) |
| widest-baseline pair over all-view DLT: depth conditioning is governed by the widest angle, and near-coincident views make "verify in every view" circular | standard incremental practice; COLMAP's `EstimateTriangulation` in spirit — Schönberger & Frahm, CVPR 2016, §4.4 |
| angle + reprojection filtering in both directions; the 2° default is in COLMAP's range (its `min_triangulation_angle` defaults 1.5°); the filter reads the **widest** angle over observing pairs, because a point triangulated from a mediocre pair can be conditioned by a third view | same section; the widest-angle choice is a recorded design decision |
| cheirality (`z > 0` in every observing camera) recorded as a **metric** because its rate is diagnostic of the poses — consistent input produces almost none; exactly 0 on the reference run | H&Z §9.6.3; measured |
| colour by mean over observations, nearest pixel — same idea as COLMAP's `extract_colors_for_all_images`; bilinear not worth the code | no source; stated as judgement |
| why this module exists as a seam: triangulation appeared in four predecessor places with `max_reproj_error` 3.0 in one and 4.0 in another, so clouds were not comparable across pose estimators | predecessor `camerapose.py`, `scenereconstruction.py`, `baseclass.py` |
| every measured band and episode | **27 runs** at 1.1.0 in the seventeen-capture sweep; scope pinned by `evidence/CORPUS.txt` |
| 9 healthy bands; numeric values in `min_triangulation_angle_deg`, `min_observations` advice | **nothing** — see the audit section in `tuning.md` |
