---
module: BundleAdjustmentLocal
module_version: 1.1.0
curated_at: 2026-08-08
---

# Sources

## Local bundle adjustment

**Mouragnon, Lhuillier, Dhome, Dekeyser, Sayd, "Real Time Localization and 3D
Reconstruction", CVPR 2006** is the standard reference for refining a sliding
window of recent cameras while holding the rest fixed, in an incremental pipeline.

**Schönberger and Frahm, CVPR 2016** (COLMAP), section 4.5, uses the same idea:
local BA after each registration over the most-connected images, global BA after
the model grows by a set fraction. COLMAP selects the window by **covisibility**
rather than by index; this module uses frame order as a proxy, which is a real
limitation on unordered collections and is recorded in
[limitations.md](limitations.md#the-window-is-contiguous-in-frame-order).

## Gauge freedom

**Triggs et al., "Bundle Adjustment — A Modern Synthesis", 1999**, section 6.
A reconstruction is determined only up to a similarity, so the solve needs the
gauge pinned. Global BA here uses
`BundleAdjustmentGauge.TWO_CAMS_FROM_WORLD`; local BA gets it for free from the
fixed cameras, which is why at least two are required.

## The `converged` bug, recorded because it is instructive

The first working version of both BA modules reported `converged: 1` on solves that
had hit the iteration cap.

The cause: `"CONVERGENCE" in str(termination).upper()`. Ceres reports
`NO_CONVERGENCE` for a solve that ran out of iterations, and `"CONVERGENCE"` is a
substring of `"NO_CONVERGENCE"`. The substring test therefore returned True on
exactly the cases the metric exists to catch, and False on nothing.

It was found by running this module at `window_size: 5` and noticing Ceres printing
`Termination: NO_CONVERGENCE` beside a metric saying `converged: 1`. Both modules
now compare the enum **name** exactly.

The follow-on: with the flag fixed, global BA on the DTU reference scene turned out
never to have converged either — it needs 154 iterations and the default cap was
100. The reprojection error was identical at both settings (0.2531), so nothing
except the flag distinguished them. The global default is now 300.

Worth recording as a pattern rather than a one-off: a health flag that is wrong in
the safe-looking direction is worse than no flag, because it suppresses the
diagnostic that would have prompted the check.

## Implementation

`pycolmap.BundleAdjustmentConfig.set_constant_rig_from_world_pose` is what makes a
camera constant in the 4.x API. Earlier pycolmap versions used
`set_constant_pose`; the rig/frame model introduced in 4.x renamed it.

`options.ceres.solver_options.max_num_iterations` — the Ceres knobs are one level
below `options.ceres`, and the object rejects unknown attributes, so a wrong path
is an `AttributeError` at solve time rather than a silently ignored setting.

## Predecessor code

`scene_agent/breadth_agent/src/sfmcore/optimization.py`,
`BundleAdjustmentOptimizerLocal` (lines 28-332). Same `window_size=8` default.

The substantive difference is structural rather than algorithmic. There, this class
was instantiated and passed as the `optimizer` constructor argument to
`CamPoseEstimatorEssentialToPnP`, which called it every `ba_per_frame` frames. One
module's behaviour was a function of another module's live object, which is
precisely the coupling that made the predecessor impossible to containerise.

Here it is an ordinary module, and the alternation — register, refine, register — is
expressed by the orchestrator. The cost is that the pose estimator no longer
refines as it goes; see its limitations file, which records this as a known gap.
