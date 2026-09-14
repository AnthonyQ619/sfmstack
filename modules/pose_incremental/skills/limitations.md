---
module: PoseEssentialToPnP
module_version: 1.4.0
curated_at: 2026-09-13
---

# When to stop tuning PoseEssentialToPnP and switch

## Uncalibrated scenes

*Symptom:* the module refuses to run at all.

It needs intrinsics and will not guess them. This is not tunable — an essential
matrix is only an essential matrix with respect to a known K.

*Switch to:* a pose estimator that estimates intrinsics jointly.

```
sfm_find_alternatives(produces="poses/v1", excluding="PoseEssentialToPnP")
```

VGGT and MapAnything are the candidates, and they do not merely tolerate an
uncalibrated scene — they do **better** without a supplied K, because they solve
for it jointly with everything else. Do not pass `calibration_path` to SceneLoader
on that path.

## Degenerate captures

*Symptom:* `no_viable_initial_pair`, or a seed that only just clears
`init_min_angle_deg` and a model with low `median_triangulation_angle` throughout.

*Why no parameter helps:* a planar scene or a pure-rotation capture has no
parallax to recover depth from. The essential matrix is degenerate, and lowering
`init_min_angle_deg` does not create baseline — it seeds on a pair that cannot
support structure, and that error propagates into every later registration.

**Check the matcher's `planarity` metric first.** Above ~0.9 a homography explains
the pairs as well as epipolar geometry does, which is a capture problem. No module
here fixes it. If the target genuinely is planar, this is a homography-estimation
problem, not an SfM one.

## Sparse sampling

*Symptom:* healthy per-pair matching, but `registered_fraction` well below 1.0 and
tracks that never reach a third view.

Measured in this repo: uniformly sampling 6 of DTU scan1's 49 images (every eighth
frame) leaves gaps SIFT cannot bridge even with exhaustive matching — 3 view-graph
components and zero tracks reaching a third view, so nothing can register. Six
*contiguous* frames connect completely.

*What helps:* **more images — load all of them.** This failure is a consequence
of subsampling, not a property of the capture: the same 49-frame capture connects
completely when it is loaded whole. `sampling: head` was previously named here as
the fix, and it is only the fix for an artificially capped set, where it buys a
contiguous baseline instead of a sparse one. If you find yourself choosing a
sampling mode to make a reconstruction connect, the actual answer is that the cap
should not be there. Not a parameter here.

## Drift on long sequences

*Symptom:* reprojection error grows with distance from the seed pair; the model
curves.

*Why no parameter helps:* this module is greedy. It registers one image at a time
against fixed structure and never moves a point once accepted, so small errors
compound. That is inherent to incremental SfM without refinement.

*What helps, and it is already on:* **interleaved local bundle adjustment during
registration is implemented in this module and enabled by default** — `local_ba`
plus six parameters that shape it. It refines a sliding window of recent cameras
and their structure as registration proceeds, which is the principled answer to
compounding drift. Follow it with `BundleAdjustmentGlobal`, which this module does
not do and is not a substitute for.

**Correction, because this section said the opposite.** An earlier version
described in-loop local BA as an unimplemented known gap, on the grounds that the
predecessor achieved it by taking a `BundleAdjustmentOptimizerLocal` *instance* as
a constructor argument and this architecture would not reproduce that coupling.
The coupling was indeed not reproduced — the solve is internal rather than another
module's object — but the capability was, and the text was never updated. A reader
arriving here from either local-BA diagnostic was told the feature they were
already running did not exist.

*The residual limit:* local BA bounds drift within its window and cannot bound it
across a sequence much longer than the window. On a set at or below the window
size there is no drift to bound at all, and the parameter guidance changes shape
accordingly — see `tuning.md` and the `local_ba_window` note in the manifest.

## Escaped points start a second solve

*Symptom:* `points_escaped`, with `escaped_points` above zero — and, on the
bundle adjustment that follows, a `second_solve` block naming the model to keep.

