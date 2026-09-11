# Results that look fine numerically and are wrong

Every entry here was found the same way: a reading, or a set of readings, said a
model was good and the model was not. They are collected because the individual
metrics are all working correctly — each measures what it claims — and the error
is in what a reader concludes from them.

If you are about to ship a model on the strength of a number, this is the file
that argues with you.

---

## The upstream metrics all agree and the model is a fraction of the capture

**The smell:** a branch wins on inlier ratio, track conflict, trifocal transfer
and reprojection error, and registers a third of the images.

**Measured:** a configuration swept *five of five* upstream quality readings and
registered 8 of 26 frames. A second looked better at the matcher on inlier ratio
(0.983 against 0.926) and was 33× worse one stage later on track conflict. A
third had every matching-stage metric prefer it and lost after bundle adjustment
by 49% of the points.

**Why it happens:** those readings measure the agreement of correspondences that
*survived*. A matcher can raise all of them by keeping fewer, safer
correspondences — which is exactly what starves the view graph. They answer "are
these matches good", and the question is "is there enough here to reconstruct".

**What to do:** registration is a precondition, not a tiebreak
([ladder.md](ladder.md)). For a branch choice, carry both branches to a model
— the stage-local comparison has been wrong every time it was checked.

**A second shape of the same smell: nothing upstream separated the failures from
the successes.** The reference campaign drove one fixed pipeline over every
corpus capture. Three models registered two frames each, out of twenty-six to
forty-five. Looking upstream for what distinguished them from the thirteen that
worked:

- **The view graph was a single connected component on every capture in the
  corpus** — the failures and the successes alike. `largest_component_fraction`
  never left 1.0, so it separated nothing.
- Matcher inlier ratio on the three failures sat in the same band as the
  successes.
- Average track length was barely above two everywhere, failures and successes
  overlapping.
- Seed-pair geometry did not sort them either: two failures seeded on the widest
  pairs in the corpus and the third on one of the narrowest, inside the range
  the successful captures used.

**So "the graph is connected" is not the same claim as "the model will grow",
and on this corpus no upstream reading anticipated the collapse at all.** That
is not an argument for a better upstream metric; it is the reason the health
profile is read *after* the sparse step. The failure is only visible in the
object the failure is about.

**And the collapse was not a property of the captures.** The alternate-leg
campaign put each of those three captures through three different single-stage
swaps — a detector-free semi-dense matcher, a learned sparse detector/matcher
pair, and a feed-forward pose estimator — and **every one of the nine runs
registered between 0.88 and 1.00 of its capture**, against a reference that had
registered 0.04, 0.08 and 0.13.

**The pose swap is the one that settles it.** It changed nothing upstream of
pose and consumed the *same cached tracks* the reference had already failed on,
and it registered 100% of every capture in seconds.

So the correspondences were sufficient all along. What failed was
seed-and-grow: an incremental estimator places one image at a time against
structure built so far, and a chain that cannot get started does not report a
bad number — it reports two registered frames and a clean error over them. That
is why the upstream readings looked fine. They were fine.

**The lesson is about what a low registration licenses you to conclude.** It
says the configuration did not reconstruct this capture. It does not say the
capture is hard, it does not say the matching was thin, and it is not evidence
about the registry until a swap has been tried in a *different paradigm* — see
[bounce.md](bounce.md), whose third signal exists for exactly this.

---

## Every frame registered, every track long and clean, and no structure at all

**The smell:** the tracking stage reports the best numbers in the corpus, the
pose stage registers 100% of the frames, and triangulation returns an empty
model.

**Measured**, on an orbit rig driven by a point tracker instead of a match
graph. The tracker reported tracks an order of magnitude longer than the
match-graph branch produced on the same capture, almost all of them long, a
**zero** inconsistency rate, and near-total five-frame survival. The pose stage
registered every frame and seeded on the widest initial pair anywhere in the
corpus. Then triangulation rejected **every single track** — none behind a
camera, all of them failing the parallax and reprojection filters — and the
pose stage's own `points_triangulated` had already read 0.

