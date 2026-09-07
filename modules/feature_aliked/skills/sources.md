---
module: FeatureDetectionALIKED
module_version: 1.2.0
curated_at: 2026-09-07
---

# Where FeatureDetectionALIKED's claims come from

**Cite-only, like the evidence tier: this file exists to be referenced, not
browsed.** The provenance summary rides `SKILL.md`; unsourced-band warnings sit
in `tuning.md`; the re-check rule is the one global rule in `SKILLS.md`.

| Claim / content | Rests on |
| --- | --- |
| the Sparse Deformable Descriptor Head: learned per-keypoint offsets instead of a fixed sampling grid — localisation accuracy for fewer parameters, so ALIKED's advantage is in `reprojection_error`, not match count | Zhao, Wu, Li, Zhang, Liu, Zhou, "ALIKED", IEEE TIM 2023 (successor to ALIKE, IEEE TMM 2022) |
| sub-pixel positions are meaningful (soft-argmax over a local score patch), not grid-quantised | ALIKE's differentiable keypoint detection, carried into ALIKED |
| base variants are **not rotation invariant**; `aliked-n16rot` is the rotation-augmented checkpoint | the paper's own evaluation — the same weakness SuperPoint has and SIFT does not |
| variants `aliked-t16` / `n16` / `n16rot` / `n32`; defaults `model_name='aliked-n16'`, `detection_threshold=0.2`, `nms_radius=2` | `lightglue.ALIKED` from cvg/LightGlue (git-pinned in `docker/runtime-lightglue/Dockerfile`); package defaults |
| the threshold scale difference from SuperPoint (0.2 vs 0.0005) is upstream — silent misconfiguration one way, total failure the other | package defaults, recorded in the parameter docs and failure message |
| `variant` and `nms_radius` exposed (predecessor hardcoded the model, fixed the radius, and defaulted `det_thres=0.005` — matching neither package's scale, unrecorded why) | predecessor `sfmcore/features.py`, `FeatureDetectionALIKED` |
| every measured band and episode | **2 runs** at 1.2.0 in the seventeen-capture sweep — a very thin base; scope pinned by `evidence/CORPUS.txt` |
| 2 healthy bands; numeric values in 5 parameters' advice | **nothing** — see the audit section in `tuning.md` |
