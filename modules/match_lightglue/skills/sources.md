---
module: FeatureMatchLightGlue
module_version: 1.6.0
curated_at: 2026-09-07
---

# Where FeatureMatchLightGlue's claims come from

**Cite-only, like the evidence tier: this file exists to be referenced, not
browsed.** The provenance summary rides `SKILL.md`; unsourced-band warnings sit
in `tuning.md`; the re-check rule is the one global rule in `SKILLS.md`.

| Claim / content | Rests on |
| --- | --- |
| adaptive depth (`depth_confidence`: per-layer exit) and width (`width_confidence`: unmatchable keypoints pruned); both roughly free in accuracy, which is why `depth_confidence` is the speed lever over `n_layers` (the latter weakens every pair, including the hard ones) | Lindenberger, Sarlin, Pollefeys, "LightGlue", ICCV 2023 |
| joint assignment via self-/cross-attention over both keypoint sets — the substantive difference from a ratio test, which evaluates each keypoint in isolation | inherited from SuperGlue (Sarlin et al., CVPR 2020) |
| separate checkpoints per descriptor (SuperPoint, DISK, ALIKED, SIFT, DoG-HardNet) — input projection and positional encoding differ, so **the wrong checkpoint does not error**: it produces a confident, meaningless assignment. `weights: auto` exists for this; `mean_match_score` is the after-the-fact detector | the paper §4 + released checkpoints |
| `sift`/`doghardnet` checkpoints require keypoint scale+orientation (`add_scale_ori`); SuperPoint/ALIKED artifacts carry neither, so the module raises instead of hitting a shape error deep in the model | checkpoint configs, observed |
| the classical stack beat the learned stack **2.6×** on final reprojection error while losing every intermediate metric, on a controlled-rig capture — consistent with the papers (published gains are on HPatches/MegaDepth/Aachen, chosen for illumination and viewpoint difficulty) | measured here; [limitations.md](limitations.md#captures-inside-the-classical-detectors-design-envelope), `docs/design/DECISIONS.md` |
| `filter_threshold`'s criterion moved from the tracker's `inconsistent_rate` to this module's own `cycle_merge_rate + cycle_split_rate`: the old instrument read flat across the deciding range twice (cycle sum fell 7.7× vs 1.17×; 0.005 movement across a 5→30-frame registration change), and it cost a tracker run per sweep point. Two measured limits on the replacement: the merge term alone is not the forecast (0.0016 beside a 17% self-contradictory table), and the sum prices a difference within a capture, never a level across captures (the constant varies ~4×) | measured across the seventeen-capture sweep; family statement in [`skills/plan/matching.md`](../../../skills/plan/matching.md) |
| pinned git install (predecessor vendored the source); `detector` inferred from provenance and cross-checked against descriptor width (predecessor's free-text default would run SuperPoint weights on SIFT features silently); exhaustive pairing available (predecessor sequential-only) | predecessor `sfmcore/featurematching.py`, `FeatureMatchLightGluePair` |
| every measured band and episode | **75 runs** at 1.6.0 in the seventeen-capture sweep — the most-run matcher; scope pinned by `evidence/CORPUS.txt` |
| 6 healthy bands; numeric values in `window`, `filter_threshold`, `n_layers`, `depth_confidence`, `width_confidence` advice | **nothing** — see the audit section in `tuning.md` |
