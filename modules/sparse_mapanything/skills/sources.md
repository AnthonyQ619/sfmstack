---
module: SparseMapAnything
module_version: 1.1.0
curated_at: 2026-09-07
---

# Where SparseMapAnything's claims come from

**Cite-only, like the evidence tier: this file exists to be referenced, not
browsed.** The provenance summary rides `SKILL.md`; unsourced-band warnings sit
in `tuning.md`; the re-check rule is the one global rule in `SKILLS.md`.

| Claim / content | Rests on |
| --- | --- |
| the model accepts geometry as **input** (`intrinsics`, `camera_poses`, `depth_z`, `ray_directions`, `is_metric_scale` all optional; it predicts what is missing) — the capability no other model here has, worth **39% more surviving structure** on the reference run | MapAnything — Keetha, Karhade, Ramanan, Scherer et al.; commit `3d10cf7`, package 1.1.4 |
| it does **not** adopt the supplied frame: estimated depth scale 1.9496 with poses supplied vs 1.9485 without — so the module reads `depth_z` (per-view, frame-agnostic) and unprojects with the supplied poses | measured directly |
| `is_metric_scale` is a trap on SfM poses: asserting metres rescaled depth to honour a false claim — scale moved to 1.3205, spread worsened 0.0059 → 0.0082. Hardcoded false; no pose artifact in this system is metric | measured directly |
| confidence unbounded, near 1 at rest, on a different scale from VGGT's (13.97 vs 60.60 on the same eight views) | measured directly |
| preprocessing: one aspect-preserving target for the whole set from the *average* aspect ratio (4:3 → 518×392, centre-cropped); the pixel map is **derived from the returned intrinsics**, never reimplemented — the direct lesson of the VGGT anisotropic-resize bug (`docs/design/DECISIONS.md`): derive the resize convention, don't assume it | `mapanything.utils.image.preprocess_inputs`, verified |
| licence: default checkpoint `facebook/map-anything` is **CC-BY-NC 4.0 — not commercially usable**; `facebook/map-anything-apache` is the Apache-2.0 alternative, switched by a build arg on `docker/runtime-mapanything/Dockerfile`; the code is Apache 2.0 | upstream licences, recorded not enforced |
| weights baked by pointing `HF_HOME`/`TORCH_HOME` at a baked dir with `HF_HUB_OFFLINE=1` (a cache miss errors instead of fetching) — `save_pretrained` cannot re-save (config carries class objects); the second, easy-to-miss download is the **DINOv2 code** from torch hub | implementation, verified |
| predecessor squeezed to 518×518 with both axes scaled by `518/width` (the VGGT bug again), read `pts3d` in the model's frame (correct only with MapAnything's own poses), never read the `conf_maps` it accepted; this unprojects `depth_z`, picks the highest-confidence observation per track | predecessor `sfmcore/scenereconstruction.py`, `Sparse3DReconstructionMapAnything` |
| **everything about behaviour in a real pipeline** | **nothing** — run zero times in the sweep; isolated testing and the predecessor only |
| 11 healthy bands; numeric values in `use_model_mask`, `min_track_len`, `min_confidence`, `amp_dtype` advice | **nothing** — see the audit section in `tuning.md` |
