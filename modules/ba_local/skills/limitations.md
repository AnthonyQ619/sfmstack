---
module: BundleAdjustmentLocal
module_version: 1.0.0
curated_at: 2026-08-08
---

# What local bundle adjustment cannot do

Everything in [`BundleAdjustmentGlobal`'s limitations](../../ba_global/skills/limitations.md)
applies — it cannot escape a bad local minimum, fix wrong correspondences, recover
scale, or improve a two-view point. Plus these, which are specific to being local.

## It cannot correct drift between distant cameras

*Symptom:* every window you refine improves, and the model as a whole stays bent.

*Why no parameter helps:* cameras outside the window are constants in the solve.
Accumulated error between the start and end of a sequence is precisely a
relationship between distant cameras, and no window that excludes one of them can
see it.

*What to do:* run `BundleAdjustmentGlobal` once at the end. That is the intended
division of labour, not a fallback.

## The window is contiguous in frame order

*Symptom:* on an unordered photo collection, the "window" is an arbitrary set of
images that may share no structure at all.

*Why:* frame order is used as a proxy for spatial neighbourhood. For video or an
ordered capture it is a good proxy. For a folder of holiday photos it is
alphabetical and means nothing.

*What to do:* use global BA on unordered collections. A view-graph-aware window —
selecting cameras by covisibility rather than by index — is the principled fix and
is not implemented; it would need this module to consume the matches or the tracks
as well, which is a real coupling and was not worth it before there was evidence it
is needed.

## Thin windows

*Symptom:* `too_few_points`, or `points_optimized` in the tens.

The window's cameras share too little structure. Either the window is too small, or
the part of the model it covers is weakly connected — which is itself a finding
worth chasing upstream, in the matcher's `min_matches_per_pair` and the tracker's
`min_frame_observations`.

Raising `window_size` is the direct fix. Lowering `min_track_length` to 2 admits
points the solve cannot use, so it raises the count without helping.

## At least two cameras must be fixed

pycolmap needs two constant poses to pin the 7-dof gauge. If the window would leave
fewer, this module silently shrinks the window rather than failing — refining all
but two — and reports the real counts in `cameras_refined` / `cameras_fixed`.

That is a deliberate degradation and it means `cameras_refined` can be smaller than
`window_size` without anything being wrong. On a model of 6 cameras with
`window_size: 8`, you get 4 refined and 2 fixed.

If the whole model fits in the window, use global BA. The `window_covers_model`
diagnostic says so.

## It is not obviously worth it at small scale

Recorded because the honest answer on the reference scene is "use the global one".

12 cameras, 6941 points: global BA is 5.3s and corrects everything. A 5-camera
local window is ~1s and corrects part of it. The crossover where local BA earns its
place is a model large enough that global BA is too slow to run repeatedly —
hundreds of cameras — which nothing in this repo has yet reached.

The reason it exists now is that the predecessor's pose estimator called it as a
nested sub-step, and reproducing that behaviour as an ordinary module (rather than
as a constructor argument to another module) was the point.