**Why it happens:** a point tracker follows a chosen point through a sequence
and reports how confidently it followed it. That is a different question from
whether the pixel it landed on is the *same physical point*. Confidence,
consistency and survival can all be excellent while the tracked position drifts
off the true correspondence — and a drift of a few pixels is invisible to every
one of those readings, tolerable to a PnP solve fitting poses to a soft
consensus, and fatal to triangulation, which intersects rays and enforces a
reprojection threshold.

Two readings did see it, and both are about *geometry* rather than about track
quality: the tracker's trifocal transfer error sat several times above anything
in the corpus, and its duplicate-track rate said most of the tracks were
re-findings of the same few points. Neither is a track-quality metric, which is
the point.

**What to do:** on any tracker that follows points rather than merging matches,
read the geometric agreement readings and ignore the confidence ones. And treat
`points_triangulated` at the pose stage as the earliest honest signal — a pose
stage can report full registration with zero structure, so **registration is a
precondition and not a guarantee**; the top entry in this file is the same
mistake with the numbers reversed.

---

## A better mean reprojection error on a differently-composed cloud

**The smell:** two models, one with a visibly better mean, and nobody has checked
what the two clouds are made of.

**Measured:** a branch reporting 0.278 px was rejected in favour of one at 0.665
px because its `two_view_fraction` was 0.648. A two-view point is exactly
determined — four residuals, three unknowns — so its residual is near zero *by
construction*. On a two-view-dominated cloud a large share of the mean is made of
numbers that could not have been anything else.

**What to do:** read `two_view_fraction` beside the mean, and split the error by
observation count before comparing two models. A comparison that skips that has
been measured producing the *wrong ranking*.

---

## A connected graph that is held together by one edge

**The smell:** `graph_components` reads 1, `largest_component_fraction` reads
1.0, and the reconstruction still drops frames.

**Measured:** a capture where four frames hung off a single 17-match bridge edge
while both of those metrics reported a healthy graph. `min_image_degree` was 1.
Fixing it took that block to 30 edges of up to 615 matches.

**Why it happens:** both metrics are terminal conditions — they detect a graph
that has already fallen apart. Neither measures margin.

**What to do:** `min_image_degree` is the reading. A thin edge on a high-degree
image is redundant; the same edge on a degree-1 image *is* the graph.

---

## Points that reproject beautifully at the wrong depth

**The smell:** low reprojection error everywhere, and the cloud's shape is wrong.

**Measured, two ways.** A point on near-parallel rays sits at an ill-determined
depth and reprojects perfectly into the views that placed it — invisible to every
error metric and to a median, which is why `p05_triangulation_angle` exists. And
a coherent reflection produces correspondences to a virtual point *behind* the
surface: self-consistent, a RANSAC inlier, unremoved by bundle adjustment, and
carrying 3.1× the mean reprojection error of the rest of the model **as a
population** while looking unremarkable point by point.

**What to do:** read the tail, not the average — `p05_triangulation_angle` and
`p95_reprojection_error`. Where a hazard is localised, compare error
*distributions* over the region, never individual points.

---

## A metric that will not move, mistaken for a metric that is bad

**The smell:** several parameter moves each change a reading by a rounding error,
and the response is to keep tuning.

**Measured:** a detector's `spatial_coverage` reported 0.612 and would not rise;
masking the frame to actual content showed it was already at 0.985 — occupying
every cell that had anything in it. The number was at its physical ceiling. Two
readers spent runs on it.

**What to do:** a flat reading across a real sweep is a ceiling, and the sweep you
already ran is the evidence. Ask what the metric's denominator is before spending
another run on its numerator.

---

## A flag that keeps moving after the model has stopped

**The smell:** `converged` reads 0, and clearing it becomes the goal.

**Measured:** capped and converged solves of the same problem agreed on
`reprojection_error_after` **to four decimal places**, repeatedly. On one capture
the only configurations that *did* converge produced measurably worse models.

