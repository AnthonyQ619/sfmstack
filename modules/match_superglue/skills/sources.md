---
module: FeatureMatchSuperGlue
module_version: 1.6.0
curated_at: 2026-09-07
---

# Where FeatureMatchSuperGlue's claims come from

**Cite-only, like the evidence tier: this file exists to be referenced, not
browsed.** The provenance summary rides `SKILL.md`; unsourced-band warnings sit
in `tuning.md`; the re-check rule is the one global rule in `SKILLS.md`.

| Claim / content | Rests on |
| --- | --- |
| self-/cross-attention over both keypoint sets + a Sinkhorn optimal-transport layer with dustbin row/column — the assignment is one-to-one **by construction**, which is why there is no `mutual` parameter | SuperGlue — Sarlin, DeTone, Malisiewicz, Rabinovich, CVPR 2020; <https://arxiv.org/abs/1911.11763> |
| **licence: research use only, not redistributable** — code and weights are cloned from upstream at build (pinned `ddcf11f`), never vendored; the image needs network to build and must not be pushed publicly | upstream repository licence |
| `forward()` reads `data['image0'].shape[2:]` — it wants a TENSOR shaped like the image (the predecessor's vendored copy was edited to take `image_size0`, which upstream rejects with `KeyError`); `matches0[k]` is the matched index in image 1 or −1; weights load relative to the module file, so the repo layout must survive in the image | verified against commit `ddcf11f` |
| successor context: LightGlue is faster and generally more accurate; its confidence comes from a matchability head, not Sinkhorn, so the two modules' scores are **not comparable** | LightGlue — Lindenberger et al., ICCV 2023 |
| the 256-dim SuperPoint descriptor is the hard constraint this module refuses to violate | SuperPoint — DeTone et al., CVPRW 2018 |
| keypoint truncation is by detector score with a metric reporting the discard (predecessor truncated silently); view graph is a parameter | predecessor `sfmcore/featurematching.py`, `FeatureMatchSuperGluePair` |
| **everything about behaviour in a real pipeline** | **nothing** — run zero times in the sweep; isolated testing and the predecessor only |
| 5 healthy bands; numeric values in `match_threshold`, `sinkhorn_iterations`, `max_keypoints`, `window` advice | **nothing** — see the audit section in `tuning.md` |
