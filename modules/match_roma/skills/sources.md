---
module: FeatureMatchRoMa
module_version: 1.6.0
curated_at: 2026-09-07
---

# Where FeatureMatchRoMa's claims come from

**Cite-only, like the evidence tier: this file exists to be referenced, not
browsed.** The provenance summary rides `SKILL.md`; unsourced-band warnings sit
in `tuning.md`; the re-check rule is the one global rule in `SKILLS.md`.

| Claim / content | Rests on |
| --- | --- |
| frozen DINOv2 backbone (coarse, robust) + ConvNet refinement (fine, local) + regression-by-classification uncertainty head — the source of the `confidence` this module filters with `min_certainty`, closer to calibrated uncertainty than a matching score | RoMa — Edstedt et al., CVPR 2024; <https://arxiv.org/abs/2305.15404> |
| robustness to illumination/viewpoint largely inherited from the backbone — why RoMa outperforms LoFTR exactly where a detector fails | DINOv2 — Oquab et al., 2023 |
| `match()` takes paths or PIL images → `(warp, certainty)`; `sample(num=)` re-samples an already-computed field, so `num` costs nothing upstream; `to_pixel_coordinates` maps into whatever size it is told — passing the SCENE's working resolution is load-bearing | `romatch` 0.1.2, verified |
| **`use_custom_corr` defaults True on Linux** and needs a compiled `local_corr` CUDA extension pip does not install — constructs fine, raises `ModuleNotFoundError` on first forward. Defaulted False here | observed against `romatch` 0.1.2 |
| sibling positioning: same detector-free premise as LoFTR, far costlier, more robust under large viewpoint change | both papers |
| view graph as a parameter; `use_custom_corr` exposed; per-correspondence certainty emitted; merge tolerance belongs to the tracker, not carried in a matched-point container | predecessor `sfmcore/featurematching.py`, RoMa matcher |
| **everything about behaviour in a real pipeline** | **nothing** — run zero times in the sweep; isolated testing and the predecessor only |
| 5 healthy bands; numeric values in `max_matches`, `min_certainty`, `use_custom_corr`, `pairing`, `ransac_threshold` advice | **nothing** — see the audit section in `tuning.md` |
