---
module: BundleAdjustmentLocal
module_version: 1.0.0
curated_at: 2026-08-08
---

# Tuning BundleAdjustmentLocal

## Reference run

DTU scan1, 12 contiguous images, 1024px, SIFT → NN (exhaustive) → UnionFind →
PoseEssentialToPnP → SparseTriangulation. `window_size: 5`:

| anchor | window before | window after | model before | model after |
|---|---:|---:|---:|---:|
| `last` | 0.4855 | **0.3536** | 0.4713 | 0.3842 |
| `first` | 0.5082 | 0.3823 | 0.4713 | 0.3892 |
| `largest_error` | **0.5458** | 0.4247 | 0.4713 | 0.3736 |

3556 points, 5 cameras refined, 7 fixed, in every case.

Two things to read here. `largest_error` picks the genuinely worst window (0.5458
starting error, against 0.4855 and 0.5082) — the anchor selection does what it
says. And it produces the best *model-wide* result (0.3736) while producing the
worst *window* result, because it was given the hardest part of the model to fix.

## `window_size` — the cost/benefit dial

Cost grows roughly with the square of the window for the dense part of the solve.

- **Below ~4**: too little freedom for the solve to do anything useful.
- **8** (default): a reasonable working value.
- **Above ~30**: you are approaching global BA and should use that instead — it
  fixes the gauge properly rather than by freezing arbitrary cameras.

Watch `cameras_fixed`. If it drops to 2 on a model much larger than the window,
the `window_covers_model` diagnostic fires and it is telling you the truth.

## `anchor`

- **`last`** — the incremental SfM case: refine the cameras just registered.
- **`first`** — refine around the seed pair. Useful when you suspect the
  initialisation, which is the one part of an incremental model that everything
  else was built against.
- **`largest_error`** — centre the window on the camera with the worst mean
  reprojection error. The right choice when running this as a targeted repair
  rather than as part of a sweep.

The window is contiguous in **frame** order, not registration order, because it is
meant to be a spatial neighbourhood and frame order is the only proxy available
without reading the view graph. On an unordered photo collection frame order means
nothing and this module is the wrong tool.

## `converged` is 0

Measured: at the default 50 iterations the reference solve did not converge; at 400
it did, with an **identical** window error (0.3536 both times).

So the practical question is not "did it converge" but "did the error stop moving".
If `window_error_after` is where you want it, a `converged: 0` at the iteration cap
costs nothing but the flag. Raise `max_iterations` when you want the flag to be
meaningful — which you do if you are running this in a loop and using convergence
as the stopping condition.

If it does not converge at a high cap, the input is the problem, not the budget.

## `window_error` does not move

Either the window was already at a local minimum — fine, if the error is low — or
you are refining a part of the model that did not need it. Try
`anchor: largest_error`.

## `min_track_length` defaults to 3 here, not 2

Deliberately different from global BA. Inside a window most points are seen by few
of the refined cameras, and a two-view point contributes nothing a local solve can
use — it has exactly as many constraints as unknowns and can only slide along its
ray.

Lower it to 2 only if `points_optimized` is too small to constrain the window, and
treat needing that as a signal about the cloud rather than about this parameter.

## When to use global BA instead

- The model is small enough that global BA is affordable. On the reference scene
  global BA took 5.3s for all 12 cameras against ~1s for a 5-camera window — the
  local version is not buying much at this size.
- You need drift between distant parts corrected. Local BA structurally cannot do
  this.
- `window_covers_model` fired.
