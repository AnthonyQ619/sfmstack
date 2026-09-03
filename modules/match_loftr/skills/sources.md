---
module: FeatureMatchLoFTR
module_version: 1.7.0
curated_at: 2026-08-08
---

# Sources

## LoFTR

**Sun, Shen, Wang, Bao, Zhou, "LoFTR: Detector-Free Local Feature Matching with
Transformers", CVPR 2021.**

Coarse-to-fine: self- and cross-attention over an 1/8-resolution feature grid
produces coarse matches, then a fine module refines each to sub-pixel on a local
window. Linear attention keeps the coarse stage tractable at that resolution.

The paper's central argument is the one that matters for module selection: a
detector is a *bottleneck*, because a keypoint that cannot be repeatably detected
can never be matched however good the descriptor is. Removing the detector is what
makes low-texture regions matchable at all — and is also why the output has no
keypoint identity to reuse across pairs, which is the downstream consequence
documented in [artifact.md](artifact.md#no-feature_index).

The `indoor` (ScanNet) and `outdoor` (MegaDepth) weights are separately trained;
section 4 evaluates them on their own domains and they are not presented as
interchangeable.

## The implementation

`kornia.feature.LoFTR`, pinned at kornia 0.8.3 in `docker/runtime-kornia/`.

Kornia gets its **own base image**, separate from the lightglue one, deliberately.
The predecessor's two conda environments pinned kornia 0.8.1 and 0.7.1 — LoFTR's
`default_cfg` import path moved between them — and the overview of that system
records this as the sharpest of its dependency conflicts. Here the two stacks never
share an environment, so there is nothing to reconcile.

The 8-pixel divisibility requirement is a consequence of the 1/8 coarse grid.
Handled here by padding rather than resizing, because a bottom-right pad leaves
every coordinate unchanged and a resize does not.

## The merge_eps_px finding

Not from a paper. Measured in this repo and recorded in
[tuning.md](tuning.md#the-first-thing-to-set-is-not-in-this-module) and in the
tracker's tuning file.

It matters because the tracker's default (1.5px, inherited from the predecessor's
`pseudo_merge_eps_px`) leaves LoFTR tracks unable to chain — 3 of 5 images
unregisterable on the reference scene. An earlier synthetic experiment in this repo,
run on SIFT matches with `feature_index` artificially stripped, endorsed exactly
that value. The proxy was not measuring the quantity that matters: with a detector
the same keypoint recurs at identical coordinates across pairs, and with LoFTR each
pair is estimated independently.

Recorded at length because a synthetic test that confirms a wrong default is a
failure mode worth being able to recognise.

## Predecessor code

`scene_agent/breadth_agent/src/sfmcore/featurematching.py`, `FeatureMatchLoftrPair`
(lines 263-548), also via kornia.

Differences:

- **Sequential-only pairing**, as with every predecessor matcher.
- **`pseudo_merge_eps_px` lived on the matcher**, passed into `PointsMatched` to
  configure a merge that happened inside the data structure. Here the merge belongs
  to the tracker, which is the module that actually performs it, and the matcher's
  only obligation is to omit `feature_index` honestly.
- **`from kornia.feature.loftr.loftr import default_cfg`** at file scope — the exact
  import that broke between kornia 0.7 and 0.8 and forced the two-environment split.
  Not needed here; `KF.LoFTR(pretrained=...)` is the whole interface used.

## What is asserted without a source

Audited 2026-09-02 against this module's own manifest.

- **Healthy bands with nothing behind them.** `pairs_matched`, `matches_per_pair`, `largest_component_fraction`, `min_image_degree`, `planarity`, `mean_match_score` declare a range and no diagnostic on this module reads them. A band with no diagnostic is a description of the captures measured so far, not a judgement on yours -- and a corpus maximum is the largest of N draws, so the next capture exceeding it is expected rather than anomalous.
- **Numeric tuning advice with no citation in this file.** `pairing`, `min_confidence`, `max_matches`, `resize_long_edge`, `min_matches` name specific values in their tuning prose. The reasoning behind them may be sound; the numbers are settings that worked here, not results anyone has published.
- **Everything about this module's behaviour in a real pipeline.** It was run **zero times** in the seventeen-capture sweep, so every claim here is from isolated testing or carried over from the predecessor. Nothing in this file has been exercised end to end.

## Review triggers

Re-read and re-check this file when any of these happens:

- **This module's version changes from 1.7.0.** These notes were written against it; a metric set or a published band can change with a version and the prose does not follow automatically.
- **A capture unlike the benchmark families appears.** Every band here was fitted on controlled-rig and field captures from two benchmark datasets. Per-frame appearance readings transfer to a larger capture; adjacent-motion readings and anything denominated in pairs do not.
- **A reading crosses one of `pairs_matched`, `matches_per_pair`, `largest_component_fraction`, and 3 more and nothing fires.** That is this file's known gap, not a defect in the capture -- but it is the signal that the band deserves either a diagnostic or a wider range.
- **The first time this module is run in a real pipeline.** Everything here is untested at that level; the first end-to-end run is the trigger to rewrite this file rather than to trust it.
