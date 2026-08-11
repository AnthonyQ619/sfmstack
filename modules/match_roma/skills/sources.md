---
module: FeatureMatchRoMa
module_version: 1.0.0
curated_at: 2026-08-10
---

# Sources

## RoMa: Robust Dense Feature Matching
Edstedt, Sundgren, Bökman, Wadenbäck, Felsberg — CVPR 2024.
<https://arxiv.org/abs/2305.15404> · <https://github.com/Parskatt/RoMa>

The method. Three parts do the work: a frozen DINOv2 backbone for coarse matching
(robust, coarse), a specialised ConvNet for fine refinement (precise, local), and
a regression-by-classification head that models match uncertainty rather than
producing a point estimate. The certainty this module exposes as `confidence` and
filters on with `min_certainty` comes from that head.

Read for: why the coarse/fine split matters, and why the certainty is closer to a
calibrated uncertainty than to a matching score.

`romatch` 0.1.2 on PyPI. API notes verified against it:

- `match(im_A, im_B, device=)` takes PATHS or PIL images and returns
  `(warp, certainty)` for the dense field.
- `sample(warp, certainty, num=)` draws correspondences certainty-weighted; it
  samples an already-computed field, so `num` costs nothing upstream.
- `to_pixel_coordinates(coords, H_A, W_A, H_B, W_B)` maps the normalised warp into
  whatever pixel size it is told — which is why passing the SCENE's working
  resolution rather than RoMa's internal one is load-bearing.
- **`use_custom_corr` defaults to True on Linux** and requires a compiled CUDA
  extension named `local_corr` that pip does not install. The model constructs
  successfully without it and raises `ModuleNotFoundError` on the first forward
  pass. This module defaults it to False.

## LoFTR: Detector-Free Local Feature Matching with Transformers
Sun, Shen, Wang, Bao, Zhou — CVPR 2021. <https://arxiv.org/abs/2104.00680>

The earlier module in the same family, and this one's sibling here. Same
detector-free premise, far cheaper, less robust under large viewpoint change.

## DINOv2
Oquab et al., 2023. <https://arxiv.org/abs/2304.07193>

The frozen backbone. Relevant because RoMa's robustness to illumination and
viewpoint is largely inherited from it, which is also why RoMa behaves better than
LoFTR on exactly the cases where a detector fails.

## The predecessor
`scene_agent/breadth_agent/src/sfmcore/featurematching.py`, the RoMa matcher.

Same call sequence. Differences: the view graph is a parameter rather than fixed
to consecutive pairs; `use_custom_corr` is exposed rather than left at the
upstream default; certainty is emitted per correspondence and summarised as a
metric; and the "pseudo merge eps" the predecessor carried inside its matched-point
container is not here — merge tolerance belongs to the tracker, which is the module
that merges.
