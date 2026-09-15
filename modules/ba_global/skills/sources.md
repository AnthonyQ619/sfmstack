---
module: BundleAdjustmentGlobal
module_version: 1.2.1
curated_at: 2026-09-07
---

# Where BundleAdjustmentGlobal's claims come from

**Cite-only, like the evidence tier: this file exists to be referenced, not
browsed.** The provenance summary rides `SKILL.md` (inlined into every describe
call); warnings about unsourced bands sit in `tuning.md` beside the bands; the
re-check rule is the one global rule in `SKILLS.md`.

| Claim / content | Rests on |
| --- | --- |
| sparse normal-equation structure; gauge must be pinned (`TWO_CAMS_FROM_WORLD` — else the solve wanders the 7-dim similarity manifold) | Triggs, McLauchlan, Hartley, Fitzgibbon, "Bundle Adjustment — A Modern Synthesis", 1999, §3–4, §6 |
| Cauchy robust loss family | Triggs et al. §5.3; the **default-on** choice is judgement, not citation (predecessor used Huber) |
| `compute_mean_reprojection_error()` returns **0.0** until `update_point_3d_errors()` is called | pycolmap 4.1.1, observed directly |
| `pycolmap.bundle_adjustment(...)` returns `None`; convergence must come from `create_default_bundle_adjuster(...).solve()` | pycolmap 4.1.1 API |
| Ceres knobs live at `options.ceres.solver_options`; unknown attributes raise | pycolmap 4.1.1 API |
| the BA/retriangulate/filter alternation belongs at orchestrator level, not nested in the module | Schönberger & Frahm, CVPR 2016, §4.5 |
| `refine_*` defaults (all False); `max_num_iterations` raised 50→100 (then 300 after the converged audit — see `BundleAdjustmentLocal`'s sources for the bug that found it) | predecessor `sfmcore/optimization.py`, `BundleAdjustmentOptimizerGlobal` |
| every measured band and episode in these skills | 88 runs at 1.1.0 across the seventeen-capture sweep — scope pinned by `evidence/CORPUS.txt`; no out-of-corpus capture |
| 7 healthy bands; numeric values in `max_iterations`, `loss_scale`, `min_track_length` advice | **nothing** — see the audit section in `tuning.md` |
