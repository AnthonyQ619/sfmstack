---
module: FeatureTrackVGGSfM
module_version: 1.5.0
curated_at: 2026-09-07
---

# Where FeatureTrackVGGSfM's claims come from

**Cite-only, like the evidence tier: this file exists to be referenced, not
browsed.** The provenance summary rides `SKILL.md`; unsourced-band warnings sit
in `tuning.md`; the re-check rule is the one global rule in `SKILLS.md`.

| Claim / content | Rests on |
| --- | --- |
| only the **tracker** is used (not the camera predictor or triangulator); weights `vggsfm_v2_tracker.pt` (186 MB), baked; stride-8 coarse correlation iterated by `coarse_iters`, stride-1 local refinement by `fine_tracking` — off leaves positions accurate to several pixels | VGGSfM — Wang, Karaev, Rupprecht, Novotny, CVPR 2024 |
| reached through VGGT's vendored copy (`vggt.dependency.vggsfm_tracker`, commit `a288dd0`) — avoids a second research-licensed clone and a pytorch3d dependency the tracker never calls | implementation decision, verified |
| the vendored copy computes **no per-observation score** (`compute_score=False` → `None`), so the predecessor's `score_threshold` was inert — not exposed here; its architecture is hardcoded (no hydra configs), so the predecessor's dozen architecture parameters cannot vary and are absent from this manifest; `vggsfm_utils` imports pycolmap/hydra/lightglue at module scope unused — in the image because the import fails without them | verified against the vendored copy |
| **weights are CC-BY-NC 4.0** — recorded, not enforced (same treatment as SuperGlue and MapAnything's default) | upstream licence |
| `dino` query selection ranks by DINOv2 CLS similarity + farthest-point sampling; loads `dinov2_vitb14_reg` — a second 330 MB download, baked, and the easy one to miss: an image built without it works under `interval` and fails under `dino` | `generate_rank_by_dino` in `vggsfm_utils` |
| why frame 0 is not privileged: tracking from frame 0 leaves each point visible in a mean of 1.77 frames vs 4.40 from a mid-sequence frame on eight views — an endpoint of a sequential capture sees the least of the scene; both predecessor behaviours (anchor at 0, always prepend 0) dropped | measured directly |
| predecessor: no dedup (7329 raw tracks, 4033 distinct — 45% duplicates), `sorted(...)[:n]` returned the numerically smallest frame indices rather than the best-ranked (so `query_selection` had less effect than it appeared), no bounds check (extrapolated positions written as observations — dropped and counted here), inert `score_threshold` exposed | predecessor `sfmcore/featuretracking.py`, `FeatureTrackingVGGSfM` |
| **everything about behaviour in a real pipeline** | **nothing** — run zero times in the sweep; isolated testing and the predecessor only |
| 4 healthy bands; numeric values in 8 parameters' advice | **nothing** — see the audit section in `tuning.md` |
