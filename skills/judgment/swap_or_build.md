---
name: swap_or_build
description: When to stop tuning a module and change it, and when nothing in the registry fits and a new one is warranted. Organised by family.
status: mostly structural — one branch comparison has been run over fourteen captures; those rows are tagged [measured]. Claims are stated as scene properties, never scene names; raw per-capture numbers are in skills/runs/INDEX.md.
---

# Tune, swap, or build

Three responses to a bad number, and they are not interchangeable. Reaching for
the wrong one is the most expensive mistake in the loop, because tuning a module
that cannot do the job burns GPU hours and produces a slightly better wrong
answer.

| | when | cost |
| --- | --- | --- |
| **tune** | the module can do this and is set up badly | minutes, and `sfm_replay` keeps the old branch |
| **swap** | the module is doing its job and its job is the wrong one here | a re-run of this stage and everything downstream |
| **build** | no member of the family has the capability at all | hours, plus a permanent maintenance surface |

**The default is tune, and the discipline is to know when it stops.** A module's
`tuning.md` is indexed by observed metric state and its `limitations.md` opens
with the failure signature that means stop. Read them in that order.

---

## The mechanism, before the judgement

**A limitations escape names a CAPABILITY, never a module.** This is the one
piece of the system that is machinery rather than opinion, and it exists so a
swap survives the registry changing under it:

```
sfm_module_skill(<module>, "limitations")
  → "something producing tracks/v1 that does NOT consume pairwise_matches/v1"
sfm_find_alternatives(produces="tracks/v1", not_consuming="pairwise_matches/v1")
  → the live answer
```

`not_consuming` is the important argument. *"Produces `tracks/v1` but does not
consume `pairwise_matches/v1`"* is how a file says **use a direct tracker,
because the matcher is the problem** without naming a module that may be gone.

Module names go stale. Capability queries do not.

---

## Signals that mean SWAP, by family

Ordered by how confident the claim is. **`[structural]`** follows from where a
family's numbers come from and holds regardless of dataset. **`[measured: N]`**
was tested by running both branches to a sparse model over N scenes and comparing
— the strongest tag here, and until 2026-08-18 nothing carried it.
**`[observed: N]`** is weaker: a *reading* on N scenes supported the claim, with
no swap performed. **`[unmeasured]`** is argument only.

### Detection

- **`texture_density` an order of magnitude below the rest of the corpus, and
  `empty_regions` says the empty part is WANTED** → swap the whole stage out for
  a detector-free matcher. Not a detector swap: `detection.md` says *"Neither,
  when the detector fires on nothing."* **`[observed: 1]`** — one capture in the
  corpus reads an order of magnitude below every other, and it is a built interior
  whose blank painted walls ARE the reconstruction target. Untested downstream.
- **`spatial_coverage` low while `keypoints_per_image` is at its cap** → the
  detector is firing, all in one place. Tune first (`keypoints_per_image` is a
  cap, not a result); swap only if raising it does not spread them.
  **`[structural]`**
- **`keypoints_min` far below the mean** → one frame is starving and will fail to
  register. Drop the frame before swapping the detector. **`[structural]`**
- **Choosing a learned detector to pair with a learned matcher is not a
  detector decision.** The descriptor type decides the matcher, so this swap is
  made at the matching stage and applied backwards. **`[structural]`**
- **High adjacent-frame motion** (`overall_magnitude`, `high_motion_tail` at the
  top of what you have seen) → **swap the detector AND matcher for learned ones,
  regardless of what the texture reading says.** This is the strongest measured
  claim in this file. **`[measured: 14]`** — across fourteen captures taken to a
  sparse model, the highest-motion captures are exactly the ones whose view graph
  fragments under a classical detector and ratio-test matcher, dropping between a
  quarter and three quarters of their frames, with a clean gap separating them
  from the captures that complete. A learned branch restored full or near-full
  registration on every one of them, while finding FEWER keypoints — it recovers
  marginal pairs rather than enriching good ones.
  The mechanism: this measures adjacent-frame overlap, and a capture that covers
  ground quickly between adjacent frames shares less between non-adjacent ones,
  which is what an exhaustive view graph is built from. **A fast capture is a
  sparse graph.** Texture readings do not see this — the fragmenting captures
  include some of the most densely textured in the corpus.

### Matching