**Why one solve is not enough here.** The in-loop window holds only the most
recently registered cameras. A point whose depth those cameras barely constrain
can leave the image during a solve, and the next image is registered against
structure fitted beside it. Admitting the cameras that see the point — a wider
window — is what constrains it. Nothing on the first model says how much that
mattered: its reprojection error can read better than the wider solve's, because
it kept an easier set of points. So the pipeline solves again rather than asking
the first model's numbers.

**What the service does**, once a bundle adjustment has refined a model built on
these poses:

1. Re-solves the chain from this stage to that refined model with
   `local_ba_window` at 28, or the image count if smaller. Every other setting,
   and every step in between, is repeated as it was.
2. Keeps that solve unless it failed, the verifier vetoed it, or it registers
   fewer cameras than a first solve the verifier accepted and its
   `registered_fraction` falls below the band this stage publishes.
3. Only if it was not kept, tries 40 — or the image count, if smaller — as a
   last resort, under the same rule.
4. Otherwise keeps the first model, unless it was vetoed too; then nothing is
   kept, and the result says so.

Any camera a re-solve gave up is named in its `registration`, kept or not, with
what the loss cost in its `trade_off`.

If the first solve already ran at 28 or wider, it stands in for step 1, and the
last resort runs only if it was vetoed. If the window already spans the capture
there is nothing wider, and the escapes are only reported.

**Why each part is there.**

- *It triggers on escaped points and nothing else.* Where nothing escaped,
  re-solving wider changed nothing on most captures and still cost the runtime.
- *The wider solve is kept by default, not chosen on its numbers.* On the
  captures where points escaped it was the better model far more often than the
  worse one. Keeping whichever solve reported the lower reprojection error
  instead gave back most of that benefit, because an easier model reports less
  error.
- *The width is fixed, not searched.* The benefit rose with width and levelled
  off. Widening until nothing escapes chose worse models than a fixed width: the
  count does not fall as the window grows, since a wider solve holds more points
  that can wander.
- *The veto is the safeguard.* Small steps up from the default width were worth
  little on average, and they were where a capture whose correspondences support
  more than one stable model landed in a wrong one — many degrees off, with every
  self-reported reading accepting it. The verifier vetoed each of those, and the
  width the pipeline uses did not produce one. Without the veto, a wrong second
  solve would silently replace a right first one.
- *40 is a last resort for cost, not for risk.* It beat 28 on a few
  configurations and lost on none, and it costs more. A window spanning the whole
  capture was no worse at the capture sizes measured, but rarely better, and
  larger captures have not been measured.
- *Registration counts, but only against an accepted first solve.* A wider solve
  can leave a camera out that the first placed. Refusing any loss threw away
  corrections worth far more than the few cameras given up; ignoring losses would
  let a solve drop cameras unseen. So a loss is tolerated while the registered
  fraction stays inside the band this stage already publishes: no new number,
  and it scales with the capture — a large capture may give up a few cameras, a
  small one perhaps none. Against a vetoed first solve no loss disqualifies,
  because a vetoed model is no alternative.
- *The band is a bound on cost, not a measured turning point.* Every loss
  observed was a small share of the capture, and the solve that gave it up was
  the better model. Nothing near the band's edge was tested, so where the
  correction stops outweighing the cameras is the reader's call, made on the
  `trade_off` below.
- *Refused cameras are retried before any of this.* An image PnP refused during
  growth is tried again against the finished structure. In the experiments
  behind this rule, that removed every loss against an accepted first solve; the
  one loss left was against a vetoed first solve, which is no alternative. Most
  cameras still missing after the retry never had enough links to be tried.

**Cost.** The chain from this stage to the refined model, run again at a wider
window: typically under twice the time of the first run of that chain, more on
long captures.

**What to do with the result.** Continue from the model `second_solve` names as
`kept`. `sfm_run_summary` lists both models, marks which was kept, and repeats
each one's verification. Do not re-solve by hand when the service is driving.

