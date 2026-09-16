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

**It is also where this stack's one measured source of run-to-run variation
lives, and the mechanism is worth carrying to any optimizer in a loop.** That
solve is multithreaded, and summing the same residuals in a different order
across threads differs in the last bits. On a finished model that is nothing. On
an in-loop solve it is not, because the next registration is made against the
refined structure, so a difference far below any threshold you care about at one
step can decide a consensus set several steps later. Measured: one capture run
twice from bit-identical tracks reproduced exactly with the in-loop solve off and
differed by a fraction of a percent of its points with it on.

That is a reason to know about it, not a reason to turn it off — the drift it
prevents is much larger than the variation it introduces. It matters when you
are **attributing** a small difference to a parameter, and `health/smells.md`
carries that reading.

### 3. Refining intrinsics changes what downstream must read

A bundle adjuster that refines K writes `intrinsics` into its output, and every
consumer that finds them prefers them — because a pose refined jointly with a K is
not consistent with an older K. Mixing them is a silent error.

**On a calibrated capture, do not refine them to lower the error.** Measured over a
batch of studio orbits carrying a shipped calibration: freeing the focal length cut
reprojection error and moved the reconstruction several times further from where
reference geometry says it belongs, and freeing the principal point as well was far
worse again at an unchanged error. An orbit lets focal length trade against depth,
so the optimiser buys the objective by resizing the scene — and no reading inside
the pipeline separates that from an improvement. Treat a refined focal that departs
from the shipped value by more than a fraction of a percent as a warning rather
than a result; `estimated_focal_ratio` and `focal_spread` are where it shows.

---

### 4. Two checks run after every step of this family, unasked

