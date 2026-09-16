---
module: DenseMVS
module_version: 1.0.0
curated_at: 2026-09-07
---

# Where DenseMVS's claims come from

**Cite-only, like the evidence tier: this file exists to be referenced, not
browsed.** The provenance summary rides `SKILL.md`; unsourced-band warnings sit
in `tuning.md`; the re-check rule is the one global rule in `SKILLS.md`.

| Claim / content | Rests on |
| --- | --- |
| the algorithm: joint depth/normal/per-pixel view selection, degrading gracefully on unstructured collections | Schönberger, Zheng, Pollefeys, Frahm, ECCV 2016 — <https://demuc.de/papers/schoenberger2016mvs.pdf> |
| `filter_min_ncc`, `filter_min_triangulation_angle`, `filter_min_num_consistent` are three independent gates a pixel must pass all of; `depth_map_completeness` is what is left | same paper, filtering stage |
| `undistort_images`, `patch_match_stereo`, `stereo_fusion` | pycolmap 4.1.1 (COLMAP — Schönberger & Frahm, CVPR 2016) |
| `patch_match_stereo` is CUDA-only, so the module requires `pycolmap-cuda12` (same import name); the CUDA wheel links X11 session management (`libsm6`, `libxext6`, `libxrender1` needed — the `libSM.so.6` import failure is not a display problem); it carries its own CUDA runtime, so the image is 742 MB not 6 GB | build observation, recorded in the Dockerfile |
| `stereo_fusion(output_path=...)` wants a **directory**; `write_consistency_graph` must be on for fusion; `gpu_index` stays `"-1"` because the broker leases exactly one device | pycolmap 4.1.1 API, observed |
| workspace built from any `sparse_model/v1` (predecessor required a specific upstream); predecessor set the *optimisation* fields (`opts.geom_consistency_max_cost`) where the deciding gates are the `filter_*` ones; all metrics here are new | predecessor `sfmcore/scenereconstruction.py`, `Dense3DReconstructionMVS` |
| **behaviour in a real pipeline** | one full dense batch of studio orbits, scored against reference geometry — `skills/evidence/dense-batch-2026-09.md`. It covers runtime under contention, the nature of the holes, and `fusion_min_num_pixels`; every other claim here is still isolated testing or the predecessor |
| 2 healthy bands; numeric values in 12 parameters' tuning advice | **nothing** — see the audit section in `tuning.md` |
