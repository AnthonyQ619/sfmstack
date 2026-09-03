---
module: FeatureMatchRoMa
module_version: 1.6.0
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

## What is asserted without a source

Audited 2026-09-02 against this module's own manifest.

- **Healthy bands with nothing behind them.** `pairs_matched`, `matches_per_pair`, `largest_component_fraction`, `min_image_degree`, `mean_certainty` declare a range and no diagnostic on this module reads them. A band with no diagnostic is a description of the captures measured so far, not a judgement on yours -- and a corpus maximum is the largest of N draws, so the next capture exceeding it is expected rather than anomalous.
- **Numeric tuning advice with no citation in this file.** `max_matches`, `min_certainty`, `use_custom_corr`, `pairing`, `ransac_threshold` name specific values in their tuning prose. The reasoning behind them may be sound; the numbers are settings that worked here, not results anyone has published.
- **Everything about this module's behaviour in a real pipeline.** It was run **zero times** in the seventeen-capture sweep, so every claim here is from isolated testing or carried over from the predecessor. Nothing in this file has been exercised end to end.

## Review triggers

Re-read and re-check this file when any of these happens:

- **This module's version changes from 1.6.0.** These notes were written against it; a metric set or a published band can change with a version and the prose does not follow automatically.
- **A capture unlike the benchmark families appears.** Every band here was fitted on controlled-rig and field captures from two benchmark datasets. Per-frame appearance readings transfer to a larger capture; adjacent-motion readings and anything denominated in pairs do not.
- **A reading crosses one of `pairs_matched`, `matches_per_pair`, `largest_component_fraction`, and 2 more and nothing fires.** That is this file's known gap, not a defect in the capture -- but it is the signal that the band deserves either a diagnostic or a wider range.
- **The first time this module is run in a real pipeline.** Everything here is untested at that level; the first end-to-end run is the trigger to rewrite this file rather than to trust it.
