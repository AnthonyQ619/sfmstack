---
module: BundleAdjustmentGlobal
module_version: 1.0.0
upstream: pycolmap 4.1.1 / Ceres
curated_at: 2026-08-07
sources: 3
---

Ceres bundle adjustment over every pose and every point at once. CPU-only, no
weights.

**Use when** you have a `sparse_model/v1` from anything. This is the only stage
that revisits earlier decisions: everything upstream is greedy, so drift
accumulates and nothing else corrects it.

**Run it.** It is close to free on a small model (3.7s for 6941 points on the
reference run) and it is the difference between a locally-consistent chain of
estimates and one globally-consistent model. On a scene whose per-stage metrics
already looked healthy it still removed a third of the reprojection error.

**Prefer something else when** — there is no alternative to bundle adjustment as
such. What varies is *scope*: `BundleAdjustmentLocal` refines a window and holds
the rest fixed, which is what you want inside an incremental loop rather than
after it.

**Observations are undistorted pixels**, so the COLMAP cameras built here are
PINHOLE with no distortion terms. That is not an approximation — the distortion
was removed once, upstream, and modelling it again would apply it twice.

**The metric to read:** `reprojection_error_after`. Above ~1.5px at a normal
working resolution, something upstream is wrong and BA cannot fix it —
see [limitations](limitations.md).

**Two traps worth knowing about** (both now handled, both recorded because they
produced plausible numbers rather than errors):

- COLMAP's `compute_mean_reprojection_error()` returns **0.0** on a freshly built
  reconstruction until `update_point_3d_errors()` is called. An earlier version of
  this module reported "before: 0.0, reduction: 0.0" — i.e. a perfect input and a
  useless solve — while actually going 0.376 → 0.253px.
- `pycolmap.bundle_adjustment()` returns `None`, so iteration counts and
  convergence read off it are invented. This module builds the adjuster explicitly
  and reports `converged=0` when it cannot tell, rather than defaulting to true.

**Cheapest thing that usually works:** defaults. Reference run — DTU scan1, 12
images, 6941 points, 22743 observations: **0.376px → 0.253px** (a 32.8% reduction)
in 154 iterations, converged, 5.3s.

**Reading the output:** [artifact.md](artifact.md). Also writes a `colmap`
sidecar, so a pycolmap consumer can open the model natively.
