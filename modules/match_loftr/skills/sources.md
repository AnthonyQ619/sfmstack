---
module: FeatureMatchLoFTR
module_version: 1.7.0
curated_at: 2026-09-07
---

# Where FeatureMatchLoFTR's claims come from

**Cite-only, like the evidence tier: this file exists to be referenced, not
browsed.** The provenance summary rides `SKILL.md`; unsourced-band warnings sit
in `tuning.md`; the re-check rule is the one global rule in `SKILLS.md`.

| Claim / content | Rests on |
| --- | --- |
| coarse-to-fine: attention over a 1/8 feature grid, then sub-pixel refinement; linear attention keeps the coarse stage tractable | Sun, Shen, Wang, Bao, Zhou, "LoFTR", CVPR 2021 |
| the selection argument: a detector is a *bottleneck* — an undetectable keypoint can never be matched — so removing it makes low-texture regions matchable, at the cost of no keypoint identity across pairs ([artifact.md](artifact.md#no-feature_index)) | the paper's central claim |
| `indoor` (ScanNet) and `outdoor` (MegaDepth) weights are separately trained and not interchangeable | the paper §4 |
| kornia 0.8.3, own base image (`docker/runtime-kornia/`) — the predecessor's two conda envs pinned 0.8.1 and 0.7.1 because LoFTR's `default_cfg` import moved between them, its sharpest dependency conflict; here the stacks never share an environment | implementation record |
| 8-pixel divisibility (the 1/8 grid), handled by bottom-right padding because a pad leaves coordinates unchanged and a resize does not | mechanism |
| the `merge_eps_px` finding: the tracker default (1.5px) leaves LoFTR tracks unable to chain — 3 of 5 images unregisterable on the reference scene — and a synthetic SIFT-minus-`feature_index` experiment endorsed exactly the wrong value, because with a detector the same keypoint recurs at identical coordinates and with LoFTR each pair is independent. Recorded at length: a synthetic test confirming a wrong default is a failure mode worth recognising | measured here; [tuning.md](tuning.md#the-first-thing-to-set-is-not-in-this-module) + the tracker's tuning file |
| merge belongs to the tracker (predecessor's `pseudo_merge_eps_px` lived on the matcher, configuring a merge inside a data structure); the honest obligation here is omitting `feature_index` | predecessor `sfmcore/featurematching.py`, `FeatureMatchLoftrPair` |
| **everything about behaviour in a real pipeline** | **nothing** — run zero times in the sweep; isolated testing and the predecessor only |
| 6 healthy bands; numeric values in `pairing`, `min_confidence`, `max_matches`, `resize_long_edge`, `min_matches` advice | **nothing** — see the audit section in `tuning.md` |
