# When a reconstruction is good enough, and when to stop turning a dial

Two different questions. The first is about a MODEL, the second about a SWEEP,
and answering the second one well is most of how you get to answer the first.

---

## The objective

**As much structure as possible, from a model you have reason to trust.**

Point count is the thing being maximised, because points are what the
reconstruction is *for* and every later stage consumes them. But it is maximised
SUBJECT TO the model being trustworthy, and the constraints below are not
tie-breakers — a model that fails one of them is not a smaller win, it is a
different and worse object that happens to report a bigger number.

The single most common way to get this wrong is to rank two models by
reprojection error. **A smaller model is an easier model.** Drop the hardest
third of the points and the mean error falls, every time, on every capture. Error
is only meaningful between models that contain the same things.

---

## The constraint ladder

Read in this order. A failure at any rung disqualifies the model regardless of
what the rungs below say — that is what makes them constraints rather than
weights.

### 1. Registration is a precondition, not a tiebreak

Every frame the capture can support should be in the model. A branch that
registers a fraction of the images has not produced a worse model of the scene;
it has produced a model of a *different, smaller* scene, and its metrics describe
that smaller scene.

This rung earns its place at the top because it is the one that most often
disagrees with everything else. A configuration has been measured sweeping every
upstream quality reading available — inlier ratio, track conflict, trifocal
transfer, reprojection error — and registering under a third of the frames. Each
of those metrics was correct about what it measured. None of them was measuring
this.

If two candidates register the same frames, go on. If they do not, prefer the one
that registers more, and only look further if you are choosing between how they
got there.

**A precondition is not a guarantee, and the other half of that has now been
measured too.** A configuration has registered **every frame of a capture** and
produced a model with **no points in it at all** — the pose stage reported full
registration and zero triangulated structure in the same breath, and the
triangulator then rejected every track it was offered. So a registration
fraction of 1.00 clears this rung and says nothing about the rungs below it;
`points_triangulated` at the pose stage is the earliest reading that would have
caught it. The case is in [smells.md](smells.md).

### 2. The structure has to be determined, not merely consistent

`p05_triangulation_angle` is the reading here. A point on near-parallel rays sits
at an ill-determined depth while reprojecting beautifully into the very views
that placed it, so it is invisible to every error metric and to a median. Where
the weak tail of the parallax distribution is low, the SHAPE of the cloud is
uncertain in a way its error does not report — and a later stage that consumes
depth will find that out for you.

### 3. The headline error has to be about the model, not its composition

`two_view_fraction` is the reading. A point seen in exactly two views is exactly
determined — four residuals, three unknowns — so its residual is near zero *by
construction* rather than because it is good. On a two-view-dominated cloud a
large share of the mean is made of numbers that could not have been anything
else, and the headline reads better than the model is.

This is the rung that most often flips a decision. A branch with a visibly better
mean error has been measured losing on inspection, because most of its advantage
was composition: two-view points it had kept and the other had not.

### 4. Coverage has to be even

`min_frame_points` is the reading — the emptiest registered camera, not the
average. A camera can be registered and carry almost no structure, and a
whole-model `point_count` cannot be moved by one starved view. That view is where
the next stage fails.

**What to do when it reads low, because every file that names this metric says
to READ it and none said what to do.** A reader shipping an otherwise good model
hit exactly that and had to compute the per-frame distribution by hand, because
no metric or series publishes it. In order:

1. **Find out whether it is one frame or a tail.** One starved camera among
   forty is a local fact and usually not worth a run; a tail of them is the
   model telling you a whole region is thin. The distribution is derivable from
   the model's `observations` group and nothing publishes it directly.
2. **Look at that frame.** The same three causes recur — it is aimed at flat or
   untextured surface, it is at the end of the traverse with few neighbours, or
   it is the one frame the detector starved. The first two are properties of the
   capture; the third is fixable at detection.
3. **Fix it upstream or do not fix it.** Nothing at this stage adds structure to
   a camera. The levers are exposure normalisation and the keypoint cap at
   detection, or more neighbours for that frame at the matcher — and both have
   already been tried by the time most readers get here.
4. **Otherwise ship it and say so in the watch line.** A low reading on one
   frame is a prediction about where the *next* stage will fail, which is worth
   recording and is not by itself a reason to reject a model that clears the
   rungs above.

