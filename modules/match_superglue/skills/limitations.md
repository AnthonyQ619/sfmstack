---
module: FeatureMatchSuperGlue
module_version: 1.6.0
curated_at: 2026-08-10
---

# What FeatureMatchSuperGlue cannot do

## SuperPoint only

The 256-dimensional descriptor width is baked into the trained weights. ALIKED
(128), SIFT (128) and ORB (32) are refused by name rather than run into confident
nonsense — there is no weight set for them and never was.

**Escape:** the learned matcher that has them.

```
find(produces="pairwise_matches/v1", consumes="features/v1")
```

`FeatureMatchLightGlue` carries weight sets for SuperPoint, ALIKED, SIFT and DISK.

## It cannot find what the detector missed

A sparse matcher matches keypoints. On a textureless wall SuperPoint finds
nothing there, and no matcher setting produces correspondences in a region with no
keypoints.

**Escape:** a detector-free matcher, which proposes correspondences directly.

```
find(produces="pairwise_matches/v1", not_consuming="features/v1")
```

`FeatureMatchLoFTR` answers this, and `FeatureMatchRoMa` more strongly. Note the
consequence: their output carries no `feature_index`, so the tracker merges
endpoints by proximity instead of by identity.

## Licence

Code and weights are Magic Leap's, released for research use only and not
redistributable. The base image clones them from upstream at build time rather
than vendoring them, which means **the image cannot be built without network
access** and cannot be pushed to a public registry. The predecessor kept a copy of
both in its source tree.

## No mutual-check parameter

There is none to expose. The Sinkhorn assignment is a partial permutation by
construction, so matches are one-to-one before any filtering. The `mutual`
parameter that `FeatureMatchNN` needs has no meaning here, and its absence is not
an omission.

## Indoor and outdoor are the whole choice

Two weight sets, trained on ScanNet and MegaDepth. There is no fine-tuning path in
this module and no third option. A scene far from both — aerial, macro, medical —
gets whichever is less wrong, and the honest response is to measure both rather
than to reason about which should win.
