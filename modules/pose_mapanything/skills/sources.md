---
module: PoseMapAnything
module_version: 1.0.0
curated_at: 2026-09-25
---

# Where PoseMapAnything's claims come from

**Cite-only, like the evidence tier: this file exists to be referenced, not
browsed.** The provenance summary rides `SKILL.md`; unsourced-band warnings sit in
`tuning.md`; the re-check rule is the one global rule in `SKILLS.md`.

| Claim / content | Rests on |
| --- | --- |
| a single feed-forward pass over the whole set predicts cameras, depth and point maps; geometry may be supplied as **input** but nothing is supplied here — this module uses the camera head only, unconditioned | MapAnything — Keetha, Karhade, Ramanan, Scherer et al.; commit `3d10cf7`, package 1.1.4 |
| `camera_poses` is camera-to-world 4×4 in the model's own frame at its own scale, inverted here to the cam-from-world `poses/v1` declares; `is_metric_scale` never asserted | verified against the commit |
| preprocessing is an aspect-preserving resize plus a centre crop, which is affine, so the model's returned `K` and the scene's image size invert it with one scale and an offset — the mapping is **derived from the returned intrinsics, never reimplemented** | `mapanything.utils.image.preprocess_inputs`, verified; the derivation rule is `docs/design/DECISIONS.md` on the VGGT anisotropic-resize bug |
| licence: default checkpoint `facebook/map-anything` is **CC-BY-NC 4.0 — not commercially usable**; `facebook/map-anything-apache` is the Apache-2.0 alternative, switched by a build arg on `docker/runtime-mapanything/Dockerfile`; the code is Apache 2.0 | upstream licences, recorded not enforced |
| weights baked by pointing `HF_HOME`/`TORCH_HOME` at a baked dir with `HF_HUB_OFFLINE=1`; the second, easy-to-miss download is the **DINOv2 code** from torch hub | shared with `SparseMapAnything`; implementation, verified |
| **that a second correspondence-free estimator makes the comparison readable at all** — one estimator alone condemns scenes where the estimator, not the model, is the outlier, and misses scenes where the disagreement is small in absolute terms but large against the estimators' own spread | measured across 35 scored captures; `skills/evidence/consensus-2026-09.md` |
| **that two learned estimators can agree tightly and both be wrong** on a scene outside their training distribution, and that the delivered model can be the better reconstruction in exactly that case | measured; same campaign file |
| the failure this module exists to catch: a matcher wrong in a globally consistent way, two matchers agreeing to a few per cent, the lowest held-out residual in its batch, and a cloud metres out | measured; same campaign file |
| **everything about behaviour as a delivery path** | **nothing** — this module is never delivered from; it is read, not shipped |
| 7 healthy bands; every numeric value in `tuning.md` and the cost figures in `SKILL.md` | **nothing** — see the audit section in `tuning.md` |
