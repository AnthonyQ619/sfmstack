# Optimization — choosing a bundle adjuster

`sparse_model/v1` in, `sparse_model/v1` out. The only family whose input and output
types are the same, which is what makes it composable and what makes its metrics
misleading.

---

## The axes

### 1. Scope against cost

**`BundleAdjustmentGlobal`** refines every pose and every point at once. Cost grows
with the whole problem, and on a large model it grows fast.

**`BundleAdjustmentLocal`** refines a window and holds the rest fixed. Cost is
bounded by the window, and so is what it can correct.

The choice is not "which is better" — global is strictly more general — but
whether the problem is small enough, or the error local enough, for the cheaper one
to reach it. Drift accumulated over a long sequence is not correctable by a window
that never spans it.

### 2. In-loop local BA is a different thing with the same name

`PoseEssentialToPnP` runs a local bundle adjustment **inside** its registration
loop, over a window of recently registered cameras. That is a parameter of the pose
estimator, not this family, and the two are not substitutes:

- In-loop local BA prevents drift from accumulating **as registration proceeds**,
  so later images are placed against corrected structure.
- `BundleAdjustmentLocal` refines a finished model.

By the time a model exists, the drift has already shaped which images registered at
all. Reaching for the module does not recover what the in-loop version would have
prevented.

### 3. Refining intrinsics changes what downstream must read

A bundle adjuster that refines K writes `intrinsics` into its output, and every
consumer that finds them prefers them — because a pose refined jointly with a K is
not consistent with an older K. Mixing them is a silent error.

---

## Reading the output — the trap that defines this family

**Error is never comparable across differing camera or point counts.**

A bundle adjustment that improves `mean_reprojection_error` while
`registered_images` or `point_count` falls has usually got *worse*: a smaller model
is an easier model. This is the single most common way to misread this stage, and
it is why `registered_images` is a required metric of the type rather than an
optional extra.

The same trap appears whenever anything upstream changes what a "point" is. Two
models with different point counts cannot be ranked by their error, whatever
produced the difference.

**What is comparable**: the before/after pair on *one* model. That is why a bundle
adjuster's own interesting numbers are its deltas, and why the type's required
metrics describe the artifact rather than the process.

---

## Which end to reach for

**Global**, by default, on any model small enough to afford it. It is the one that
can actually fix the problem.

**Local** when global does not fit — in time or memory — and the error is known to
be local. Read `iterations` and whether it converged: a global solve that hit its
iteration cap has not finished, and its output is a partial refinement being
reported as a result.

**Neither** is a real option. A triangulated model that will be consumed by MVS
does not strictly need refining first, but the poses it carries are what MVS builds
on, so imprecision there propagates into every depth map.

---

## What has NOT been measured

| Question | Needs |
| --- | --- |
| **Where local stops reaching** | Sequence length against uncorrected drift. Nothing here establishes the point at which a window is no longer enough. |
| **Whether refining intrinsics helps or hurts** | Scenes with trustworthy calibration. Refining K on a well-calibrated scene can fit noise; on a poorly calibrated one it is the point. The boundary is untested. |
| **The cost curve** | Runtime against camera and point count, on models spanning orders of magnitude. "Global does not fit" is currently a judgement with no numbers behind it. |
| **What a converged solve is worth** | Whether a model that hit its iteration cap is materially worse downstream, or merely unfinished on paper. |
