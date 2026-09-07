---
module: FeatureTrackUnionFind
module_version: 1.4.0
curated_at: 2026-09-07
---

# Where FeatureTrackUnionFind's claims come from

**Cite-only, like the evidence tier: this file exists to be referenced, not
browsed.** The provenance summary rides `SKILL.md`; unsourced-band warnings sit
in `tuning.md`; the re-check rule is the one global rule in `SKILLS.md`.

| Claim / content | Rests on |
| --- | --- |
| tracks as connected components of the verified scene graph; COLMAP's departure — it **refuses** inconsistency-creating merges during registration rather than merging and cleaning up. This module does the cleanup version, which is why `on_conflict` exists ([limitations.md](limitations.md#what-would-replace-this-implementation-specifically)) | Schönberger & Frahm, CVPR 2016, §4 |
| union by size with path halving — inverse-Ackermann amortised; halving over full compression because it needs no second pass | Tarjan 1975; standard practice |
| a track with two keypoints from one image is inconsistent — the origin of the `drop` policy; `first` exists only because the predecessor implemented it by accident (last-write-wins in a per-frame dict), kept for comparability, **not recommended** | Snavely, Seitz, Szeliski, "Photo Tourism", SIGGRAPH 2006, §4.2 |
| the ratio-test / track-length interaction: across a `ratio_test` sweep 0.7 → 1.0, `avg_track_length` rises monotonically while `inlier_ratio` falls 0.97 → 0.22 and `inconsistent_rate` rises 58× — track length improves as the pipeline degrades ([tuning.md](tuning.md#avg_track_length-is-not-a-quality-metric)) | measured in this repository |
| four-offset-lattice proximity merging: any interval under half a cell fits some cell of some grid; over a KD-tree (sfmkit allows numpy only) and over a single grid (which fails exactly on the subpixel jitter it must absorb); verified by test at 0.5px/1.5eps and 0.1eps | standard construction + tests |
| `merge_eps_px` descends from the predecessor's `pseudo_merge_eps_px`, same 1.5px default; the predecessor conflated pairwise container, track container and observation registry in one class — the split into `pairwise_matches/v1` and `tracks/v1` is what makes this a single function | predecessor `sfmcore/featuretracking.py` + `featmatchDT.PointsMatched` |
| `unmergeable_input` was declared and never emittable — the module RAISES on detector-free matches with `merge_eps_px` 0; the declaration is gone, the raise's message says more than the diagnostic did | manifest audit, corrected |
| every measured band and episode | **84 runs** at 1.4.0 in the seventeen-capture sweep — the most-run tracker; scope pinned by `evidence/CORPUS.txt` |
| 3 healthy bands; numeric values in `min_track_len`, `probe_merge_headroom`, `merge_eps_px` advice | **nothing** — see the audit section in `tuning.md` |
