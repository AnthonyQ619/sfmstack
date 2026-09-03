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

## What is asserted without a source

Audited 2026-09-02 against this module's own manifest.

- **Healthy bands with nothing behind them.** `point_count`, `views_contributing`, `mean_depth_confidence`, `depth_scale_spread` declare a range and no diagnostic on this module reads them. A band with no diagnostic is a description of the captures measured so far, not a judgement on yours -- and a corpus maximum is the largest of N draws, so the next capture exceeding it is expected rather than anomalous.
- **Numeric tuning advice with no citation in this file.** `stride`, `min_confidence`, `depth_scale`, `write_ply` name specific values in their tuning prose. The reasoning behind them may be sound; the numbers are settings that worked here, not results anyone has published.
- **Everything about this module's behaviour in a real pipeline.** It was run **zero times** in the seventeen-capture sweep, so every claim here is from isolated testing or carried over from the predecessor. Nothing in this file has been exercised end to end.

## Review triggers

Re-read and re-check this file when any of these happens:

- **This module's version changes from 1.0.0.** These notes were written against it; a metric set or a published band can change with a version and the prose does not follow automatically.
- **A capture unlike the benchmark families appears.** Every band here was fitted on controlled-rig and field captures from two benchmark datasets. Per-frame appearance readings transfer to a larger capture; adjacent-motion readings and anything denominated in pairs do not.
- **A reading crosses one of `point_count`, `views_contributing`, `mean_depth_confidence`, and 1 more and nothing fires.** That is this file's known gap, not a defect in the capture -- but it is the signal that the band deserves either a diagnostic or a wider range.
- **The first time this module is run in a real pipeline.** Everything here is untested at that level; the first end-to-end run is the trigger to rewrite this file rather than to trust it.
