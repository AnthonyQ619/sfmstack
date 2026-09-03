---
module: FeatureMatchFLANN
module_version: 1.6.0
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

## `no_pairs` is not a diagnostic, and used to be listed as one

The manifest declared it and the module never emitted it, because when no image pair survives matching -- the module RAISES, with a message naming the attempted pair count, the best raw match count and min_matches. A raise is the right behaviour — there is no artifact to hang a diagnostic on — but a diagnostic listed in the contract and unreachable in practice is worse than none: a reader planning against `sfm_describe_module` sees a failure mode they can catch and read, and will instead get an exception. The declaration is gone; the raise and its message are unchanged, and the message says more than the diagnostic did.

## What is asserted without a source

Audited 2026-09-02 against this module's own manifest.

- **Healthy bands with nothing behind them.** `pairs_matched`, `matches_per_pair`, `largest_component_fraction`, `min_image_degree`, `planarity` declare a range and no diagnostic on this module reads them. A band with no diagnostic is a description of the captures measured so far, not a judgement on yours -- and a corpus maximum is the largest of N draws, so the next capture exceeding it is expected rather than anomalous.
- **Numeric tuning advice with no citation in this file.** `window`, `ratio_test`, `trees`, `lsh_tables` name specific values in their tuning prose. The reasoning behind them may be sound; the numbers are settings that worked here, not results anyone has published.
- **Scope of the measurements.** What is written here was exercised across 4 runs of this module in a seventeen-capture sweep of benchmark captures, at version 1.6.0. That is the whole evidence base: no capture outside those two benchmark families has been run through it.

## Review triggers

Re-read and re-check this file when any of these happens:

- **This module's version changes from 1.6.0.** These notes were written against it; a metric set or a published band can change with a version and the prose does not follow automatically.
- **A capture unlike the benchmark families appears.** Every band here was fitted on controlled-rig and field captures from two benchmark datasets. Per-frame appearance readings transfer to a larger capture; adjacent-motion readings and anything denominated in pairs do not.
- **A reading crosses one of `pairs_matched`, `matches_per_pair`, `largest_component_fraction`, and 2 more and nothing fires.** That is this file's known gap, not a defect in the capture -- but it is the signal that the band deserves either a diagnostic or a wider range.
