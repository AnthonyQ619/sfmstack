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
rung below, each expressed as a **percentile within the reference corpus** — the reconstruction of every corpus capture by the reference
pipeline, recorded in the reference campaign under
[`evidence/`](../evidence/EVIDENCE.md). Until that campaign has run, the digest
reports every rung as *cannot evaluate: no reference yet*, and that is the honest
state, not an error.

Every component is computable from the model and its inputs alone — no ground
truth — and scene-size invariant, so a percentile against the corpus is a fair
comparison rather than a measure of which scene you are on:

| Rung | Component | Why it cannot be gamed |
| --- | --- | --- |
| Registration | registered frames / capture frames | a fraction, not a count |
| Conditioning | median triangulation angle over points | angle is scale-free |
| Composition | median track length, and points per registered frame | support, not raw point count |
| Coverage | median over frames of the fraction of image grid cells holding ≥1 observation | evenness, not totals |
| Error | median reprojection error **among well-supported points only** (track length ≥ corpus-median support) | composition-adjusted; dropping long tracks cannot flatter it |
| Yield | structure surviving into the model / structure the pipeline had available | self-normalised by the capture's own upstream supply |
| Pose agreement | median angular discrepancy between final relative poses and the pairwise two-view estimates (rotation angle, and translation *direction* angle) | never touches the points, so it sees the drift reprojection error cannot |

**The scalar, when one number is wanted, is the minimum percentile across the
seven** — the weakest rung. That matches the ladder's semantics (a model is only
as healthy as its worst constraint) and cannot average a failure away. The report
is always the vector plus the weakest rung; the raw point count and model size sit
in the header as stated context, because a raw count is only comparable *within* a
capture (model A against model B of the same scene — the procedure below), never
across scenes.

Three rungs need a definitional note:

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

On the reference corpus itself, ground-truth poses exist (the benchmark families
ship them), so the reference campaign records GT pose error **beside** the
internal readings — used once, to validate which internal readings actually track
truth before any definition is frozen. GT can never be a rung; the profile must
work on captures that have none.

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
