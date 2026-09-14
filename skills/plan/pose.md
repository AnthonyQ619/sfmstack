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
| **Absolute pose accuracy of either** | ~~Ground-truth extrinsics.~~ **Measured.** Relative pose error against reference extrinsics, per capture, over the images each model registered. What it settled is above and in [`health/ladder.md`](../health/ladder.md); what it could not is that an error over the frames a stalled model kept is not comparable to one over a whole capture, so absolute *rankings* between models of unequal registration remain unavailable. AUC at fixed angle thresholds is still not computed. |
| ~~**What feed-forward buys where geometric stalls**~~ | **Measured**, on seven captures where it genuinely stalled: full registration on all seven, worse per-pair accuracy on six. Above. |
| **How far in-loop local BA carries** | Sequence length against drift, on captures long enough for drift to dominate. The mechanism is understood; the length at which it stops being enough is not. |
| **Whether estimated intrinsics are usable** | `estimated_focal_ratio` says whether a model agrees with a calibration. Whether its estimate is good enough to reconstruct with, on a scene with no calibration at all, is a different question and untested. |