### 5. Only now, the error

`mean_reprojection_error` for the level and `p95_reprojection_error` for the
shape. Read them together: a mean close to p95 is a uniformly mediocre model, a
mean far below it is a good model carrying a few bad points, and those want
opposite responses.

---

## The health profile — the ladder as seven measurable rungs

**The rungs are read after the sparse reconstruction step, and never before.**
The profile describes a finished sparse model; no upstream stage — detection,
matching, tracking, pose — should be judged against these rungs, even where a
rung's component sounds computable early (a registration fraction, a coverage
number). Upstream stages have their own metrics and diagnostics, and the first entry in
[smells.md](smells.md) is exactly what judging the model from upstream readings
produces: every upstream metric agreeing while the model is a fraction of the
capture. The digest enforces the scope mechanically: it attaches only to a run
that produced a `sparse_model/v1`.

The run summary of any such run carries the **health profile**: one reading per
rung below, each expressed as a **percentile within the reference corpus** — the
reconstruction of every corpus capture by one fixed pipeline, recorded in
[`evidence/reference-pipeline-2026-09`](../evidence/reference-pipeline-2026-09.md).
Read that file before trusting a percentile: it says what ran, and it says which
two of these rung definitions did not survive their own first reading. Where a
rung cannot be computed the digest reports it as unevaluable rather than
guessing, which is the honest state and not an error.

Every component is computable from the model and its inputs alone — no ground
truth — and scene-size invariant, so a percentile against the corpus is a fair
comparison rather than a measure of which scene you are on:

| Rung | Component | Why it cannot be gamed |
| --- | --- | --- |
| Registration | registered frames / capture frames | a fraction, not a count |
| Conditioning | median triangulation angle over points | angle is scale-free |
| Composition | share of points seen in MORE than two views | support, not raw point count |
| Coverage | median over frames of the fraction of image grid cells holding ≥1 observation | evenness, not totals |
| Error | median reprojection error **among points seen in more than two views** | composition-adjusted; dropping long tracks cannot flatter it |
| Yield | structure surviving into the model / structure the pipeline had available | self-normalised by the capture's own upstream supply |
| Pose agreement | median angular discrepancy between final relative poses and the pairwise two-view estimates (rotation angle, and translation *direction* angle) | never touches the points, so it sees the drift reprojection error cannot |

**The scalar, when one number is wanted, is the minimum percentile across the
seven** — the weakest rung. That matches the ladder's semantics (a model is only
as healthy as its worst constraint) and cannot average a failure away. The report
is always the vector plus the weakest rung; the raw point count and model size sit
in the header as stated context, because a raw count is only comparable *within* a
capture (model A against model B of the same scene — the procedure below), never
across scenes.

Five rungs need a definitional note:

- **Composition is the share of points over-determined, not the median support.**
  It was the median observations-per-point until the reference campaign measured
  it, and the median read **exactly 2 on every capture in the corpus** — healthy
  and broken alike — because a sparse cloud is two-view-dominated by
  construction. A rung with no variance across the reference corpus has a
  meaningless percentile, which is worse than no rung: it still reports a number.
  The replacement is the reading rung 3 above already argues from, so the
  profile and the ladder now measure the same thing. **A composition of exactly
  zero is a hard downstream precondition, not a soft reading**: an optimizer
  that refines a window of cameras drops points below three views by default,
  so a cloud with no over-determined point at all leaves it nothing to solve and
  it refuses to run. Measured on the three captures reading zero here and on
  none of the others — the rung predicted the refusal exactly.
- **"Well-supported" in the error rung means more than two views, and that is
  arithmetic rather than a tuned cut point.** It was the corpus-median support
  until the reference campaign measured that median at 2 on every capture, which
  admitted every point and left the qualifier doing nothing. A two-view point is
  exactly determined, so averaging its residual in measures the algebra rather
  than the reconstruction.
- **Yield is recorded in both its forms** until the reference campaign decides
  between them: track-yield (3D points / tracks entering reconstruction) and
  observation-yield (observations in the model / observations in the tracks). The
  second is stricter — it also punishes truncating long tracks — and is the
  provisional default. Yield is the profile's anti-gaming guard: any tuning that
  flatters error, composition or coverage by discarding structure pays here,
  visibly. Its own blind spot — a starved pipeline converting its few tracks
  efficiently — is covered by coverage and registration, which read the emptiness
  directly.