The service runs `SparseVerification` on the refined model, against the matches it
was never fitted on, and returns the verdict on the same result as `verification`.
It is a veto, not a ranking: it rejects a model that contradicts that evidence and
says nothing about which of two accepted models is better. And when the pose stage
behind the model reported escaped points, the service re-solves the chain from that
stage at a wider window and returns `second_solve`, naming the model to continue
from and any cameras the re-solve gave up. Read both before planning the next step.
See [SparseVerification](../../modules/sparse_verification/skills/SKILL.md) and
[PoseEssentialToPnP's limitations](../../modules/pose_incremental/skills/limitations.md#escaped-points-start-a-second-solve).

## Reading the output — the trap that defines this family

**Error is never comparable across differing camera or point counts** — and, until
recently, was not comparable at *equal* counts either.

A bundle adjustment that improves `mean_reprojection_error` while
`registered_images` or `point_count` falls has usually got *worse*: a smaller model
is an easier model. This is the single most common way to misread this stage, and
it is why `registered_images` is a required metric of the type rather than an
optional extra.

The same trap appears whenever anything upstream changes what a "point" is. Two
models with different point counts cannot be ranked by their error, whatever
produced the difference.

**The harder version, now fixed at the source but worth knowing you can check.**
Producers of `sparse_model/v1` were computing `mean_reprojection_error` over
different populations under one documented meaning — some over points, one over
observations, which weights long tracks and so inflates the figure, and one over a
frame it did not publish. The gap ran to 3.5x and it *inverted the head-to-head
comparison* the family files invite. All producers now publish the per-point mean.
The cross-check that catches a recurrence costs nothing and is worth running when a
comparison surprises you: **a bundle adjuster's `reprojection_error_before` should
equal the producing module's `mean_reprojection_error` on the same artifact.** Two
independent implementations of one quantity; if they disagree, one of them has a
convention bug. That check was already written in `ba_global`'s tuning notes and
had simply never been run.

**It has now been run, on both adjusters, over every capture in the reference
corpus — and it holds for one of them and cannot hold for the other.** The
global adjuster's `reprojection_error_before` reproduced the triangulator's
`mean_reprojection_error` **to four decimal places on every capture**, which is
the check working. The local adjuster's was **higher on every capture**, by a
tenth to nearly a half.

That is not a convention bug and the check should not be read as failing. The
local module's `min_track_length` deletes points *before* the entry error is
measured, so its "before" describes the cloud it kept and the triangulator's
describes the cloud it was handed. **The direction is the tell, and it is the
same mechanism as everything else on this page**: the points removed are the
two-view ones, whose residuals are near zero by construction, so removing them
can only push the mean up.

So the check applies to an adjuster that deleted nothing. Where a module's
`min_track_length` bites, a "before" above the producer's mean is evidence that
it bit — and the size of the gap is a free reading on how much of the cloud
went.

**What is comparable**: the before/after pair on *one* model. That is why a bundle
adjuster's own interesting numbers are its deltas, and why the type's required
metrics describe the artifact rather than the process.

**What the deltas cannot tell you, and what now can.** A bundle adjuster's output
is normally the LAST `sparse_model/v1` in a pipeline — the artifact a dense stage
actually builds on — so it is the only place some questions can still be asked.
Both adjusters therefore publish the same artifact readings every producer of the
type does, measured on the model they SHIP rather than the one they were handed:

- **`p05_triangulation_angle`** — the weak end of the parallax distribution. A
  point on near-parallel rays sits at an ill-determined depth while reprojecting
  beautifully into the very views that made it, so no reprojection metric can see
  it and neither can a median. Refinement moves structure, so the input model's
  reading is stale the moment the solve finishes; read it on the output.
- **`two_view_fraction`** — on a two-view-dominated cloud a large share of the
  mean is residuals that are near zero *by construction*, because a two-view point
  has four residuals against three unknowns and is exactly determined. The
  headline then reads better than the model is.
- **`min_frame_points`** — a camera can be registered and carry almost no
  structure. `registered_images` counts it the same as any other.
- **`p95_reprojection_error`** — separates a uniformly mediocre model from a good
  one with a few bad points. Those want opposite responses and the mean cannot
  tell them apart.

The two-view reading is also the one that decides between the adjusters, because
`min_track_length` deletes rather than holds out: the local module defaults to 3
and the global one to 2, so on a two-view-heavy cloud the local module ships half
the points. Both now announce that with `points_dropped_by_min_track_length`
rather than leaving it to be noticed.

**"Half" was measured on one capture and is optimistic.** Across every capture in
the reference corpus, run through both adjusters from one shared triangulation,
the local module shipped between a quarter and a half of the global module's
points — so the typical loss is nearer two-thirds than one-half, and the worst
case is three-quarters. The loss tracks the input's `two_view_fraction`, which is
the mechanism and which you can read before choosing.

**When a dense stage is downstream, that deletion is not a hygiene choice.** The
points `min_track_length` removes are the two-view ones, and those cover the parts
of a subject only two cameras see well — which is where a verified densifier leaves
its holes. Measured on a dense batch: at equal registration and equal error, the
models that kept their weak structure produced the more complete dense clouds, and
nothing downstream recovers what was deleted here. Decide it against the
deliverable — [plan/dense.md](dense.md#planning-the-sparse-stage-for-a-dense-deliverable).

**And it drives the composition rung to a perfect score.** Every point below
three views is gone, so the share of over-determined points is 1.000 by
construction — on a model that is a strict subset of the one it is being compared
against, and which scored *worse* against ground truth on twelve of those
thirteen captures. If you rank two adjusters on composition or on median
triangulation angle, this is the ranking you will get and it is backwards. Read
yield beside them; see [`health/ladder.md`](../health/ladder.md).

**Where the input cloud has no over-determined point at all, the local module
does not run.** It raises rather than shipping an empty model, which is the right
behaviour and worth anticipating: a health profile whose composition rung reads
exactly zero predicts this refusal, and it predicted it exactly on the three
captures in the corpus that read zero.

---

## Which end to reach for

**Global**, by default, on any model small enough to afford it. It is the one that
can actually fix the problem.

**Local** when global does not fit — in time or memory — and the error is known to
be local.

**On `converged`, and this paragraph used to say something stronger and wrong.** It
claimed a solve at its iteration cap "has not finished, and its output is a partial
refinement being reported as a result." Measured across a seventeen-capture sweep,
that is false often enough to be dangerous: capped and converged solves of the same
problem agreed on `reprojection_error_after` **to four decimal places**, every time
it was checked. Three separate readers spent a run each confirming it. On one
capture the only configurations that *did* converge were measurably worse models,
so a reader who trusted the old sentence would have shipped the worse one to clear
a flag.

What actually drives the flag is usually the robust loss: a Cauchy loss can keep
the trust-region step from meeting Ceres' tolerance on a model already sitting at
its optimum. So read `converged` as bookkeeping unless `reprojection_error_after`
is *also* bad. If you want to clear it, the cheap test is a raised cap — if the
error is identical to four decimals, the solve was finished and only the flag was
not. Note also that `iterations` reports cap+1 on a capped run, so it never equals
the cap and "did it stop at the cap" is not a test that passes.

**Neither** is a real option. A triangulated model that will be consumed by MVS
does not strictly need refining first, but the poses it carries are what MVS builds
on, so imprecision there propagates into every depth map.

---

## Two things the output does that nothing else tells you

**Bundle adjustment moves the gauge, and it is not a small move.** The solve fixes
seven degrees of freedom somewhere, and where it lands is not the input's frame:
measured, one capture's whole model came back scaled by 0.81 and another by 1.45,
in opposite directions, with the shape unchanged. Two consequences. Any threshold
expressed as a multiple of the reconstruction's arbitrary scale unit — most
obviously a triangulator's `max_landmark_distance`, documented as a multiple of the
seed baseline — is in a *different unit* after a bundle adjustment, so a bound
chosen before one does not mean the same thing after. And a near-uniform
displacement of every point is a rigid motion rather than per-point correction, so
`error_reduction` alone cannot tell "the structure was already right" from "the
structure improved". No metric currently separates them.

**The points array is reordered.** Both the input and output models carry
`track_id`, and the rows are not in the same order. Differencing `xyz` positionally
across a bundle adjustment gives an answer that is wrong by roughly an order of
magnitude and looks plausible — measured at a median motion of 0.119 scene units
positionally against 0.0153 when joined on `track_id` first, and one reader reported
2.06 against 0.02 before catching it. **Join on `track_id` before comparing
anything, including a model against its own refinement.** The instruction to pair on
`track_id` exists in the triangulators' tuning notes but is scoped there to
comparing two different modules, which is why this case kept catching people.

## What has NOT been measured

| Question | Needs |
| --- | --- |
| **Where local stops reaching** | Sequence length against uncorrected drift. Nothing here establishes the point at which a window is no longer enough. |
| **Whether refining intrinsics helps or hurts** | Still open on the boundary, but one side is now measured: on a well-calibrated rig, refinement improved reprojection error by up to 21% *by giving a single physical lens a different focal length per frame*. That is the fitting-noise case, and it is now detectable rather than inferred — `estimated_focal_ratio` and `focal_spread` on `BundleAdjustmentGlobal` publish it, and a diagnostic fires when a one-calibration scene comes back with many. A dense batch has since measured the consequence rather than the symptom, and it is worse than fitting noise: on calibrated orbits, refinement lowered reprojection error while moving the reconstruction several times further from reference geometry. What is untested is still the other side: a genuinely bad calibration, where refinement should be the point. |
| **The cost curve** | Runtime against camera and point count, on models spanning orders of magnitude. "Global does not fit" is currently a judgement with no numbers behind it. |
| ~~**What a converged solve is worth**~~ | **ANSWERED, and see "Which end to reach for" above.** On these captures it is worth the flag and nothing else: capped and converged solves of one problem agreed to four decimals every time. What remains open is whether that holds on a model large enough for the cap to bind for real reasons. |
