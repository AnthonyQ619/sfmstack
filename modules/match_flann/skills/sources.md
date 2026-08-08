---
module: FeatureMatchFLANN
module_version: 1.0.0
curated_at: 2026-08-07
---

# Sources

## FLANN

**Muja and Lowe, "Fast Approximate Nearest Neighbors with Automatic Algorithm
Configuration", VISAPP 2009**, and **"Scalable Nearest Neighbor Algorithms for High
Dimensional Data", TPAMI 2014** for the LSH and hierarchical clustering paths.

The 2009 paper's central claim is that the right algorithm and its parameters are
data-dependent, and it provides an automatic tuning procedure to find them. OpenCV
exposes the algorithms but not that procedure, so `trees` and `checks` are set by
hand here — which is exactly the situation the paper argues against.

`match_agreement` is this module's substitute: rather than auto-tuning, it measures
the recall you actually got so the choice can be made on evidence.

## Randomised KD-trees

**Silpa-Anan and Hartley, "Optimised KD-trees for fast image descriptor matching",
CVPR 2008.** Multiple trees split on randomly chosen high-variance dimensions and
searched in a shared priority queue, which is what makes the approach work in the
128 dimensions SIFT lives in — a single KD-tree degenerates to linear search well
below that.

## Multi-probe LSH

**Lv, Josephson, Wang, Charikar, Li, "Multi-Probe LSH", VLDB 2007.** Probing
neighbouring hash buckets rather than only the exact one, which buys recall without
proportionally more tables. `lsh_probe_level` is that parameter.

Used here for binary descriptors because Hamming space cannot be indexed by a
KD-tree. The selection is automatic from the features artifact's `binary` flag
rather than a parameter, so an ORB→SIFT swap upstream cannot silently produce a
wrong index.

## Why this module measures itself

The observed result — FLANN 6x slower than brute force at 4096 keypoints per pair —
contradicts the usual reason for reaching for approximate search, and it is
specific to per-pair index construction rather than to FLANN.

Recorded in [limitations](limitations.md) with the timing, because the general
claim ("ANN is faster") is true and the specific application here is not.

## Predecessor code

`scene_agent/breadth_agent/src/sfmcore/featurematching.py`, `FeatureMatchFlannPair`
(lines 911-1065), alongside `FeatureMatchBFPair`.

Same `FLANN_INDEX_KDTREE` with `trees=5` (4 here, the OpenCV default) and
`checks=50`. Differences:

- **Sequential-only pairing.** As with every predecessor matcher, it matched
  `(i, i+1)` and nothing else.
- **No index selection for binary descriptors.** It built a KD-tree regardless,
  which for ORB descriptors is a category error — the resulting matches are not
  meaningful, and nothing in the pipeline would have said so.
- **No agreement measurement**, so the approximation's cost was invisible.