- **Pose agreement** exists because the profile otherwise reads pose quality only
  through the points, and a pose set that is *self-consistently* wrong — drift, a
  solve locked into a distorted but coherent frame — produces structure that
  reprojects cleanly (see the wrong-depth entry in [smells.md](smells.md)). It is
  a consistency reading, not an error against truth: the pairwise measurements
  are themselves noisy, and the discrepancy blends both errors.
- **Percentiles over the corpus are coarse** — with seventeen reference draws
  they move in roughly six-point steps — and a capture below the corpus minimum
  reads as *below the observed range*, never as *failed*: the minimum is the
  smallest of seventeen draws, not a floor.

**What the ground truth settled, and what it could not.** The reference corpus
has ground-truth poses, so the campaign computed true pose error beside every
internal reading — once, to check whether the rungs track accuracy. The answer
was that the check itself does not work, for a reason that vindicates the
design: true pose error is measured over the images a model *registered*, so a
model that keeps two frames and gets that one pair right outscores a complete
reconstruction. Two such models did. **A single accuracy number cannot see what
a model discarded**, which is why this profile is a vector with registration
first, and why the weakest-rung scalar is a minimum rather than a mean — on the
worst model in the corpus, conditioning and pose agreement both sit near the top
of their distributions, and a mean would have called it mediocre instead of
broken.

A rung is therefore validated by comparing two models of the SAME capture at
EQUAL registration, where a ground-truth comparison is legitimate. **That
comparison has now run**, and what it found is below.

---

## What the controlled comparisons said about each rung

A comparison is legitimate when the two models contain the **same images**, and
the campaign produced two kinds. The direct kind: a swap at or after the pose
stage cannot add or drop a camera, so the alternate registers exactly what the
reference did, by construction. The stronger kind: several captures ended up
with **three or four different pipelines each registering 100% of the capture**,
which makes every pair among them comparable and — unlike the first kind —
includes cases where the alternate genuinely wins.

Taking every pair of models of one capture where both registered the whole
capture gives **seventeen comparisons**, and each rung can be scored on whether
it ranked the pair the way ground truth did
([`evidence/alternate-legs-2026-09`](../evidence/alternate-legs-2026-09.md)):

| Rung | ranked correctly | of |
| --- | --- | --- |
| **Coverage** | **17** | 17 |
| **Yield (observations)** | **17** | 17 |
| Yield (tracks) | 16 | 17 |
| Point count | 16 | 17 |
| Pose agreement (either form) | 14 | 15 evaluable |
| Error | 10 | 17 |
| Conditioning | 9 | 17 |
| **Composition** | **6** | 17 |

**Coverage and observation-yield did not miss once in that campaign.** They are
the two rungs that ask how much of the capture the model actually accounts for —
one over the image plane, one over the structure the pipeline supplied — and
nothing in it fooled either.

### A second campaign widened the set, and coverage did not hold

Driving the whole loop over every capture at full frame count produced a further
twenty comparable pairs
([`evidence/agentic-campaign-2026-09`](../evidence/agentic-campaign-2026-09.md)).
Excluding one capture on which every branch failed — all its models are broken
and comparing two broken models measures nothing — fourteen clean pairs remain:

| Rung | ranked correctly | of |
| --- | --- | --- |
| Coverage, yield (both forms), point count | 12 | 14 |
| Conditioning | 11 | 14 |
| Error | 9 | 14 |
| Composition | 8 | 14 |

**Observation-yield survives as the rung to lean on; coverage does not.** Yield
is now right on roughly thirty-five of thirty-seven comparisons across both
campaigns. Coverage is on thirty-one of thirty-six, and its misses are not
scattered — see the next section, which gives them a mechanism.

Conditioning's better showing here is the split below working as designed: these
pairs are nearly all genuine branch changes rather than point-retention rules,
which is the half of that table where it reads correctly.

### Coverage is a selection effect too, and the selector is the DETECTOR

Composition moves with a point-retention rule. Coverage moves with the
**detector's spatial-distribution policy**, and the mechanism is the same shape:
the rung is measuring an upstream choice rather than the model's quality.

