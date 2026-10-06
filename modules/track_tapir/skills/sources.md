---
module: FeatureTrackTapir
module_version: 1.5.0
curated_at: 2026-09-07
---

# Where FeatureTrackTapir's claims come from

**Cite-only, like the evidence tier: this file exists to be referenced, not
browsed.** The provenance summary rides `SKILL.md`; unsourced-band warnings sit
in `tuning.md`; the re-check rule is the one global rule in `SKILLS.md`.

| Claim / content | Rests on |
| --- | --- |
| the tracker | TAPIR — Doersch et al., ICCV 2023; BootsTAPIR = TAPIR + self-supervised bootstrapping, architecturally `extra_convs=True` and nothing else — Doersch et al., 2024 |
| checkpoint `bootstapir_checkpoint_v2.pt` (209 MB, 54.7M params), baked; loads with **0 missing / 0 unexpected** keys at `pyramid_level=1`, asserted at build — the module loads `strict=False` for non-default pyramid levels, and without the build assert that would hide a mismatched checkpoint completely | build verification |
| confidence = `(1 − σ(occlusion)) · (1 − σ(expected_dist))` per upstream demos; reporting the occlusion term separately as `mean_occlusion` is this module's addition — it distinguishes "the point left view" from "the model cannot localise it" | upstream demos + design decision |
| conventions that silently transpose or mis-scale: query points are `(t, y, x)` (swapping tracks the transpose of the scene, no crash); output tracks `(B, N, T, 2)` — points-first, the OPPOSITE of VGGSfM's `(B, T, N, 2)`; video is channel-last in [−1, 1] | verified against tapnet commit `c2cbab8` |
| `--no-deps` install: `tapnet`'s declared deps are JAX-first, none on the torch path; `tapnet.torch.tapir_model` needs numpy, torch, `dm-tree`, `einshape`, installed explicitly — the alternative is 2 GB of unused JAX beside torch fighting for the same GPU allocator | package inspection (Apache 2.0) |
| predecessor: no dedup (measured 5506 raw tracks, 2736 distinct — 50% duplicates entering BA multiple times), no bounds check, `resize_to=None` ran the model at full scene resolution far outside its training distribution (768 already measures worse than 384 on every track metric), discarded the occlusion term, hardcoded a local checkpoint path | predecessor `sfmcore/featuretracking.py`, `FeatureTrackingTapir` |
| **behaviour in a real pipeline** | **partially measured.** Run on corpus captures against `FeatureTrackUnionFind` on the same stored scene and SIFT features: see [`evidence/features-only-tracking-2026-10.md`](../../../skills/evidence/features-only-tracking-2026-10.md). Everything else is isolated testing and the predecessor only |
| 7 healthy bands; numeric values in `query_frame_num`, `input_size`, `min_confidence`, `pyramid_level`, `dedupe_eps_px` advice | **nothing** — see the audit section in `tuning.md` |
| the 8-view comparison table in `SKILL.md` and the resolution figures in `limitations.md`; the 16-view masonry-courtyard reconstruction that deduplication-off broke | one DTU studio rig orbit at 8 views and one ETH3D masonry courtyard at 16, isolated testing on single captures |
