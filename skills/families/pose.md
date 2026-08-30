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
separate module.

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

Two rules, in this order. Both were transferred here from other family files by
readers who needed them and found nothing at this stage; they are written down now
so the next reader does not have to.

**FIRST, REGISTRATION IS A PRECONDITION, NOT A TIEBREAK.** `registered_fraction` is
the one unambiguous axis this stage has. **Never compare reprojection error between
two runs that registered different numbers of images** — a smaller model is an
easier one, and error will flatter the run that gave up. Three separate
configurations in one sweep produced better mean error by dropping cameras or
deleting a third of the structure, and each looked like an improvement until the
count was read beside it. If `registered_images` differs, the comparison is void;
say so and stop.

**THEN, PRICE THE MARGIN AGAINST THE MODULE'S OWN SPAN.** Sweep one cheap parameter
with everything else held, and record the range the metric covers across that
sweep. A gap between two configurations narrower than that span is not
interpretable — it is inside the noise the module generates by itself. Measured on
one capture, fifteen configurations spanned 0.207 to 0.246 px of mean error, so a
6% difference between two of them settles nothing, and a reader correctly refused a
change on that basis. This is the same rule `families/tracking.md` gives for
`trifocal_transfer_px`; there is no pose-specific span published, so measure it on
the capture in front of you.

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
| **Absolute pose accuracy of either** | Ground-truth extrinsics. Nothing here has been compared against them — the dataset in use carries none, so every comparison so far is internal consistency. AUC at 5/10/30 degrees against a posed dataset is the missing measurement, and the report now exports poses in a form that supports it. |
| **What feed-forward buys where geometric stalls** | A scene where it genuinely stalls. Measured so far only where the geometric estimator registers everything, which is the case it is best at and says nothing about the case the alternative exists for. |
| **How far in-loop local BA carries** | Sequence length against drift, on captures long enough for drift to dominate. The mechanism is understood; the length at which it stops being enough is not. |
| **Whether estimated intrinsics are usable** | `estimated_focal_ratio` says whether a model agrees with a calibration. Whether its estimate is good enough to reconstruct with, on a scene with no calibration at all, is a different question and untested. |
