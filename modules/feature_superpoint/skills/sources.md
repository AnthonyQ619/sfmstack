---
module: FeatureDetectionSuperPoint
module_version: 1.1.0
curated_at: 2026-09-07
---

# Where FeatureDetectionSuperPoint's claims come from

**Cite-only, like the evidence tier: this file exists to be referenced, not
browsed.** The provenance summary rides `SKILL.md`; unsourced-band warnings sit
in `tuning.md`; the re-check rule is the one global rule in `SKILLS.md`.

| Claim / content | Rests on |
| --- | --- |
| Homographic Adaptation training: self-labelled across random homographies — the reason keypoints are repeatable under viewpoint change and **not** under rotation beyond the homography sampling ([limitations.md](limitations.md#rotation)) | DeTone, Malisiewicz, Rabinovich, "SuperPoint", CVPRW 2018 |
| detector and descriptor share an encoder, trained jointly — the substantive difference from SIFT's separately-designed pair | same paper |
| defaults `detection_threshold=0.0005`, `nms_radius=4`, `descriptor_dim=256` | `lightglue.SuperPoint` from cvg/LightGlue (git-pinned in `docker/runtime-lightglue/Dockerfile`); package defaults |
| weights baked at build time (`cache_weights.py` → `TORCH_HOME=/weights`): first-use download fails air-gapped, re-downloads per cold start, and teaches the `DurationEstimator` a one-off as the module's normal cost | deployment decision, recorded because it is easy to get wrong |
| pinned git install replaces vendored source; `detection_threshold` and `nms_radius` exposed (predecessor exposed only `max_keypoints=1024`, so the knobs deciding whether cap or threshold binds were unreachable); weights in images, not 4.8 GB of untracked files | predecessor `sfmcore/features.py`, `FeatureDetectionSP` |
| every measured band and episode | **21 runs** at 1.1.0 in the seventeen-capture sweep; scope pinned by `evidence/CORPUS.txt` |
| 2 healthy bands; numeric values in 4 parameters' advice | **nothing** — see the audit section in `tuning.md` |
