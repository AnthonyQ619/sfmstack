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
[limitations.md](limitations.md#easy-scenes) and `docs/design/DECISIONS.md`.

The finding — that the classical stack beat the learned stack by 2.6x on final
reprojection error while losing on every intermediate metric — is consistent with
the papers rather than in tension with them: the published gains are measured on
HPatches, MegaDepth and Aachen Day-Night, which are chosen for illumination and
viewpoint difficulty. DTU scan1 is none of those things.

Recorded because the practical failure mode is reaching for the learned matcher by
reputation on a capture where it does not help, and then trusting the higher match
count.

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
