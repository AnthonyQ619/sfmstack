---
module: SparseVGGT
module_version: 1.1.0
curated_at: 2026-09-07
---

# Where SparseVGGT's claims come from

**Cite-only, like the evidence tier: this file exists to be referenced, not
browsed.** The provenance summary rides `SKILL.md`; unsourced-band warnings sit
in `tuning.md`; the re-check rule is the one global rule in `SKILLS.md`.

| Claim / content | Rests on |
| --- | --- |
| the depth head, pinned at commit `a288dd0`: `depth_head(tokens, images=, patch_start_idx=)` → `(depth, confidence)` shaped `(B, N, 518, 518, 1)` / `(B, N, 518, 518)`; preprocessing is the same `pad` letterbox as `PoseVGGT` — and here it also decides which pixel an observation samples depth from | VGGT — Wang, Leroy, Cabon, Chidlovskii, Revaud et al., CVPR 2025; verified against the commit |
| **why the depth head and not the point head**: point maps live in VGGT's own frame at VGGT's own scale — correct only with VGGT poses, silently wrong otherwise; depth is per-view and frame-agnostic, so unprojecting with the supplied K and pose lands in the supplied frame by construction, leaving one scale ambiguity estimated from the tracks and reported with its spread | design decision + the validation below |
| the scale estimator validated, not just producing a number: fed `PoseVGGT`'s own poses, `depth_scale` = **1.0044** (unity — the units already agree); fed classical poses on the same scene, 2.1164 at the same 0.004 spread | measured directly |
| observation choice: the highest-confidence observation per track (predecessor took `views[0]` and accepted `conf_maps` it never read); predecessor's track filter kept tracks **shorter** than the minimum (`< minimum_observation`) — intent unrecoverable; `min_track_len` here keeps tracks that reach it; predecessor had no scale handling because point maps made the question invisible | predecessor `sfmcore/scenereconstruction.py`, `Sparse3DReconstructionVGGT` |
| **everything about behaviour in a real pipeline** | **nothing** — run zero times in the sweep; isolated testing and the predecessor only |
| 11 healthy bands; numeric values in `min_track_len`, `min_confidence` advice | **nothing** — see the audit section in `tuning.md` |
