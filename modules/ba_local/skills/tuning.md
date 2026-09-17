---
module: BundleAdjustmentLocal
module_version: 1.2.1
curated_at: 2026-08-08
---

# Tuning BundleAdjustmentLocal

## Reference run

One capture: a short contiguous arc of twelve calibrated frames around a small,
well-textured object on a plain backdrop, at about 1 MP, through a classical
detector → ratio-test matcher (exhaustive) → union-find tracker → incremental
poses → pairwise triangulation. `window_size: 5`:

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

**Correction, measured.** "BA cannot improve it" is too strong, and the constraint
count behind it is wrong: a two-view point has FOUR residuals against THREE
unknowns. What is true is that it carries no redundancy of its own, so it gains
least. What is false is that it gains nothing — the cameras move during the solve
and the point moves with them. Measured through a bundle adjustment on two separate
captures, two-view points improved by 12.9% and 2.5%. That matters because this
claim is the whole justification for `min_track_length: 3`, which on a
two-view-dominated cloud deletes half the model.

Lower it to 2 only if `points_optimized` is too small to constrain the window, and
treat needing that as a signal about the cloud rather than about this parameter.

**A dense stage downstream is not a reason to lower it.** That was asserted here
from a cross-capture correlation and has since been tested directly: deleting a third
to three fifths of a model's points by raising this filter changed the dense stage's
completeness by **+0.0000 mm** across a corpus of studio orbits. Choose it for the
window's sake, not the densifier's. See
[plan/dense.md](../../../skills/plan/dense.md#planning-the-sparse-stage-for-a-dense-deliverable).

**The deletion is now announced rather than left to be noticed.**
`points_dropped_by_min_track_length` fires whenever the filter takes points out,
because nothing in the metrics could reveal it: `points_optimized` counts the
window, so it cannot separate a point this filter deleted from one that merely lies
outside the window, and `point_count` describes the output without a before to
compare against. Read `two_view_fraction` on the INPUT model to predict the size of
the loss before running — that reading is the same one that decides whether this
module or the global one suits the cloud at all.

## When to use global BA instead

- The model is small enough that global BA is affordable. On the reference scene
  global BA took 5.3s for all 12 cameras against ~1s for a 5-camera window — the
  local version is not buying much at this size.
- You need drift between distant parts corrected. Local BA structurally cannot do
  this.
- `window_covers_model` fired.

## Metrics that mislead

`reprojection_error_after` is the **whole model**, most of which was deliberately
not optimised. It understates what the module did. `window_error_after` is the one
to judge on: 0.3536 against 0.3842 on the reference run.

`converged` at the default `max_iterations: 50` is frequently 0 with no practical
consequence — the reference solve reached an identical answer converged or not.
Read it together with whether `window_error_after` is where you want it.

`cameras_refined` can be less than `window_size` when the model is small, because
two cameras must stay fixed to pin the gauge.

## What here rests on nothing — the manifest audit

Audited against this module's own manifest. **Seven healthy bands**
(`min_frame_points`, `p95_reprojection_error`, `window_error_before`,
`observation_count`, `mean_track_length`, `mean_reprojection_error`, and one
more) declare a range no diagnostic reads — each is a description of the
captures measured so far, not a judgement on yours. The numbers in the
`window_size` and `min_track_length` advice are settings that worked here, not
published results. And this module has run **zero times** in a real pipeline,
so every band here comes from isolated testing.
