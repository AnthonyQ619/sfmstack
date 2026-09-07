---
module: BundleAdjustmentLocal
module_version: 1.1.0
curated_at: 2026-09-07
---

# Where BundleAdjustmentLocal's claims come from

**Cite-only, like the evidence tier: this file exists to be referenced, not
browsed.** The provenance summary rides `SKILL.md`; unsourced-band warnings sit
in `tuning.md`; the re-check rule is the one global rule in `SKILLS.md`.

| Claim / content | Rests on |
| --- | --- |
| sliding-window refinement with the rest held fixed | Mouragnon et al., "Real Time Localization and 3D Reconstruction", CVPR 2006 |
| local BA per registration + global BA on growth; window by **covisibility** (this module uses frame order as a proxy — a recorded limitation) | Schönberger & Frahm, CVPR 2016, §4.5; [limitations.md](limitations.md#the-window-is-contiguous-in-frame-order) |
| gauge freedom; local BA gets its gauge from the fixed cameras, hence ≥2 required | Triggs et al., 1999, §6 |
| the `converged` flag: `"CONVERGENCE" in str(termination)` matched `NO_CONVERGENCE` too, reporting `converged: 1` on capped solves — both BA modules now compare the enum name exactly. Follow-on: global BA's reference solve needed 154 iterations against a cap of 100 with **identical** error (0.2531), so the global default became 300. The pattern worth citing: a health flag wrong in the safe direction is worse than no flag | found by direct observation at `window_size: 5`, fixed and re-measured |
| `set_constant_rig_from_world_pose` is the 4.x API for pinning a camera (was `set_constant_pose`) | pycolmap 4.x rig/frame model |
| `window_size=8` default | predecessor `sfmcore/optimization.py`, `BundleAdjustmentOptimizerLocal` — where this class was a constructor argument of the pose estimator, the coupling that made the predecessor impossible to containerise; the alternation now belongs to the orchestrator, and the pose estimator's limitations file records the cost |
| **everything about behaviour in a real pipeline** | **nothing** — run zero times in the sweep; isolated testing and the predecessor only |
| 7 healthy bands; numeric values in `window_size`, `min_track_length` advice | **nothing** — see the audit section in `tuning.md` |