**What to do:** read `converged` as bookkeeping unless the error is also bad. Two
configurations agreeing to four decimals are the same configuration.

---

## A difference between two runs that is the pipeline, not the change

**The smell:** a parameter is changed, the model comes back a fraction of a
percent different, and that fraction is read as the effect of the change.

**Measured:** the same recipe run twice — in two separate artifact stores, so
both genuinely executed rather than one being served from cache — produced
bit-identical detection, matching and tracking, and then diverged at the pose
stage, ending a fraction of a percent apart in point count. Other captures on
the same chain reproduced exactly.

**The mechanism, because it predicts where else to look:** the divergence came
from a multithreaded solver inside the registration loop. The same residuals
summed in a different order across threads differ in the last bits, and an
incremental method feeds that straight into its next decision until it changes a
consensus set. It is not random sampling — the RANSACs on that path were probed
and are deterministic — so expect this wherever a multithreaded optimiser sits
in a feedback loop, and do not expect a seed to fix it.

**Why it stays hidden:** an unchanged recipe is served from the artifact store
and never re-executed, so nothing ever runs twice to disagree with itself. And
the obvious check does not work — an artifact id is derived from the recipe, not
from the bytes, so two artifacts with the same id are two runs of one recipe and
nothing more.

**What to do:** before believing a small difference, run the *unchanged*
configuration a second time in a fresh store and see how far it moves on its
own. That spread is the floor. A difference smaller than it is not a result.

---

## The same recipe, twice, and one of them is badly wrong

**The smell:** a model registers every frame, reports the best reprojection
error you have seen on the capture, and is wrong.

**Measured, and this is the clearest case in the corpus.** One capture was solved
seven times from the same recipe. On one set of correspondences, three
independent solves agreed to three decimal places on their error against
reference geometry. On another set — differing by well under a tenth of a
percent — three solves landed an **order of magnitude apart from each other**,
two of them roughly ninety times further from truth than the good model.

**The part that matters is what the rungs said about the wrong ones.** They
registered every frame. They reported *lower* mean reprojection error than
either correct model. Their triangulation angles were marginally better, one had
more than twice the minimum frame support, and their point counts and two-view
fractions were ordinary. **Judged on the health profile alone, the wrong models
would have been preferred.**

**Why this happens, in a form that transfers:** a capture's solve can have more
than one stable answer. Seed-and-grow picks an initial pair and grows, and where
the geometry admits a second self-consistent configuration, a tiny difference
early — a handful of correspondences, a last-bit difference in a refinement —
decides which one the run walks into. Both are *internally* consistent, which is
exactly why every internal metric is happy in both. Reprojection error measures
agreement between a model and the observations it kept; it cannot see a model
that is coherently wrong.

**What to do:**

- **Stop reading a low reprojection error as evidence of correctness.** It is
  evidence of self-consistency, and the wrong model here won on it.
- **Where a capture matters, solve it twice** and compare the two models to each
  other by the procedure in [ladder.md](ladder.md#comparing-two-finished-models).
  Two runs that agree are worth far more than one run that looks good. Two runs
  that disagree by more than the noise floor are telling you the capture has more
  than one answer, which is a fact about the capture and not a defect of the run.
- **Suspect this most where a capture is a wander with weak connections** rather
  than a tight orbit — somewhere the graph could plausibly fold a different way.
  It is not predicted by any rung; repetition is the only test.

---

## A band exceeded on a capture where nothing is wrong

**The smell:** a reading sits just outside a published range, and the run stops to
investigate.

**Measured:** a capture read outside a published maximum on a metric described as
"reliably quiet", while running at the exact protocol the corpus was fitted on.

**Why it happens:** a corpus maximum is an *order statistic* — the largest of N
draws — not a bound. The next capture exceeding it is the expected outcome.

**What to do:** ask whether the band could have contained your reading at all, and
whether any *diagnostic* fired. A band with no diagnostic behind it is describing
a corpus, not judging your capture.
