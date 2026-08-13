# Sparse reconstruction — choosing a reconstructor

Everything that produces `sparse_model/v1`. Five modules, and they are not all the
same shape: four take poses, one estimates them.

---

## The axes

### 1. Where depth comes from

**Ray intersection** (`SparseTriangulation`, `SparseTriangulationGTSAM`): two or
more rays from posed cameras, and the point is where they meet. It needs at least
two views with a real baseline, and it **cannot place a point seen once**. Its
error is measurable and it is the error it minimised.

**A learned prior** (`SparseVGGT`, `SparseMapAnything`): depth is predicted
per-view and unprojected with the supplied pose. A track seen **once** still gets a
3D point — the capability no geometric triangulator has, and unverified by
construction, since nothing checked it against a second view.

The consequence for reading the output: a geometric triangulator *placed* each
point to minimise reprojection error, and a learned one predicted a depth and then
measured the error. The same `max_reprojection_error` threshold therefore rejects
far more from the learned one, and the two `mean_reprojection_error` values are not
measuring the same thing.

### 2. Whether poses are an input or an output

Four modules take `poses/v1` and place structure in the frame they are given.
**`SparseGlobalCOLMAP` takes `pairwise_matches/v1` and estimates poses itself** —
rotation averaging over the whole view graph, then global positioning, then
triangulation. No registration order exists, so nothing can stall on an
unregisterable frame.

That makes it the answer to a *different* problem. The other four cannot fix bad
poses; this one replaces the way poses were obtained.

### 3. A learned prior carries a scale, and it must be measured

A model's depth is in the model's unit; the poses are in theirs. One scalar relates
them, and it is **not** 1.0 unless the poses came from the same model.

Two things follow, and both are properties of the family rather than of any module:

- **The scale must be estimated and reported with its spread.** The spread is the
  honest answer to "is this depth consistent with these poses at all", because a
  single scalar can only relate them if the ratio is actually constant across the
  scene. Assuming the scale produces a cloud that is correctly shaped and wrongly
  placed, with no metric moving.
- **Conditioning a model on the supplied poses does not put its output in their
  frame.** A model that accepts poses as input predicts *better depth* from them;
  it still answers in its own frame at its own scale. Reading its point maps
  directly is correct only when the poses also came from it, and silently wrong
  otherwise.

### 4. Within ray intersection: how many views the estimator uses

Two triangulators consume the same three artifacts and differ in one thing —
whether a track seen in *n* views is solved from **two** of them or from **all
of them**.

- `SparseTriangulation` triangulates from the **widest-baseline pair**, then
  verifies in every observing view. The right cheap answer, and it discards
  evidence: a track seen in eight views is placed by two.
- `SparseTriangulationGTSAM` solves over **every** observing view at once (LOST,
  optimal under a Gaussian noise model on the measurements), and carries a
  far-landmark bound the pairwise path has no equivalent of.

**The gain is a function of track length and nothing else.** At two observations
the two are the same computation and produce the same point. The advantage appears
at three or four, and is substantial at five or more. Read `long_track_fraction`
and `track_survival_5` on the tracks artifact to know which regime you are in
before choosing — those are the numbers that predict whether the choice matters.

**Bundle adjustment erases the accuracy half of the difference.** Refinement finds
the same optimum from either starting point, so on the points both estimators keep,
a post-BA comparison is a coin flip. What survives refinement is **yield**: the
better initial estimate passes the same reprojection filter more often, so more
structure reaches the final model. The rule that follows:

> **Pick the all-view estimator for reach, not for precision** — unless the
> pipeline has no bundle adjustment stage, in which case the precision is yours to
> keep.

The single-scene magnitudes are in
[`docs/import_lessons.md`](../../docs/import_lessons.md).

---

## Which end to reach for

**Ray intersection** whenever the tracks support it: `long_track_fraction` healthy,
poses registered, real baselines. It is more accurate than any prior and it reports
an error you can trust.

**A learned prior** when tracks are short — a high proportion of one- and two-view
tracks means a geometric triangulator will discard most of them, and a learned one
will place them. Read `single_view_points` afterwards: that is how much of the
cloud rests on nothing but the prior.

**Global reconstruction** when the poses are the problem and the view graph is not:
`registered_fraction` low with `graph_components` at 1.

**A note on which learned reconstructor**: `SparseMapAnything` can be conditioned
on the supplied poses and intrinsics and `SparseVGGT` cannot. Where the poses are
trustworthy that is free information; where they are suspect it is a hazard,
because the model will predict depth consistent with a wrong pose and the
scale-spread metric — which measures agreement between the two — will look healthy.
Running it both ways is the only signal.

---

## What has NOT been measured

| Question | Needs |
| --- | --- |
| **Accuracy against ground-truth geometry** | A dataset with reference structure. Every number so far is reprojection error, which is internal consistency, and it is not comparable between a module that minimised it and one that did not. |
| **Where short tracks make a learned prior win** | A sweep on `long_track_fraction`. The rule "reach for a prior when tracks are short" has no threshold, and the crossover is the whole question. |
| **Whether single-view points are usable structure** | They are unverified by construction. Whether they help or hurt a subsequent bundle adjustment is untested, and it is the argument for `min_track_len: 1` being the default. |
| **LOST against DLT at short baseline** | Controlled baselines. The theoretical advantage is clear; the baseline below which it matters is not. |
| **Whether pose-conditioning is net positive** | Scenes with poses of known quality. It measurably improves depth given good poses, and the failure mode given bad ones is understood but not quantified. |
