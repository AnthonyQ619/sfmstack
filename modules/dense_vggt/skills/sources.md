---
module: DenseVGGT
module_version: 1.2.0
curated_at: 2026-09-07
---

# Where DenseVGGT's claims come from

**Cite-only, like the evidence tier: this file exists to be referenced, not
browsed.** The provenance summary rides `SKILL.md`; unsourced-band warnings sit
in `tuning.md`; the re-check rule is the one global rule in `SKILLS.md`.

| Claim / content | Rests on |
| --- | --- |
| the depth head, and the preprocessing letterbox shared with `PoseVGGT`/`SparseVGGT` | VGGT — Wang, Leroy, Cabon, Chidlovskii, Revaud et al., CVPR 2025; <https://arxiv.org/abs/2503.11651>; commit `a288dd0` |
| **confidence is unbounded above** (measured mean 46.6 on a controlled-rig capture) — treating it as 0–1 is the likeliest misconfiguration, which is why `min_confidence` documents it and the failure message repeats it | measured directly on the pinned checkpoint |
| depth is predicted for the whole 518-square **including the letterbox padding**, which gets a plausible depth — so only the image region is unprojected, else every view grows a flat sheet at its edge | observed directly |
| unprojection into the supplied frame (predecessor read point maps in VGGT's own frame, composed only with VGGT poses, had no scale handling, and unprojected the padding) | predecessor `sfmcore/scenereconstruction.py`, `Dense3DReconstructionVGGT` |
| **behaviour in a real pipeline** | one dense batch, as a comparison arm only — `skills/evidence/dense-batch-2026-09.md`, which is where its accuracy against reference geometry and its behaviour as a hole-filler come from. No capture has shipped its cloud as a deliverable; everything else here is isolated testing and the predecessor |
| 4 healthy bands; numeric values in `stride`, `min_confidence`, `depth_scale`, `write_ply` advice | **nothing** — see the audit section in `tuning.md` |