A detector that spreads a fixed budget evenly across the frame — suppression,
or a learned detector's own non-maximum policy — hands the reconstruction points
in more of the grid cells coverage counts, whether or not those points are
better. Measured on two captures where two pipelines each registered the whole
capture: in both, the branch with the higher detector-stage `spatial_coverage`
produced the higher model-level coverage rung, **and was the less accurate model
against ground truth**, by a factor of two on one of them.

So coverage joins composition and conditioning as a reading that has to be
qualified rather than ranked on:

> **Compare coverage between two models only when they came from the same
> detector at the same cap.** Across detectors it is partly comparing
> suppression strategies. Where they differ, read yield and point count beside
> it and let coverage explain rather than decide.

**The error rung barely beat a coin flip overall, and lost badly where it
mattered.** Ten of seventeen is not a signal at this sample size, and on the
eight comparisons that cross *branches* rather than optimizers it was right
**twice** — actively anti-correlated with truth on the comparisons a planner
would actually be making. The composition adjustment did not rescue it:
restricting the median to points seen
in more than two views removes the crudest version of the trap and leaves the
rest, because a model can still hold fewer and better-supported points, report a
lower error, and sit further from the truth. Rung 5 says to read the error last;
this says it may not deserve a place in a ranking at all.

### Composition and conditioning are conditional readings, not rungs you can read alone

Split the same seventeen comparisons by what actually differs between the two
models, and these two rungs stop looking unreliable and start looking
*conditional*:

| | conditioning | composition |
| --- | --- | --- |
| pairs differing by a **point-retention rule** (an optimizer that deletes short tracks) | 1 of 9 | **0 of 9** |
| pairs differing by an actual **change of branch** (detector, matcher, tracker, pose) | **8 of 8** | 6 of 8 |

One mechanism explains both halves. **Both rungs rise when short,
weakly-triangulated points are discarded** — the median widest angle rises
because the low tail left, the over-determined share rises because the two-view
points left — and nothing about the surviving geometry improved. One leg drove
composition to a flawless **1.000 on every capture it ran**, by removing every
two-view point from a model that was otherwise a strict subset of the one it was
being compared against, and which was worse against truth almost every time.
Where the difference between two models is real geometry rather than a filter,
the same rungs are excellent.

**Yield is the reading that tells you which case you are in**, and it is the
whole reason yield is in the profile:

| | composition & conditioning | yield | truth |
| --- | --- | --- | --- |
| a filter removed the weak points | rose | **fell** | worse |
| the branch produced better tracks | rose | **held** | better |

**So never read composition or conditioning without reading yield beside them.**
With yield falling, either is a measure of what a model threw away, dressed as a
measure of what it kept. This is the same trap as rung 3 above, one level up:
rung 3 warns that a model's *error* is a function of its composition, and this
warns that its *composition* is a function of what it discarded.

### Pose agreement, and the pipeline that cannot have it

Pose agreement ranked 14 of the 15 comparisons it could be computed on. It is
the only rung that never touches the points — it compares the final relative
poses against the pairwise two-view estimates, over cameras the swap did not
change — which is why the point-retention confound above does not reach it: it
scored the same on both halves of the split.

**And it is the one rung a pipeline can be shaped so as not to have.** Those
two-view estimates are re-derived from a matches artifact, so a pipeline with no
matching stage at all — a point tracker run straight off a detector — has
nothing to compare its final poses against and the rung reports unevaluable.
That is the two missing comparisons. The rung with the best independent record
is absent exactly where the profile has fewest other defences, because a
matcherless branch also has no matcher diagnostics upstream.

### Two limits that apply to all of the above

**Seventeen comparisons is a small sample, and they are not independent.** Nine
of them are one capture against one optimizer swap, repeated across the corpus,
so they contribute one mechanism nine times rather than nine mechanisms. The
eight cross-branch comparisons come from three captures. A rung scoring 17 of 17
here has not been shown to be reliable in general; it has been shown not to have
failed yet, on a corpus this small.

And **percentiles saturate outside the reference corpus.** Several alternate
models fall below the corpus's observed range on the error rung and read 0
together, so the weakest-rung scalar stops ordering them. The corpus is one
pipeline's distribution; an alternate leg is out of distribution for it, and the
scalar degrades to a tie exactly where the vector still separates.

### The profile has a hole, and it is on the branch that rescues registration