**When the kept solve gave up cameras**, read its `trade_off` before moving on.
None of it needs reference geometry:

- `rotation_change_deg` — how far the relative rotations between the cameras
  both solves registered moved. Large, with the veto passed: the second solve
  corrected something, and it is the one to keep. Near zero: the wider window
  bought little, so the first solve's extra cameras may be worth more; choosing
  the first is legitimate when those cameras matter.
- `lost_structure_still_covered` beside `typical_for_registered` — per lost
  camera, the share of what it sees that at least two other cameras still see.
  Near the typical share, it was a redundant viewpoint. Well below it, a region
  lost support; if that region matters, link those cameras better upstream
  rather than giving up the correction.
- `verdicts` — a vetoed first solve is not an alternative, whatever the other
  two readings say.

## When a global method is simply better

*Symptom:* the images are an unordered collection rather than a sequence, and
registration order is doing real work.

Incremental SfM is order-dependent by construction. On unordered collections a
global method that solves all poses at once is both faster and more robust.

*Switch to:* a mapper that goes straight from correspondences to a reconstruction,
skipping the separate pose stage:

```
sfm_find_alternatives(produces="sparse_model/v1", not_consuming="poses/v1")
```

## This module's output is not bit-reproducible with `local_ba` on

*Symptom:* two runs of what is genuinely the same recipe return poses that are
not identical, and a model built on them differs by a fraction of a percent in
point count. On a capture whose solve is comfortable you will never see it; on a
marginal one you will.

*Why:* the in-loop local bundle adjustment is a Ceres solve and it is
multithreaded. Summing the same residuals in a different order across threads
gives a different answer in the last bits, and incremental SfM feeds that
straight back into the next registration — so a difference far below any
threshold you care about at one step becomes a different consensus set a few
steps later.

**It is not the RANSAC, which is the natural first guess and is wrong.** Probed
directly, and inside this module's own image, `findEssentialMat(USAC_MAGSAC)` and
`solvePnPRansac(SQPNP)` both return identical results across repeated unseeded
calls on a heavily outlier-contaminated problem, and both ignore
`cv2.setRNGSeed`. A seed parameter was written for this module against that
hypothesis and withdrawn when the probe falsified it; do not reintroduce one
expecting it to help.

**How it was isolated**, because the method matters more than the result here:
the same capture was run end to end in two separate artifact stores with
identical parameters, so both executed for real rather than one being served from
cache. `scene`, `features`, `matches` and `tracks` came back with bit-identical
payloads. `poses` did not. Re-running just this module from that identical
tracks payload with `local_ba: false` produced bit-identical poses in both
stores; with it on, they differed.

*What helps:*

- **`local_ba: false`** makes this module bit-reproducible, and costs you the
  drift control that the section above says is the reason it is on by default.
  That is a real trade, not a free fix — take it when you are trying to attribute
  a difference between two configurations, not as a standing setting.
- **Accept the variance and measure it.** Run the configuration you care about
  twice, in separate stores, and treat the spread as the floor: a difference
  between two configurations smaller than the difference between two runs of one
  configuration is not a difference. `health/ladder.md` carries this rule.
- **Untested, and the obvious next step:** the Ceres solve here does not set
  `solver_options.num_threads`, so it takes the default and uses what it finds.
  Pinning it to 1 should make the solve deterministic at a speed cost. Nobody has
  measured either side of that yet.

**The reason this went unnoticed for so long is the artifact cache**, and that
part is not specific to this module. An unchanged recipe is served from the store
and never re-executed, so nothing ever runs twice to disagree with itself. Worse,
the check that looks like it would catch this does not: an artifact id is derived
from the recipe — module, version, parameters, input ids — not from the bytes
produced, so two artifacts with the same id are two runs of one recipe and
nothing more. In the isolation above, every stage's id matched on both sides,
including the stages whose payloads differ.
