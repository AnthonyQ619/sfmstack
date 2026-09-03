---
module: FeatureDetectionALIKED
module_version: 1.2.0
curated_at: 2026-08-08
---

# Sources

## ALIKED

**Zhao, Wu, Li, Zhang, Liu, Zhou, "ALIKED: A Lighter Keypoint and Descriptor
Extraction Network via Deformable Transformation", IEEE TIM 2023.** Successor to
ALIKE (Zhao et al., IEEE TMM 2022).

The contribution is the Sparse Deformable Descriptor Head: instead of sampling the
feature map on a fixed grid around each keypoint, it learns per-keypoint offsets,
so the descriptor's support adapts to local geometry. That is what buys
localisation accuracy for fewer parameters.

The differentiable keypoint detection from ALIKE — a soft-argmax over a local
score patch — is what makes the sub-pixel positions meaningful rather than
grid-quantised. Worth knowing when deciding whether ALIKED is buying anything:
its advantage is in `reprojection_error`, not in match count.

## Variants

`aliked-t16`, `aliked-n16`, `aliked-n16rot`, `aliked-n32` are the upstream
checkpoints. `n16rot` is trained with rotation augmentation; the paper's own
evaluation notes the base models are not rotation invariant, which is the same
weakness SuperPoint has and SIFT does not.

## The implementation

`lightglue.ALIKED` from **cvg/LightGlue**, installed from git in
`docker/runtime-lightglue/Dockerfile` and sharing that base image with SuperPoint
and LightGlue. Defaults are the package's own: `model_name='aliked-n16'`,
`detection_threshold=0.2`, `nms_radius=2`.

The threshold scale difference from SuperPoint (0.2 against 0.0005) is upstream,
not something introduced here. It is recorded prominently in the parameter
documentation and in the module's failure message because it is a silent
misconfiguration in one direction and a total-failure one in the other.

## Predecessor code

`scene_agent/breadth_agent/src/sfmcore/features.py`, `FeatureDetectionALIKED`
(lines 385-484), already using `lightglue.ALIKED`.

Differences:

- **`variant` is exposed.** The predecessor hardcoded the default model and offered
  `max_keypoints` and `det_thres` only, so `aliked-n16rot` — the one genuine reason
  to prefer ALIKED on a rotating capture — was unreachable.
- **`nms_radius` is exposed**, so the coverage/density trade is tunable rather than
  fixed at the package default.
- **The threshold scale is documented.** The predecessor's `det_thres=0.005`
  default sat between SuperPoint's scale and ALIKED's, matching neither package
  default, with nothing recording why.

## What is asserted without a source

Audited 2026-09-02 against this module's own manifest.

- **Healthy bands with nothing behind them.** `keypoints_per_image`, `spatial_coverage` declare a range and no diagnostic on this module reads them. A band with no diagnostic is a description of the captures measured so far, not a judgement on yours -- and a corpus maximum is the largest of N draws, so the next capture exceeding it is expected rather than anomalous.
- **Numeric tuning advice with no citation in this file.** `variant`, `max_keypoints`, `detection_threshold`, `nms_radius`, `resize_long_edge` name specific values in their tuning prose. The reasoning behind them may be sound; the numbers are settings that worked here, not results anyone has published.
- **Scope of the measurements.** What is written here was exercised across 2 runs of this module in a seventeen-capture sweep of benchmark captures, at version 1.2.0. That is the whole evidence base: no capture outside those two benchmark families has been run through it.

## Review triggers

Re-read and re-check this file when any of these happens:

- **This module's version changes from 1.2.0.** These notes were written against it; a metric set or a published band can change with a version and the prose does not follow automatically.
- **A capture unlike the benchmark families appears.** Every band here was fitted on controlled-rig and field captures from two benchmark datasets. Per-frame appearance readings transfer to a larger capture; adjacent-motion readings and anything denominated in pairs do not.
- **A reading crosses one of `keypoints_per_image`, `spatial_coverage` and nothing fires.** That is this file's known gap, not a defect in the capture -- but it is the signal that the band deserves either a diagnostic or a wider range.