**Both yield rungs are unevaluable on a model whose poses came from a global
reconstructor**, because that module consumes matches and produces a
`sparse_model/v1` directly — there is no tracks artifact, so there is no
denominator for "structure the pipeline had available". The digest reports it
honestly as unevaluable rather than guessing, which is correct behaviour and
still leaves you without the rung.

That matters more than the same gap on pose agreement (below), for two reasons.
Yield is the rung with the best record across both campaigns, and it is the
reading that tells you whether a movement in composition, conditioning or
coverage is a real improvement or a selection effect — so losing it removes the
discriminator at the same time as the score. And the global reconstructor is
exactly what [`plan/pose.md`](../plan/pose.md) prescribes when registration
stalls, so the hole opens precisely on the captures that most needed help.

**Measured, and it has already cost a decision.** On a shallow-relief subject
two pipelines each registered the whole capture: the incremental one carried
more points and higher coverage, the global one fewer of both, and against
ground truth the global model was better by roughly a factor of sixty. With
yield unavailable the tiebreak fell to coverage and point count alone, and both
chose the worse model. On a dim built interior the same shape recurred, milder.

**So when one candidate is a global reconstruction, do not settle the choice on
the profile.** Read registration first as always; then, if they tie, prefer a
comparison the profile can actually make — same reconstructor, or a
reconstruction-free check such as reprojection distributions split by
observation count — and say in the plan that the vector was short a rung.

---

## Comparing two finished models

Most stopping decisions are really this decision. The procedure that survives
scrutiny:

1. **Equalise registration first.** If the two models do not contain the same
   cameras, rung 1 has already answered you.
2. **Join on `track_id`, never on row order.** Both models carry it and the rows
   are not in the same order — differencing positionally gives an answer that is
   wrong by roughly an order of magnitude and looks entirely plausible.
3. **Split the error by observation count** before comparing. If one model holds
   more two-view points than the other, its mean is flattered by rung 3, and the
   split is what separates "genuinely better" from "differently composed".
4. **Prefer more structure** once 1–3 are level. This is the objective.

A comparison that skips step 3 has been measured producing the *wrong ranking*,
so it is not optional care — it is the difference between a result and a coin
flip.

---

## When to stop turning a dial

### Bracket, do not walk

A monotonic improvement across the values you happened to try is not a result.
Take the value past the one you like and confirm it is worse. An unbracketed
"better at the edge of what I tried" is the single most common way a sweep
reports a discovery that is really the boundary of the search.

### The no-op test

Before spending runs on a parameter, ask what the artifact would look like if the
parameter did nothing. If a filter's threshold is already looser than the data it
filters, the run returns a byte-identical artifact and the sweep measures your
patience. Read the distribution the parameter acts on first.

### Stop when the movement is smaller than the thing you are comparing against

Two configurations agreeing to four decimal places are the same configuration.
This is worth stating because a flag can keep moving after the model has stopped:
a solve at its iteration cap and a converged solve of the same problem have been
measured agreeing to four decimals repeatedly, so clearing the flag bought
nothing and cost a run.

### Stop when the ceiling is known and small

Some gains have a bound you can read before spending anything. Where a cheap
module reports the fraction of candidates it kept, an expensive module that can
only recover what the cheap one discarded is bounded by the remainder. If that
headroom is a percent, the swap is nearly free of consequence whatever else is
true of it.

### Stop when the next question is upstream

If a dial is not moving what you need, the constraint is usually not in this
module. Structure that was never triangulated cannot be refined; frames that
never matched cannot be registered. A stage-local sweep cannot reach a defect
that entered two stages earlier, and continuing to sweep is how a run spends a
sixth of its budget in a decision tree whose branches all end in the same place.

---

## What this file cannot tell you

**There is no absolute threshold here, and that is not an omission.** No
reprojection error is "good" independent of the capture: the same number is
excellent on a wide-baseline rig orbit and mediocre on a narrow-baseline walk,
because the two are not measuring equally constrained geometry. Everything above
is comparative or structural for that reason.

**Nothing here is ground truth.** Every reading in this stack is internal
consistency — the model agreeing with itself. The pose-agreement rung narrows
this blind spot (it checks the global solve against the local evidence it was
built from, independently of the points) but does not close it: a reconstruction
can satisfy every rung above and be globally wrong in a way no metric here can
see. Where accuracy
against reference geometry actually matters, that requires a dataset with
reference structure, and the answer does not live in this pipeline.