- **Repeated OBJECTS between images, on a capture whose graph is not at risk** →
  swap the MATCHER to one that reasons jointly over all correspondences, and
  **keep the detector**. A better or more invariant descriptor makes this worse,
  because two castings of one mould are identical at every scale and invariance is
  precisely what makes them match. **`[measured: 14]`** — holding a classical
  detector's keypoints fixed and moving a ratio-test matcher to a jointly-reasoning
  one gained sparse points on every well-connected capture whose subject repeats,
  by a few percent up to a third. `FeatureMatchLightGlue` takes a `sift` weight
  set and `auto` reads the producing module off the features artifact, so this
  costs **no re-detection** — the same `features/v1` feeds both.
  **Ask this question second, after connectivity.** On a fast capture the graph
  fails before ambiguity matters, and this swap will not save it.
- **The same swap on a NON-repeating, well-connected capture is expensive and
  should not be made.** Same experiment, same fixed keypoints: the joint matcher
  discarded a third to a half of the model on every capture whose subject does not
  repeat. **`[measured: 14]`** The ratio test is doing real work when nothing is
  confusing it, and replacing it costs real points. `repetitiveness` is the
  closest thing to a signal for which side you are on, and it is a weak one —
  see `scene_to_pipeline.md` §2, which explains why it is measuring a different
  axis than the hazard.
- **Repeated PATTERN between images** → try scale and context first: a larger
  descriptor support, a higher working resolution. Swap only if that fails.
  Different escape from the row above, which is why the note has two halves.
  **`[structural]`**
- **`inlier_ratio` healthy and the model is wrong** → the matcher is not the
  problem. Look at `material_hazards`: a coherent reflection is a RANSAC inlier.
  **Do not swap the matcher for this.** **`[observed: 3]`**
- **`planarity` near 1** → *nothing in this family fixes it.* The matches may be
  perfect. This is a signal to change the POSE stage, and `SceneMotion` has
  already separated the two causes for you. **`[structural]`**

### Tracking

- **The tracker cannot be chosen before the matcher runs.** Detector-based
  matching writes `feature_index` and chaining is exact; detector-free does not
  and the tracker must merge by proximity. A plan that fixes the tracker up front
  is over-committed. **`[structural]`**
- **`inconsistent_rate` and `split_rate` moving in opposite directions as
  `merge_eps_px` changes** → this is tuning, not swapping. They are the
  over-merge and under-merge signals and neither is meaningful alone.
  **`[structural]`**
- **Both bad at every tolerance** → the endpoints are not separable at this
  resolution. Swap the matcher, not the tracker. **`[unmeasured]`**

### Pose

- **`pure_rotation_risk` high** → no parameter helps and no swap helps. There is
  no parallax, so there is no structure to recover at any quality of matching.
  Drop the frames or say the capture cannot be reconstructed. **This is the one
  place where the honest answer is to stop.** **`[structural]`**
- **`planar_dominance` high with `pure_rotation_risk` at zero** → the structure
  exists and the two-view essential-matrix decomposition is ill-conditioned.
  Swap to a solver that does not bootstrap from two views — `SparseGlobalCOLMAP`
  solves the graph globally, `PoseVGGT` never decomposes an E. Or stay
  incremental and raise `init_min_angle_deg`. **`[structural]`**

  **This one was run, and the run could not settle it — which is itself the
  finding.** On captures reading up to a fifth of pairs preferring a homography,
  the incremental route registered every frame and returned consistently MORE
  points than the global solver on the same matches. That looks like evidence
  against the swap and is not, because **the failure this swap prevents is a
  confident wrong model, not a missing one.** A mis-decomposed essential matrix
  yields a full, plausible, well-reprojecting point cloud. Point count, registered
  count and reprojection error would all look healthy on precisely the outcome the
  prescription exists to avoid.

  **So: do not read "more points" as "better" on a degeneracy question, and do not
  cite that run as support for staying incremental.** Settling this needs ground
  truth or a geometric check against a known plane — neither of which this stack
  has yet. Until then the swap stays a structural argument, and the honest cost
  statement is: the global solver returned roughly a third fewer points and lost
  nothing measurable, on captures where the incremental route did not visibly
  fail.

  *(Measured again since: the gap is the two modules' different
  `min_track_len` defaults. At a matched floor the global solver returns MORE
  points, not fewer. Compare at matched settings.)*

  **The general lesson, worth more than the specific one:** *a branch comparison
  can only settle a question whose failure mode is visible in the metrics you
  collect.* Connectivity failures are visible — a frame either registered or it
  did not. Degeneracy failures are not. Check which kind you have before spending
  GPU hours on an A/B that cannot answer it.
