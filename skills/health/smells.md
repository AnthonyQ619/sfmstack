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
