---
module: DenseVGGT
module_version: 1.0.0
curated_at: 2026-08-11
---

# Sources

## VGGT: Visual Geometry Grounded Transformer
Wang, Leroy, Cabon, Chidlovskii, Revaud et al. — CVPR 2025 (best paper).
<https://arxiv.org/abs/2503.11651> · <https://github.com/facebookresearch/vggt>

The depth head, pinned at commit `a288dd0`. Same preprocessing letterbox as
`PoseVGGT` and `SparseVGGT`.

Two behaviours of the head that shape this module:

- **The confidence is unbounded above.** Measured mean 46.6 on DTU. Treating it as
  a 0–1 probability is the most likely way to misconfigure this module, which is
  why `min_confidence` documents it and the failure message repeats it.
- **Depth is predicted for the whole 518-square**, including the white letterbox
  padding, which the model happily assigns a plausible depth. Unprojecting it adds
  a flat sheet at the edge of every view, so only the image region is unprojected.

## The predecessor
`scene_agent/breadth_agent/src/sfmcore/scenereconstruction.py`,
`Dense3DReconstructionVGGT`.

Differences: it used the point maps in VGGT's own frame, so it composed only with
VGGT poses; this unprojects depth into the supplied frame. It had no scale
handling, because reading point maps made the question invisible. And it
unprojected the full square including padding.
