---
module: DenseFusion
module_version: 1.0.0
curated_at: 2026-09-16
---

# Where DenseFusion's claims come from

**Cite-only, like the evidence tier: this file exists to be referenced, not
browsed.**

| Claim / content | Rests on |
| --- | --- |
| fusion as a separate policy stage over per-pixel depth, normals and view agreement | Schönberger, Zheng, Pollefeys, Frahm, ECCV 2016 — <https://demuc.de/papers/schoenberger2016mvs.pdf> |
| `stereo_fusion(output_path, workspace_path, input_type, options)`; the tolerances and their defaults | pycolmap 4.1.1 (COLMAP — Schönberger & Frahm, CVPR 2016) |
| the same CUDA wheel as `DenseMVS`, and the X11 libraries it links, so the fusion code is identical | build observation, recorded in the Dockerfile |
| re-fusing a kept workspace at the delivered setting reproduces the delivered cloud | direct check on the corpus captures, one stereo pass each |
| the fusion curve's shape, the good region, the collapse at the loosest settings, the hardest capture sitting higher | the dense deep-dive on the corpus's studio orbits, scored against reference geometry on the published basis, with and without the geometric check |
| the stopping rule — a step that roughly doubles the cloud is where accuracy falls away | the same measurements, read back as point counts per setting |
| everything about `max_reproj_error`, `max_depth_error`, `max_normal_error`, `check_num_images` | **nothing measured** — COLMAP's defaults |
