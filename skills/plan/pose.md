# Pose estimation — choosing an estimator

Everything that produces `poses/v1` — and one option that produces poses without
being in this family at all.

---

## The axes

### 1. Geometric or feed-forward

**`PoseEssentialToPnP`** needs correspondences and calibration. It picks a seed
pair, decomposes an essential matrix, and then registers images one at a time by
PnP against the structure built so far.

**`PoseVGGT`** needs neither. It attends across the whole image set and reads
camera parameters off the aggregated tokens.

What follows from that, and it is most of the decision:

| | geometric | feed-forward |
| --- | --- | --- |
| needs correspondences | yes | no |
| needs calibration | yes | **no — it estimates intrinsics** |
| can fail on one image | yes — registration stalls | no; it poses every image or none |
| per-image evidence | inlier counts, the seed pair, a threshold to relax | none |
| `mean_reprojection_error` | measured | **null by construction** |

The last row is the one that bites. A feed-forward estimator has no
correspondences, so it cannot report the error that would tell you whether it
worked. Nothing in its own artifact answers "is this right"; the first number that
does is the triangulator's `yield`, downstream.

### 2. Registration order, and drift

Incremental registration accumulates. Each image is placed against structure built
from the ones before it, so errors compound along the chain, and the compounding is
worse with learned features whose positions are less precise. **In-loop local
bundle adjustment** — a window refined as registration proceeds — exists for
exactly this, and it is a parameter of the geometric estimator rather than a
separate module. When points escape that window during a solve, the service
solves the chain again at a wider window once the model is refined, and names the
model to continue from — see
[PoseEssentialToPnP's limitations](../../modules/pose_incremental/skills/limitations.md#escaped-points-start-a-second-solve).
Do not plan a window sweep of your own for it.

Feed-forward has no order and therefore no drift. It has a different problem:
whatever the model gets wrong, it gets wrong everywhere at once, and there is no
per-image signal to localise it.

### 3. Estimating intrinsics changes what downstream reads

A module that estimated intrinsics writes them beside its poses, and every
consumer that finds them **prefers them over the scene's calibration** — because a
pose computed with its own K is not consistent with anyone else's.

On an uncalibrated scene that is the whole point. On a calibrated one it is a claim
to check: `estimated_focal_ratio` against 1.0 is the single most useful warning a
feed-forward estimator produces, and far from 1.0 means the two disagree and the
poses were computed with the estimate.

### 4. The third option: no pose module at all

`SparseGlobalCOLMAP` consumes `pairwise_matches/v1` and estimates poses *internally*
as part of reconstructing. Rotation averaging over the whole view graph, then global
positioning — no registration order, so nothing to stall.

That is the answer when the problem is **order** rather than correspondence quality:
an unordered collection where incremental registration cannot find a next image it
can place. It is not in this family because it produces `sparse_model/v1`; see
[sparse.md](sparse.md).

**It does register cameras the incremental route leaves behind, and the comparison
has been run carefully.** Against the *best* incremental model built on the **same
correspondences** — so the matcher is held fixed and the reconstructor is the only
thing that changes — it added cameras on every corpus capture that had any to add,
and **lost none on any of them**. The gain is a few frames each, not a
transformation, and on a capture already registered whole there is nothing to add. This is the indication in the paragraph above, and it is the same
effect the `reconstructor-decided` class in
[`evidence/INDEX.md`](../evidence/INDEX.md) records.

The campaign is in
[`evidence/global-arm-2026-10.md`](../evidence/global-arm-2026-10.md), which also
records that this set sits entirely above the 0.7 crossing below, and says nothing
about the regime beneath it.

**The consensus reading does not select it.** Reaching for this module because the two
estimators put your model outside their mutual agreement was tried and measured: the
association between that reading and which arm produced the better model was
indistinguishable from zero, and the two captures it did help sat at the extreme ends
of the reading. Small sample, but it errs the safe way — do not route the consensus
reading to this decision. It is a branch-choice reading and is documented as one
above.

What it does change is the model's global **shape**, and that shows up in a
reference-scored dense deliverable rather than in any reading the pipeline reports.
See [dense.md](dense.md).

---

## Which end to reach for

**Geometric**, by default, on a calibrated scene whose matcher produced one
connected view graph. It is the only option here that reports whether it worked.

**When there is no matcher, which is a legal chain.** A predictive tracker consumes
`features/v1` directly, so a detector → tracker → pose chain has no view graph and
none of `graph_components`, `min_image_degree`, `inlier_ratio` or `planarity`
exists. The default above still applies — read the tracker in the matcher's place:
`min_frame_observations` and `long_tracks_per_frame` for whether every frame is
carried, `trifocal_transfer_px` for whether the correspondences are any good.

**On any chain, the floor that decides whether a frame can be registered at all is
`min_frame_long_tracks`, not `min_frame_observations`.** Resection needs 2D–3D
correspondences, which only a track reaching a third view can supply, so a frame can
carry a great many observations and still fail PnP because almost all of them belong
to two-view tracks. Read the long-track count for the weakest frame before concluding
that a frame which failed to register was poorly matched — the two readings disagree
exactly where it matters.
Connectivity is not at risk on such a chain in the way it is with a view graph,
because nothing was ever cut off. Note that the third option below,
global reconstruction, consumes `pairwise_matches/v1` and is simply **unavailable**
here — not a judgement call, an absence.

**Feed-forward** when the scene is **uncalibrated** — there is no alternative — or
when the geometric estimator reports `registered_fraction` below 1 and the missing
images are ones you need.

That second case has now been measured, and it is the strongest single result in
this file. Seven captures on which the geometric estimator stalled — three of
them at under a seventh of their frames — were re-run with the pose stage
swapped and **nothing else changed**: the same detector, the same matcher, the
same cached tracks the geometric estimator had already failed on. The
feed-forward estimator registered **every frame of all seven**, in seconds.

Two things follow, and the second matters more than the first.

The correspondences were never the constraint. It is tempting to read a stalled
registration as thin matching, and on these captures that reading was wrong on
all seven — the tracks were byte-identical to the ones that failed. **A stalled
incremental registration is evidence about seed-and-grow, not about the data it
grew from.**

And the swap is nearly free to try. It needs no correspondences, so it can run
off the artifacts already on disk, and it costs seconds where the campaign it
rescues costs an afternoon. Where `registered_fraction` is low, run it before
you spend a single run tuning the matcher.

**Where the trade flips is a reading, and it is `registered_fraction`.** The paragraph
below says the damage scales with how much the geometric branch had already done; the
crossing is at about **0.7**. At or below it, the estimator's own model was the better
delivery on most of the corpus captures that reached it, and on one of them by a wide
margin. Above it the finding reverses, which is the same result from the other side:
over corpus captures that registered every frame the core won more often than not and
the median favoured it — though two low-texture outdoor captures were large exceptions,
so full registration is not by itself a reason to stop looking. Read
the fraction rather than the absolute camera count: a capture missing three of ten and
one missing thirty of a hundred are the same situation, and the second is not three
times worse. The campaign is in
[`evidence/short-core-2026-10.md`](../evidence/short-core-2026-10.md), which also
reports the wider batch for scale.

**The counter-case is in the corpus and it is not currently detectable.** One
interior walk held seven of ten and its core still beat both estimators — at 0.021
against 0.000, which is a contest between two failures rather than a good delivery
lost. What makes it the exception is not that it was hard: a coherent reflector stood
between the camera and the scene, and four of its nine pairs carried no parallax, so
**the estimators themselves were unusable there**. No estimator-side reading separates
it from the captures the swap helped — `baseline_span` sits inside their range and no
diagnostic fires — and where the swap did cost something it cost at most 0.064 against
gains several times that. So this is a default with a known cost, not a rule with an
escape, and the report should name which model was delivered and why.

**What it does not automatically buy is accuracy, and the trade is sharp.**
Against ground truth, the fully-registered feed-forward model was *worse* per
pair on six of the seven, and the damage scaled with how much the geometric
branch had already been doing: on a capture it had registered around
three-quarters of, at good accuracy, the swap completed the registration and cost
roughly two orders of magnitude of pose error. Part of that gap is the confound
in [`health/ladder.md`](../health/ladder.md) — an error over the frames a stalled
model kept is not comparable to one over the whole capture — but not all of it,
because the gap grows precisely where the stalled model kept the most frames.

**One reading on the stalled model told the two cases apart, before the swap
ran.** The seventh capture — the one where feed-forward was better, by a factor
of fifty — is the one whose stalled model read **wildly outside the corpus on
pose agreement**, two orders of magnitude above the other six, which all sat in
the ordinary band. The mechanism is why it should: pose agreement asks whether
the poses a model *did* produce agree with the two-view evidence they were built
from, so it separates a pose stage that ran out of images from one that was
producing wrong poses and would have kept producing them.

**The rule this supports:** low registration is the reason to consider the swap;
the stalled model's pose agreement is what says whether to expect it to help. In
the corpus band, expect to trade accuracy for coverage and decide which you need.
Far outside it, the geometric solve is broken rather than stalled and the swap is
a straight improvement. One positive case supports this, so carry it as a
mechanism-backed expectation and not as a measured law — and see the reliability
ladder in [`evidence/EVIDENCE.md`](../evidence/EVIDENCE.md) for why a predictive
claim from this corpus is the category to trust least.

---

## Before you deliver a model, ask it whether it agrees with itself

Everything above is about choosing an estimator. This is about the model that came
out, and it is where this stage most often goes wrong in a way nothing else catches.

**You already have this reading, and that is exactly the problem.** The service runs
`SparseVerification` itself after the optimization stage, so a verdict comes back
whether or not you asked for one. Across a campaign driven cold, a number of delivered
models were badly wrong against reference geometry — and **every one of them had a
verifier reading in hand, which called most of them consistent.** On the corpus
captures of that campaign it called every wrong model consistent. The failure here is
not a step that was skipped. It is a verdict that was believed.

**Read the angular residual, not only the pixel one, and this is the part that will
surprise you.** The module's veto is `heldout_residual_px`, banded at the pose
estimator's inlier threshold. A pixel tolerance is not a fixed amount of geometry:
the same pixel figure is a much larger angle on a wide-angle camera than on a long
lens, and across that campaign's five families the median focal length spanned well
over an order of magnitude. Measured against the thirteen known-wrong models, **the
pixel veto caught two of them and the same residual read as an angle
(`heldout_residual_mrad`) caught nearly all**. Every model the veto missed came from
a short-focal camera, where its default slack is many times the angle it is on a
long lens. So:

- On a long-focal capture — a rig orbit, a survey camera — the px veto and the angle
  say the same thing and there is nothing to do.
- **On a wide-angle or short-focal capture the px veto is loose by the ratio of the
  focal lengths, and it is the angular reading that carries the signal.** Read it,
  compare it against what a correct model reads rather than against a published
  ceiling, and note that the module deliberately publishes no band for it.

**And the band you would compare an angle against was fitted on long lenses.** Every
capture whose readings set the healthy end of this reading is a rig orbit or a survey
camera. On one of the campaign's worst models the driving agent did the conversion
itself, wrote down that its residual was around two milliradians and that this sat
*outside a long-lens corpus* — and delivered the model anyway, because nothing told
it which of the two readings to believe. It was wrong by more than a right angle.
**When the px verdict and the angle disagree on a short-focal capture, the angle is
the one carrying information**, and the px verdict's silence is not evidence.

This is the same defect this corpus has already corrected once on a different axis:
a camera-count-dependent statistic was withdrawn for a scale-free one because it put
the same situation on either side of a fixed floor depending on capture size. See
[`evidence/view-graph-support-2026-09.md`](../evidence/view-graph-support-2026-09.md)
for that precedent and
[`evidence/sparse-pose-2026-09.md`](../evidence/sparse-pose-2026-09.md) for this one.

**Three readings, and what each means when it fires.**

| reading | what it says | what to do |
| --- | --- | --- |
| angular residual well above what a correct model of this capture reads | the model disagrees with correspondences it was never fit on | do not deliver without looking again — below |
| `supported_stray_cameras` at two or more | the model's own agreeing evidence leaves cameras disconnected from the body of it | the same, and the disconnected cameras name where to look |
| `nothing_held_out` | the model is too small to check at all | **unverified, not verified.** Say so in the report and do not let it pass as clean |

Read the strays rather than `supported_second_size`, which is the same quantity
seen only through its largest piece: cameras that each fail to reach the model and
fail to reach each other leave pieces of one, which that reading reports as a single
stray and passes. Several cameras unsupported *separately* is a scattered
registration failure, not a stray, and only the total makes it visible.

**The ANGULAR reading is a reason to look again, not a discard — and this scopes to
the angular reading alone.** At any sensitivity that catches the wrong models it
also fires on roughly one good model in five, and two of the most accurate models in
that campaign are among its false alarms: shallow-relief interiors that read high and
are excellent. That is not a flaw to be tuned away, because this reading measures
consistency with evidence and never accuracy, and a shallow subject is exactly where
the two come apart. Weigh it as a constraint that has fired, in the sense
[`health/ladder.md`](../health/ladder.md) uses, and then decide.

**None of that loosens the px veto, which stays absolute.** `contradicted` and
`model_not_supported_by_its_own_evidence` mean what
[`SparseVerification`](../../modules/sparse_verification/skills/SKILL.md) has always
said they mean: do not keep that model. The two readings fail in opposite
directions and must not be confused — the px verdict is nearly silent and almost
never wrong when it does speak — across that campaign the alarms it raised were all
genuine, and on the corpus captures it raised none at all — while the angular reading
speaks often and is wrong about a fifth of the time. **So a firing angle invites a second look; a firing veto ends the
matter.** Measured on the run that followed this section's first draft: four agents
recorded overruling a veto, and one of them delivered a studio orbit **forty times
further from truth** than the model it rejected, on the grounds that the vetoed model
carried more points and better coverage. Those are exactly the rungs a
self-consistent wrong model wins on. If a veto leaves you with no model, that is
information about the capture — say so and deliver the smaller verified model, or
fill it by the section below. It is never grounds to keep the vetoed one.

**A quiet verdict is not a clearance, and the asymmetry is the whole point.** Both
vetoes are *structural*: they ask whether the pairs that agree with the model connect
it, and whether any camera stands outside that agreement. A model can be wrong
everywhere and still answer yes to both, because being uniformly displaced breaks no
component and leaves no stray. Measured over twenty delivered models, **no veto fired
on any of them** — and one of the twenty sat at seventy-four degrees of median
rotation error against reference poses, with `supported_components` 1,
`supported_largest_share` 1.0 and `supported_stray_cameras` 0. Every structural reading
was quiet and the model was the worst in the batch.

**What carried that capture was the magnitude, and it carries no band.**
`heldout_residual_mrad` read **14.1** on it, against a next-highest of 3.6 and a
median under 1.5 across the other nineteen; over the twenty it tracks rotation error
at rho +0.68. It has no healthy band for the reason
[`tuning.md`](../../modules/sparse_verification/skills/tuning.md) gives — the gate is
a parameter, and a fixed band beside it would state a second threshold that disagrees
the moment anyone changes the first. So read it the way the corpus asks every other
residual to be read: **against what a capture of this kind reads**, not against a
number. An order of magnitude above the rest of your own batch is the signal, and no
diagnostic will raise it for you. Before you treat a passing verdict as clearance,
read [what the module says it cannot
see](../../modules/sparse_verification/skills/limitations.md).

### Every reading above is built on the model's own evidence

That is the limit of all three of them, and it is worth saying once, plainly, because
it defines a failure they share rather than one they each happen to miss.

The residual, the strays and the veto are all computed from correspondences. On a
capture with repeated or near-symmetric structure the matcher can be wrong in a way
that is *globally consistent*: the wrong answer satisfies the two-view geometry at
every baseline, so the model agrees with its own evidence everywhere, and every
reading built on that evidence agrees with it. Measured on such a capture — two
different matchers produced models agreeing closely with each other, the held-out
residual was the lowest of its batch, every camera registered, and the delivered
cloud was metres out. **No amount of care with the readings above reaches this.** The
evidence is not being read wrongly; the evidence is wrong.

**So ask something that never saw your correspondences.** Run both
correspondence-free estimators — `PoseVGGT` and `PoseMapAnything`, each of which
consumes the scene and nothing else — and pass your model and both of them to
`sfm_compare` in one call. It returns `pose_agreement`: all three pairwise rotation
disagreements, with nothing privileged.

**Read your disagreement against theirs, never on its own.** This is the whole
technique and it is easy to get wrong by leaving out the second estimator:

| what you see | what it means |
| --- | --- |
| the two estimators sit close to each other, and both sit far from you | the two independent answers agree, and yours is the outlier — **look** |
| the two estimators sit far from each other | they are not agreeing on anything, so their distance from you measures their spread, not your error — no signal, whichever one you happened to compare against |
| the two estimators sit close to each other and close to you | three independent answers agree; this is the quiet case |

One estimator cannot distinguish the first row from the second. Measured across a
multi-family batch, a single estimator condemns captures where the *estimator* is the
outlier — including one of the most accurate reconstructions in the batch — and
misses captures whose disagreement is small in absolute terms but large against how
tightly the two estimators agree. Neither error survives having both. The second
estimator is not a refinement; it is what supplies the scale the reading is in.

**When it fires, the remedy is the whole feed-forward branch, and it is measured
rather than assumed.** Not the poses alone — a model built from feed-forward poses
on top of geometric depth was worse than either on every capture it was tried on, so
a half-swap is not available here. Run the branch through to a cloud, measure both
deliveries the way you would measure any two candidates, and keep the better.

**A disagreement is a reason to measure the alternative. It is never, by itself, a
reason to discard what you have.** The two estimators are independent of your
matcher; they are not independent of each other. They share a training distribution,
and on a scene far outside it — dense vegetation is the measured case — they agree
tightly and are *both* wrong, while the geometric model is the better reconstruction.
The reading is still true there: those poses really do disagree with everything. What
is false is the inference from disagreement to swap. Acting on the reading directly
costs you that capture; acting on the measurement costs you one run.

The campaign is in
[`evidence/consensus-2026-09.md`](../evidence/consensus-2026-09.md).

### When it fires, fill rather than swap — and do not refine the fill

Where the reading fires *and* the geometric branch is holding cameras its own
matcher cannot justify, the remedy measured to work is narrower than the wholesale
swap above.

**Dropping cameras is half a move, and half is worse than none.** This is the
failure the first run of this section produced, so it is stated before the remedy
rather than after it. Rejecting the unsupported cameras makes the model you keep
more accurate — measured, on every capture where it was tried — and it makes the
*delivery* worse, because the frames you dropped are still frames the capture
contains and every pair touching one is now unanswered. On one subsampled room
capture the rejection took median rotation error from about fourteen degrees to
under three and cost roughly half the delivered accuracy-over-all-pairs anyway; on
an interior walk it cost more than that. **So if a verdict or a reading takes
cameras out of your model, finish the move: fill them back by the method below, in
the same session, before you deliver.** A model that stops at the verified core and
stops there is not the conservative choice — it is an unfinished one, and the report
should say which frames are missing and why you could not fill them.

**Keep the geometric core. Use the feed-forward estimator only for the cameras the
core cannot support.** Measured over the worst captures in that campaign, the fill beat the geometric model
as delivered at every threshold, and was level with the feed-forward estimator run
alone — ahead at the tight and the loose end, behind in the middle, and never by a
margin that decides anything. So it is the better delivery
where the core is nearly complete, and where the core is badly short the estimator's
model on its own is ahead — which is what `registered_fraction` at about 0.7 separates
and what the delivery table below says. The alignment is cheap and it *gains* at tight
thresholds, because a mixed pair then has the accurate core on one side of it.

**The chain is `PoseFill` → `SparseTriangulation` → `BundleAdjustmentGlobal`.**
`PoseFill` fits the similarity from the feed-forward frame into the core's on the
cameras both tables place, and returns **one pose table** with the core's rows
untouched and the rest carried across, marked. Triangulation then builds the
structure from the scene's own tracks, in one frame at one scale — so the filled
cameras carry real observations wherever correspondences reach them, rather than
being poses bolted onto someone else's cloud. Merging two finished *models* instead
is the shape to avoid: it means reconciling two point sets and two track tables
built at different scales, and that is where the scale question becomes genuinely
hard. Merging the pose tables is seven parameters with a closed-form answer.

**Dropping is the same move, and `drop_image_indices` is how.** The table below says
to drop the cameras the model cannot support *and* fill them. Pass them to
`PoseFill` and both halves happen at once: they leave the core before the similarity
is fitted, so a camera in the wrong place cannot pull the frame alignment either,
and they are then filled like any other missing camera. Dropping by re-running the
loader on a narrower pattern is not the same thing — that rebuilds the capture from
features onward and throws away the core you were keeping.

**Which camera to drop is a reading, not a guess.** `SparseVerification` publishes
`worst_camera_index` and a per-camera median held-out residual beside its per-pair
array. Read it rather than dropping on suspicion, and note that **the camera to drop
is often not a stray**: it can sit inside the largest agreeing component, contribute
nothing to `supported_stray_cameras`, and still be the one every pair touching it
disagrees with. The two readings answer different questions.

**A camera can be in the wrong place without disagreeing with anything.**
`worst_camera_index` asks which camera its own pairs contradict, and a camera can
contradict nothing and still be misplaced — on a measured capture the camera 45000 times
the median camera-centre offset out of position carried 105 observations and
contradicted nothing at all. A spatial reading of exactly that was published through
`SparseVerification` 1.4.0 and **retired in 1.5.0**: scored on delivered rather than
known-bad models it did not predict the outcome, because the grossly displaced cameras it
caught had already been rejected by the readings above. So the gap is real and currently
unmeasured — do not infer from a quiet verifier that every camera is where it belongs.

**Before dropping on either reading, ask whether dropping can help at all.** On that
same capture, removing the far camera changed the reference alignment by nothing: it
was already an outlier, and fifty-two of ninety cameras were misplaced by a fraction
of a metre each. A model wrong everywhere does not become right when its most
visible symptom is deleted, and `supported_components` above 1 with a large second
piece is what says so. The drop is for the capture whose cameras are right except for
one or two — where it has been measured to recover most of a failed alignment — and
not for a model that is globally adrift.

**Read both gates before you deliver it, because they price different things.**

| reading | what it asks | when it is silent |
| --- | --- | --- |
| `shared_residual` | were the two tables put into a common frame, on the cameras where both have an opinion | it says nothing about the cameras being placed |
| `filled_agreement_deg` | do two independent estimators agree about **the frames being filled** | null unless a second estimator was passed as `poses_b` |

The first is what a **drifting** estimator trips: one similarity has seven parameters
and cannot correct a scale that varies along a capture. Expect it on a long handheld
walk, not on a subsampled orbit.

The second exists because the first can pass while the fill is still wrong. Measured:
a capture whose two estimators agreed across the whole overlap and disagreed by tens
of degrees on exactly the four frames being filled — a clean frame fit, placing
cameras only one estimator had an opinion about. **Pass the second estimator.** It
costs one run you have usually already spent on the consensus reading, and without it
the frames that matter most rest on a single opinion.

When either fires, deliver the core and say which frames are missing; a refused fill
costs the core, a bad fill costs the delivery.

**Then freeze the filled cameras. Do not put them in the global refinement.** This
is the single largest effect in the whole result and it runs against the obvious
expectation. Bundle adjustment over the combined model **helps the geometric core on
every capture and badly damages the fill** — pairs touching a filled camera came out
several times worse refined than left at their feed-forward estimate, with the share
of catastrophic pairs rising by a factor of several. The mechanism is plain once
stated: refinement drags those cameras using exactly the correspondences that were
too thin to register them in the first place. Refine the core, hold the fill fixed,
and say in the report which cameras are which.

Pass the filled indices to `BundleAdjustmentGlobal`'s **`fixed_image_indices`**;
`filled_images` on the model is the count, and the `filled` mask says which. Their
points still move — a filled camera contributes structure like any other, it just
does not move itself.

**And the mark travels with the model, which matters more than it sounds.** A
filled camera rests on no correspondences, so every reading built on
correspondences finds it unsupported — correctly, and misleadingly, because it was
never claimed to be supported. `SparseVerification` builds its components over the
cameras that *claimed* to rest on evidence and reports the rest as
`filled_cameras_excluded`. Without that, four filled cameras read as four strays and
trip the error veto, and a correctly executed fill would be discarded by
construction. If you ever assemble a merged pose table by hand, carry the mask or
the rest of the stack is obliged to reject what you built.

**And do not reach for this every time the reading fires.** One of the two captures
promoted into [CORPUS.txt](../evidence/CORPUS.txt) is there to be the counter-example:
a wide-FOV room capture that the verifier flags on both readings, that was **already
good**, and that the hybrid made distinctly worse. Where the geometric branch is
holding its cameras on evidence it actually has, filling is a downgrade. The trigger
is the reading *together with* cameras the view graph cannot justify — not the
reading alone.

**The two halves of that, side by side, because they are easy to collapse into one
rule and they are opposites:**

| you are holding | do |
| --- | --- |
| every frame, on evidence the matcher verified, and the reading is quiet | deliver it; nothing here applies |
| every frame, but some on evidence the matcher could not verify, and the reading fires | drop those cameras **and fill them**, frozen — both halves, in one call: their indices go in `PoseFill`'s `drop_image_indices`, then triangulate, then refine with the filled indices in `fixed_image_indices` |
| fewer frames than the capture has, because a veto or the graph took them out | **fill them**, frozen, by the same chain. Stopping here is the unfinished move above |
| fewer frames, `PoseFill` refuses or either gate fires, and **`registered_fraction` is above about 0.7** | deliver the core, and say plainly in the report which frames are missing and that the capture was not fully solved. A nearly-complete accurate core is the case the swap damages |
| fewer frames, `PoseFill` refuses or either gate fires, and **`registered_fraction` is at or below about 0.7** | **deliver the estimator's model on its own**, marked as such. The core alone was the wrong delivery on most of the captures this row fired on, and on one of them by a wide margin. If no estimator will run, deliver the core and say the capture was not solved |
| **a core too small to fill at all** — fewer than a handful of cameras shared with the estimator | there is nothing to fit a frame onto, and this is not a swap. **Deliver the estimator's model on its own**, marked as such. Every capture measured at this row delivered the core instead, and the estimator's model was the better delivery on nearly all of them — a core of two to five cameras is not the conservative delivery, it is most of the capture missing. Deliver the core only where the estimators are themselves unusable, and say so. Do **not** lower `min_shared_cameras` to get a fill through: a residual computed on four cameras is a fit to four points, and an agent that tried it had the fill caught by the other gate anyway |

**One consequence of a successful fill to keep in view:** `registered_fraction`
reaches 1.0, so the rules below that key on *low* registration — global
reconstruction, for one — stop applying. That is correct, because the capture is
now fully posed. It also hides the matcher weakness underneath, which is why
`filled_images` is published and why the report has to name the filled frames.

**Global reconstruction instead** when `registered_fraction` is low on an
*unordered* set and the matcher's `graph_components` is 1. That combination says
the correspondences are there and the order is the problem.

A geometric estimator that stalls on a scene whose view graph is already fragmented
is not the pose stage's failure. Fix the graph.

**The choice is one-sided in what it can prove, and that is worth knowing before
you spend a run on the alternative.** The feed-forward branch's reprojection
metrics are null by construction, so its artifact contains nothing that answers
"is this right", and the first reading that does is a triangulator's yield one
stage later. So at this stage the geometric branch can be shown to have *worked*
and the feed-forward branch cannot be shown to have failed. Running it anyway is
still worth it on a calibrated scene for one reason: `estimated_focal_ratio` is a
free, independent check on the calibration the geometric branch depends on, and
nothing else in the pipeline performs it.

---

## Whether a difference is real

Three rules, in this order. They were transferred here from other family files by
readers who needed them and found nothing at this stage; they are written down now
so the next reader does not have to.

**They answer different questions, and rules two and three will appear to
contradict each other if you forget which.** Rule two is for comparing two
configurations you happened to try. Rule three is for a parameter you have SWEPT
and bracketed. Applied to a sweep, rule two is self-defeating — the span it asks
you to price against *is* the sweep, so no configuration inside it could ever be
preferred, including the bracketed minimum rule three sends you to find. Readers
have hit exactly that and resolved it correctly by following rule three; the
resolution is written into rule two below rather than left to be rediscovered.

**FIRST, REGISTRATION IS A PRECONDITION, NOT A TIEBREAK.** `registered_fraction` is
the one unambiguous axis this stage has. **Never compare reprojection error between
two runs that registered different numbers of images** — a smaller model is an
easier one, and error will flatter the run that gave up. Three separate
configurations in one sweep produced better mean error by dropping cameras or
deleting a third of the structure, and each looked like an improvement until the
count was read beside it. If `registered_images` differs, the comparison is void;
say so and stop. The service's second solve is not such a comparison: it keeps the
wider solve by default rather than on its error, and when that solve registers
fewer cameras it records which, and what they cost, as a trade-off for you to
weigh — see the same
[limitations section](../../modules/pose_incremental/skills/limitations.md#escaped-points-start-a-second-solve).

**But `registered_fraction` is itself a configured quantity, so the rung above
only ranks two runs that obtained their poses the same way.** This module counts
frames it placed against structure that existed *at the moment of placement* — a
frame PnP refused gets one more try against the finished structure, but a frame
that never reached enough links to it is never tried — and that structure is gated
by its own triangulation parameters. Measured on a
capture that reconstructs perfectly, with byte-identical input tracks: tightening
the minimum triangulation angle alone took `registered_fraction` from **1.00 to
the seed pair**. Nothing about the data changed.

Two consequences, and the second is the larger one:

- **Compare registration at matched pose-stage parameters**, the same way
  [`optimization.md`](optimization.md) requires a matched track-length floor
  before comparing point counts. A registration difference across a
  parameter change is partly the parameter.
- **Across pipelines that obtain poses differently the axis is not comparable at
  all.** A feed-forward estimator poses every image or none, and a global
  reconstructor has no registration order to stall — neither is running the
  process this fraction describes. Full registration from those means something
  different from full registration here, and the tiebreak has to come from
  somewhere else (see [`health/ladder.md`](../health/ladder.md), which has the
  measured case where it went wrong).

**THEN, PRICE AN UNBRACKETED MARGIN AGAINST THE MODULE'S OWN SPAN.** Sweep one
cheap parameter with everything else held, and record the range the metric covers
across that sweep. A gap between two configurations narrower than that span is not
interpretable — it is inside the noise the module generates by itself. Measured on
one capture, fifteen configurations spanned 0.207 to 0.246 px of mean error, so a
6% difference between two of them settles nothing, and a reader correctly refused a
change on that basis. This is the same rule `plan/tracking.md` gives for
`trifocal_transfer_px`; there is no pose-specific span published, so measure it on
the capture in front of you.

**Its scope, which an earlier version left implicit and which cost several readers
a paragraph of confusion each.** This rule governs a comparison between two
configurations you have no other reason to separate. It does NOT void a bracketed
interior minimum: a turn is structural evidence — the metric rose on both sides of
it — and a span test cannot see structure, only width. Where rule three applies,
it wins, and the honest report is "the margin is inside the span, and the minimum
is bracketed, so I take it and I am not claiming it is large."

**And when the module has no cheap knob to measure a span with, say so rather than
inventing one.** Some modules expose only substantive parameters — every knob
changes the answer, or changes the model size and voids the comparison outright, so
there is no no-op sweep to take a noise floor from. On such a module this rule
cannot be applied at all. That is not a licence to treat every small difference as
real; it means falling back to rule three and reporting the weaker warrant
explicitly, which is what a reader driving the global bundle adjuster correctly
did.

**AND WHERE A PARAMETER HAS A TURNING POINT, BRACKET IT.** A monotone improvement
under a robust loss is weak evidence, because the loss is reshaping the very
residuals it downweights — the metric can improve while the model does not. An
interior minimum cannot be explained that way, so finding the turn is what makes
the result credible. It costs one run past the apparent optimum.

This applies to exactly one knob at this stage, `local_ba_loss_scale`, and it is
worth the run. Across a capture sweep, eight captures swept it far enough to see:
**four found a turn and four stopped while still improving.** On the four that
turned, a reader who had kept going past the optimum would have given back between
7% and 28% of the median error they had just won. On the four that did not, three
readers recorded in as many words that they had no stopping rule and settled on
judgement. Both halves of that are the cost of not bracketing.

**What neither rule can do:** establish that a configuration is *right*. There is no
ground truth here — see below. These rules tell you when a difference is too small
to mean anything, which is a different and more modest claim.

## What this stage can and cannot settle about the stages above it

**It can refute an upstream choice. It cannot confirm one.** With no ground truth,
two candidate chains are each internally consistent and neither can be shown
correct — but a chain that produces a diverged solve, a lost registration or a
collapsed seed angle has been shown *broken*, and that is a decision you can act
on. Across a seventeen-capture sweep every backtrack attempted at this stage was
settled negatively or not at all; none was settled in favour.

**And an upstream verdict can be exactly wrong until this stage sees it.** On one
capture, four of five matching- and tracking-stage quality readings preferred the
branch that the pose stage then showed produced 41% fewer points at 38% worse
error, from a seed with a third of the parallax. The upstream readings were not
misreported — the losing branch really was cleaner — it had bought that cleanliness
by discarding most of its correspondences, which only shows up once something tries
to build a model. **So a matcher question that could not be settled at tracking is
worth carrying forward rather than closing.**

**Two things follow for how you read this stage's own numbers.** Point count is
bounded by the subject, so it does not compare across captures — a cropped subject,
a mostly-empty frame, or a capture that is two disconnected sites all return correct
results that look like failures. And `median_triangulation_angle` and reprojection
error genuinely disagree; a configuration that improves the error while lowering the
angle is usually buying a smaller, easier model rather than a better one.

---

## What has NOT been measured

| Question | Needs |
| --- | --- |
| **Absolute pose accuracy of either** | ~~Ground-truth extrinsics.~~ **Measured.** Relative pose error against reference extrinsics, per capture, over the images each model registered. What it settled is above and in [`health/ladder.md`](../health/ladder.md); what it could not is that an error over the frames a stalled model kept is not comparable to one over a whole capture, so absolute *rankings* between models of unequal registration remain unavailable. **AUC at fixed angle thresholds has since been computed** over five families at a fixed view count, charging every unanswered pair as a miss so that models of unequal registration become comparable after all — see [`evidence/sparse-pose-2026-09.md`](../evidence/sparse-pose-2026-09.md). The shape it found: the geometric chain wins at the tight threshold on four families of five and loses at the loose one, which is the coverage-for-accuracy trade above, measured. |
| ~~**What feed-forward buys where geometric stalls**~~ | **Measured** twice. On seven captures where it genuinely stalled: full registration on all seven, worse per-pair accuracy on six. And again as a *fill* rather than a swap, on the worst captures of that campaign, where it beat both branches at every threshold provided the filled cameras were left out of the refinement. Both above. |
| **How far in-loop local BA carries** | Sequence length against drift, on captures long enough for drift to dominate. The mechanism is understood; the length at which it stops being enough is not. |
| **Whether the delivered-model reading matters on a dense chain** | It was tested on thirty-five captures that had been driven to a dense cloud and did not predict dense quality there at all. But every one of those was a capture with dense overlap and full registration, which is the regime where this reading is silent on the sparse path too — so what that tests is the population, not the reading. **Nothing has driven a thin capture to a dense cloud**, which is the only condition under which it could say anything. The module runs on both paths regardless — the question is only where to act on what it says. Until one does: act on it here, record it there. |
| **Whether estimated intrinsics are usable** | `estimated_focal_ratio` says whether a model agrees with a calibration. Whether its estimate is good enough to reconstruct with, on a scene with no calibration at all, is a different question and untested. |
