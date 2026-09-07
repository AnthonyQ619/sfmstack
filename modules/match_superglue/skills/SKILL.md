---
module: FeatureMatchSuperGlue
module_version: 1.6.0
upstream: magicleap/SuperGluePretrainedNetwork @ ddcf11f
curated_at: 2026-08-10
sources: 3
---

## Where to go next

This file is the router. Everything below is orientation; the detail lives in the
other four documents, and this table is how to pick one without fetching all of
them.

| If | Fetch |
| --- | --- |
| a number is out of band, or a diagnostic told you to tune | **`tuning`** — 7 parameters documented, starting with `weights` |
| you need to know whether this module can do the thing at all | **`limitations`** — e.g. "It cannot find what the detector missed" |
| you are reading what it wrote | **`artifact`** — the layout of `pairwise_matches/v1` |
| you want to know where a claim came from, or what rests on nothing | **`sources`** — includes an audited list of what is asserted without a source |

**First readings on this module's output:** `pairs_proposed`, `pairs_matched`, `matches_per_pair`.

**Diagnostics it can raise:** `wrong_descriptor_width`, `no_pairs_matched`, `broken_chain`, `low_inlier_ratio`, `keypoints_truncated`.

## What this module is for


Attentional GNN over both keypoint sets, then a Sinkhorn optimal-transport
assignment. **SuperPoint descriptors only.** GPU strongly recommended.

**Use when** you want a second opinion from a learned matcher. LightGlue is the
same idea made adaptive and is usually faster and slightly better; a second
learned matcher is the cheapest way to tell "the matcher is wrong" from "this
scene is hard".

**Prefer LightGlue when** you need any detector other than SuperPoint, or when
matching cost matters. LightGlue prunes points and exits layers early;
SuperGlue's attention runs over every keypoint at every layer.

**Measured on a turntable capture of a compact object** (12 images at 1024px, SuperPoint, sequential window 1,
GPU, in containers):

| | SuperGlue | LightGlue |
|---|---:|---:|
| matches per pair | 1102.6 | 1089.1 |
| inlier ratio | 0.992 | 0.991 |
| mean match score | 0.874 | 0.851 |
| runtime | 5.9 s | 5.3 s |

They agree, which on an easy scene is the expected and useful result: it says the
matcher is not what limits this pipeline. Disagreement is the interesting case.

**The scores are not comparable between them.** SuperGlue's is a Sinkhorn
assignment probability, LightGlue's is a matchability head. Read
`mean_match_score` across settings *within* one module, never across the two.

**Cheapest thing that usually works:** defaults with `weights: outdoor`. Switch to
`indoor` for room interiors — the two are trained on different datasets (ScanNet
vs MegaDepth), not merely tuned.

**Reading the output:** [artifact.md](artifact.md).

## Provenance

**Run zero times in any pipeline.** Every claim in these skills is from isolated
testing or carried from the predecessor codebase; nothing here has been exercised
end to end. The first real run is the trigger to re-check all of it.
Claim-by-claim citations: the `sources` skill.
