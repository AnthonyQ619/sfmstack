---
module: FeatureMatchSuperGlue
module_version: 1.6.0
curated_at: 2026-08-10
---

# Sources

## SuperGlue: Learning Feature Matching with Graph Neural Networks
Sarlin, DeTone, Malisiewicz, Rabinovich — CVPR 2020 (oral).
<https://arxiv.org/abs/1911.11763> · <https://github.com/magicleap/SuperGluePretrainedNetwork>

The method. Two ideas do the work: self- and cross-attention over both keypoint
sets so a match is chosen with knowledge of the whole opposing set, and a Sinkhorn
optimal-transport layer that solves a partial assignment — including the decision
that a keypoint matches nothing, via the dustbin row and column.

Read for: why the assignment is one-to-one by construction, which is why this
module has no `mutual` parameter.

**Licence:** research use only, not redistributable. Both the code and the two
weight files live in the upstream repository, and the base image clones it at
build time (pinned to `ddcf11f`) rather than vendoring it. The image therefore
needs network access to build and must not be pushed publicly.

API notes verified against that commit:

- `forward()` reads `data['image0'].shape[2:]` to normalise keypoints, so it wants
  a TENSOR shaped like the image, not the image size. The predecessor's vendored
  copy was edited to take an `image_size0` key instead; upstream has no such key,
  and passing one raises `KeyError: 'image0'`.
- `matches0[k]` is the index in image 1 matched to keypoint k of image 0, or -1.
- Weights load from a path relative to the module file, so the repository layout
  must be preserved in the image.

## LightGlue: Local Feature Matching at Light Speed
Lindenberger, Sarlin, Pollefeys — ICCV 2023.
<https://arxiv.org/abs/2306.13643>

The successor, and this module's sibling here. Same joint-reasoning idea with
adaptive depth and point pruning; faster and generally more accurate. Its
confidence comes from a matchability head rather than a Sinkhorn assignment, which
is why the two modules' scores are not comparable.

## SuperPoint
DeTone, Malisiewicz, Rabinovich — CVPRW 2018. <https://arxiv.org/abs/1712.07629>

The detector these weights were trained against. Its 256-dimensional descriptor is
the hard constraint this module refuses to violate.

## The predecessor
`scene_agent/breadth_agent/src/sfmcore/featurematching.py`,
`FeatureMatchSuperGluePair`, with the network vendored at
`models/matchers/superglue.py` and weights at `models/matchers/weights/`.

Differences: the code and weights are not copied into this repository; keypoint
truncation is by detector score with a metric reporting how much was discarded
(the predecessor truncated silently); and the view graph is a parameter rather
than fixed to consecutive pairs.

## What is asserted without a source

Audited 2026-09-02 against this module's own manifest.

- **Healthy bands with nothing behind them.** `pairs_matched`, `matches_per_pair`, `largest_component_fraction`, `min_image_degree`, `mean_match_score` declare a range and no diagnostic on this module reads them. A band with no diagnostic is a description of the captures measured so far, not a judgement on yours -- and a corpus maximum is the largest of N draws, so the next capture exceeding it is expected rather than anomalous.
- **Numeric tuning advice with no citation in this file.** `match_threshold`, `sinkhorn_iterations`, `max_keypoints`, `window` name specific values in their tuning prose. The reasoning behind them may be sound; the numbers are settings that worked here, not results anyone has published.
- **Everything about this module's behaviour in a real pipeline.** It was run **zero times** in the seventeen-capture sweep, so every claim here is from isolated testing or carried over from the predecessor. Nothing in this file has been exercised end to end.

## Review triggers

Re-read and re-check this file when any of these happens:

- **This module's version changes from 1.6.0.** These notes were written against it; a metric set or a published band can change with a version and the prose does not follow automatically.
- **A capture unlike the benchmark families appears.** Every band here was fitted on controlled-rig and field captures from two benchmark datasets. Per-frame appearance readings transfer to a larger capture; adjacent-motion readings and anything denominated in pairs do not.
- **A reading crosses one of `pairs_matched`, `matches_per_pair`, `largest_component_fraction`, and 2 more and nothing fires.** That is this file's known gap, not a defect in the capture -- but it is the signal that the band deserves either a diagnostic or a wider range.
- **The first time this module is run in a real pipeline.** Everything here is untested at that level; the first end-to-end run is the trigger to rewrite this file rather than to trust it.
