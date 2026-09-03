---
module: FeatureMatchLightGlue
module_version: 1.6.0
curated_at: 2026-08-08
---

# Sources

## LightGlue

**Lindenberger, Sarlin, Pollefeys, "LightGlue: Local Feature Matching at Light
Speed", ICCV 2023.**

A redesign of SuperGlue with two adaptivity mechanisms:

- **Depth**: a confidence classifier after each layer decides whether the
  prediction has converged, so easy pairs exit early. `depth_confidence`.
- **Width**: keypoints judged unmatchable are pruned between layers.
  `width_confidence`.

The paper reports both as roughly free in accuracy on typical data, which is why
`depth_confidence` is the recommended speed lever here over reducing `n_layers` —
the latter weakens every pair uniformly, including the hard ones that need the
depth.

The core mechanism inherited from SuperGlue is self- and cross-attention over both
keypoint sets, producing a **joint** assignment. That is the substantive difference
from the ratio test, which evaluates each keypoint in isolation and therefore
cannot use the fact that its neighbours also matched consistently.

## Per-descriptor training

Section 4 and the released checkpoints: separate weights for SuperPoint, DISK,
ALIKED, SIFT and DoG-HardNet. This is not a fine-tuning convenience — the input
projection and the positional encoding differ per descriptor type.

Consequence, and the reason `weights: auto` exists: the wrong checkpoint does not
error. It produces an assignment from descriptors it was not trained on, and the
result is confident and meaningless. `mean_match_score` is this module's after-the-
fact detector for that.

The `sift` and `doghardnet` checkpoints set `add_scale_ori`, so they require
keypoint scale and orientation as extra inputs. SuperPoint and ALIKED artifacts
carry neither, and this module raises rather than proceeding — a check worth having
because the failure would otherwise be a shape error deep inside the model.

## SuperGlue, for context

**Sarlin, DeTone, Malisiewicz, Rabinovich, "SuperGlue: Learning Feature Matching
with Graph Neural Networks", CVPR 2020.** The predecessor architecture, and one of
the 23 modules still to be ported. LightGlue is faster and more accurate on the
published benchmarks; SuperGlue remains relevant mainly for reproducing older
results.

## The measured DTU result

Not from a paper. Measured in this repo and recorded in
[limitations.md](limitations.md#captures-inside-the-classical-detectors-design-envelope) and `docs/design/DECISIONS.md`.

The finding — that the classical stack beat the learned stack by 2.6x on final
reprojection error while losing on every intermediate metric — is consistent with
the papers rather than in tension with them: the published gains are measured on
HPatches, MegaDepth and Aachen Day-Night, which are chosen for illumination and
viewpoint difficulty. DTU scan1 is none of those things.

Recorded because the practical failure mode is reaching for the learned matcher by
reputation on a capture where it does not help, and then trusting the higher match
count.

## The criterion for `filter_threshold`, and why it changed

Not from a paper. Measured in this repo across a seventeen-capture sweep.

The documented criterion for this module's quality dial was the tracker's
`inconsistent_rate`, on the correct reasoning that two-view verification cannot see
a match displaced onto a repeated structure. That reasoning still holds. What
failed is the choice of instrument.

`inconsistent_rate` was measured insensitive across the range that decides the run,
twice: on one capture the matcher's own `cycle_merge_rate + cycle_split_rate` fell
7.7x across a sweep while `inconsistent_rate` fell 1.17x; on another,
`inconsistent_rate` moved 0.005 across a sweep whose registration went from 5
frames to 30, non-monotonically. The cycle terms tracked both cleanly. They also
sit on this artifact, so keying on them removes a tracker run from every point of a
sweep.

Two limits on the replacement, both measured:

- **The merge term alone is not the forecast**, and it used to be annotated as one.
  A capture read 0.0016 on it — clean — and produced a track table 17%
  self-contradictory, with all of the signal in the split term.
- **The sum is not a level.** The constant relating it to `inconsistent_rate`
  varies about fourfold between captures, so it prices a difference within one
  capture and cannot be thresholded across them.

The family-level statement is in [`skills/families/matching.md`](../../../skills/families/matching.md).

## Predecessor code

`scene_agent/breadth_agent/src/sfmcore/featurematching.py`,
`FeatureMatchLightGluePair` (lines 722-911), using a vendored copy of LightGlue at
`sfmcore/models/matchers/lightglue.py`.

Differences:

- **Vendored source versus a pinned git install.** Same trade as SuperPoint.
- **`detector` was a free-text parameter defaulting to `'superpoint'`**, validated
  only against a list of supported names — nothing checked it against the features
  actually supplied. Passing SIFT features with the default would run SuperPoint
  weights silently. Here it is inferred from provenance and cross-checked against
  descriptor width.
- **`cam_data=CameraData`** as a default argument — a class object as a default
  value, noted in the predecessor's own inventory as something that "will silently
  mask a missing argument".
- **Sequential-only pairing**, as with every predecessor matcher.

## What is asserted without a source

Audited 2026-09-02 against this module's own manifest.

- **Healthy bands with nothing behind them.** `pairs_matched`, `matches_per_pair`, `largest_component_fraction`, `min_image_degree`, `planarity`, `mean_match_score` declare a range and no diagnostic on this module reads them. A band with no diagnostic is a description of the captures measured so far, not a judgement on yours -- and a corpus maximum is the largest of N draws, so the next capture exceeding it is expected rather than anomalous.
- **Numeric tuning advice with no citation in this file.** `window`, `filter_threshold`, `n_layers`, `depth_confidence`, `width_confidence` name specific values in their tuning prose. The reasoning behind them may be sound; the numbers are settings that worked here, not results anyone has published.
- **Scope of the measurements.** What is written here was exercised across 75 runs of this module in a seventeen-capture sweep of benchmark captures, at version 1.6.0. That is the whole evidence base: no capture outside those two benchmark families has been run through it.

## Review triggers

Re-read and re-check this file when any of these happens:

- **This module's version changes from 1.6.0.** These notes were written against it; a metric set or a published band can change with a version and the prose does not follow automatically.
- **A capture unlike the benchmark families appears.** Every band here was fitted on controlled-rig and field captures from two benchmark datasets. Per-frame appearance readings transfer to a larger capture; adjacent-motion readings and anything denominated in pairs do not.
- **A reading crosses one of `pairs_matched`, `matches_per_pair`, `largest_component_fraction`, and 3 more and nothing fires.** That is this file's known gap, not a defect in the capture -- but it is the signal that the band deserves either a diagnostic or a wider range.
