---
module: FeatureMatchLoFTR
module_version: 1.0.0
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
