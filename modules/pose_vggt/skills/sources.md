---
module: PoseVGGT
module_version: 1.2.0
curated_at: 2026-09-07
---

# Where PoseVGGT's claims come from

**Cite-only, like the evidence tier: this file exists to be referenced, not
browsed.** The provenance summary rides `SKILL.md`; unsourced-band warnings sit
in `tuning.md`; the re-check rule is the one global rule in `SKILLS.md`.

| Claim / content | Rests on |
| --- | --- |
| alternating frame-wise and global attention over the whole set; cameras, depth, point maps and tracks read off aggregated tokens in one forward pass — this module uses the camera head only. Needs no correspondences; accuracy is **initialisation-grade**, trained to be right about geometry, not to minimise reprojection on your scene | VGGT — Wang, Leroy, Cabon, Chidlovskii, Revaud et al., CVPR 2025; <https://arxiv.org/abs/2503.11651> |
| commit `a288dd0`, checkpoint `facebook/VGGT-1B` (5 GB) baked into the image — the HF cache follows `HOME`, and the container runs as the host uid with `HOME=/tmp`, so a hub-cached file written as root at build is not where the module looks at run time | implementation, verified |
| `aggregator(images)` takes `(B, N, 3, 518, 518)` — a single set is `images[None]`; `pose_encoding_to_extri_intri` returns **cam_from_world** 3×4 OpenCV, matching `poses/v1`, with intrinsics in pixels of the 518-square; the module implements `pad` preprocessing itself so it can invert it exactly in the intrinsics | verified against the commit |
| **the anisotropic-squeeze bug and its measurement**: squeezing to 518×518 produced `fx/fy` = 1.329 (exactly the source aspect ratio) and a focal 1.48× calibration, because VGGT predicts square pixels; letterboxing took `estimated_focal_ratio` 1.48 → 1.095, triangulated points 1315 → 5899, reprojection error 1.943 → 1.051 px | measured directly |
| no stitching stage; chunking is a hard boundary — VGGT replaced DUSt3R/MASt3R's pairwise-then-align design with whole-set attention, so there is no alignment to fall back on | DUSt3R — Wang, Leroy et al., CVPR 2024 |
| letterboxes any aspect (predecessor asserted square input); writes its estimate into its own artifact (predecessor rewrote the scene's calibration in place); camera head in full precision because the decode produces a rotation (predecessor used autocast) | predecessor `sfmcore/camerapose.py`, `CamPoseEstimatorVGGTModel` |
| **behaviour as a delivery path** | measured. Run over all seventy-five captures of the pose batch as a scoring arm, and measured as the DELIVERY on the captures where the geometric core came back short: at `registered_fraction` at or below about 0.7 this module's own model was the better delivery than the short core on three of the four corpus captures that reached that point, by as much as 0.56 AUC@30 over all pairs, and on captures that registered every frame it was worse. The exception is a capture whose geometry is degenerate — a coherent reflector between camera and scene, no parallax — where this module scored zero and the seven-camera core won. [`evidence/short-core-2026-10.md`](../../../skills/evidence/short-core-2026-10.md) |
| 4 healthy bands; numeric values in `max_images_per_pass`, `dtype` advice | **nothing** — see the audit section in `tuning.md` |