- **The seed cannot be found at all** (`init_min_angle_deg` rejecting
  everything) → rotation, not planarity. Different fix, same metric. **`[structural]`**

### Sparse and optimization

- **Reprojection error is not comparable across differing model sizes.** A model
  with fewer points can report a better error and be worse. Judge a swap here on
  point count and `median_triangulation_angle` together, never on error alone.
  **`[structural]`**
- **Small baseline against a shallow subject** → everything will look excellent.
  `inlier_ratio` and reprojection error both stay healthy while triangulation
  angles are poor. Judge on `median_triangulation_angle`. **`[observed: 1]`** — a
  carved panel photographed head-on from a tight arc, the lowest motion reading in
  the corpus by a wide margin.

---

## When to BUILD

Much rarer than it feels in the moment, and the bar is deliberately high: a new
module is a permanent surface that has to keep working through every future
change to `sfmkit`.

**The signal is a capability query that comes back empty.** Not "nothing worked"
— *nothing in the registry has the shape the problem needs*:

```
sfm_find_alternatives(produces="tracks/v1", not_consuming="pairwise_matches/v1")
  → []
```

That is evidence. "I tried three modules and they were all bad" is not — it
usually means the problem is upstream of the stage being blamed.

**Before scaffolding, rule out the three cheaper answers:**

1. **Is the input wrong?** More failures trace to `SceneLoader` parameters than to
   any module. On the most texture-starved capture in the corpus the first move
   is a larger `target_resolution`, not a
   detector.
2. **Is the stage wrong?** `planarity` is a matching metric whose fix is in pose.
   A family can be doing its job perfectly while the number it reports is bad.
3. **Does an existing module have an unused parameter for this?** Check
   `sfm_describe_module` before assuming; the per-parameter `tuning` notes are
   there precisely so a capability is not rebuilt.

**Then:** `sfm_scaffold_module` → implement the adapter → `sfm_build_module` →
`sfm_smoke_test`. The scaffold validates declared payload types up front, so a
module that cannot be wired into anything fails before it is written.

**A new module must declare every metric its output type requires**, with the
direction fixed by the type. That is checked at registry load, not at run time —
a manifest that omits one fails before any container starts.

---

## What is NOT in this file

**Thresholds.** What counts as "narrow baseline" or "repetitive texture" lives in
[scene_to_pipeline.md](../scene_to_pipeline.md) with the measured ranges behind
it. This file assumes you have already read a number as high or low and asks what
to do about it.

**Stopping.** When a result is good enough is [stopping.md](stopping.md), which is
not written yet.

**Which families to trust.** [priors.md](priors.md), also not written.

---

## Honesty about the evidence

**Almost nothing here has been measured end to end.** The observed counts refer
to scenes where a *reading* supported the claim, not to swaps that were performed
and compared, **with one exception, now recorded.** Six scenes have been run
through three detector+matcher branches to a sparse model with everything
downstream held identical — see `scene_to_pipeline.md` §4a. What it settled:

- **A learned detector is not a way to get more points.** SuperPoint's keypoint
  cap binds at 2048 where SIFT returns 4000–7000 on the same frames, and
  SuperPoint+LightGlue produced the smallest model on all six scenes.
- **On a repetitive scene, swap the MATCHER and keep the detector.** Holding SIFT
  fixed and moving a ratio-test matcher to a joint one recovered up to a third more
  points on well-connected captures whose subject repeats. That is the "repeated
  OBJECTS" row under **Matching** above.
- **The trap in the row below is real.** SIFT+NN reported *better* reprojection
  error than a learned branch while building a model with worse triangulation
  angles. Judged on error alone the wrong branch wins.

One caution that is itself a finding: the first run of that experiment passed no
parameters and so measured the matchers at their `pairing: sequential` default
rather than the `exhaustive` every plan specified. It produced a clean, plausible
and entirely wrong result — half-registered models and a texture band that does
not exist. **A swap comparison is only evidence if both branches run the
configuration the plan actually names.**

The claims marked `[structural]` do not need that evidence — they follow from
where each family's numbers come from. The ones marked `[observed]` and
`[unmeasured]` do, and until it exists they are arguments dressed as guidance.

Add to this file the same way as to `scene_to_pipeline.md`: the scene, the
number, how it was checked, and what it changed. A swap that was tried and did
NOT help is worth more here than one that did, and is the entry most likely to be
left out.
