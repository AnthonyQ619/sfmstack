# Feature matching — choosing a matcher

Everything that produces `pairwise_matches/v1`. One of its axes reaches forward
into the tracker, which is why this choice is not local.

---

## The axes

### 1. Detector-based or detector-free — and what it costs downstream

A **detector-based** matcher (`FeatureMatchNN`, `FeatureMatchFLANN`,
`FeatureMatchLightGlue`, `FeatureMatchSuperGlue`) consumes `features/v1` and
matches a fixed keypoint table. Every correspondence names *which* keypoint it
matched, so `feature_index` is written.

A **detector-free** matcher (`FeatureMatchLoFTR`, `FeatureMatchRoMa`) consumes
images and produces correspondences directly. There is no keypoint table, so there
is no `feature_index`.

**That difference propagates into the tracker and changes how tracks are built.**
With `feature_index`, chaining is *exact*: two matches share a node when they cite
the same keypoint. Without it, the tracker must merge endpoints by **proximity**,
controlled by `merge_eps_px` — and the value that works is specific to the matcher
*and* the working resolution, not to the stage. A tolerance carried from one
detector-free matcher to another over-merges or under-merges.

So choosing a detector-free matcher commits you to tuning a tolerance in a
different module. That is a real cost, and it is invisible if you only look at this
stage.

### 2. Independent or joint

`FeatureMatchNN` and `FeatureMatchFLANN` decide each match on its own descriptor
distance and a ratio test. Nothing about match *A* informs match *B*.

`FeatureMatchLightGlue`, `FeatureMatchSuperGlue` and the detector-free pair reason
about all correspondences in a pair **jointly** — attention across both keypoint
sets, and an assignment that must be globally consistent. That is what lets them
survive repetitive structure, where a per-match ratio test has no way to prefer the
right one of several identical candidates.

Repetitive texture is therefore the clearest signal for a learned matcher: a
building frontage, a tiled floor, a row of identical windows.

**Judge that from the description, not from `repetitiveness`.** That metric
template-matches within one image and is not scale invariant, so a subject whose
repeating elements recede in perspective reads *low* — the most repetitive subject
in a corpus can produce the lowest reading in it — while a fronto-parallel grid
reads *high* for a purely geometric reason. It is dominated by viewing geometry
rather than by ambiguity, and the hazard here is *between-image* ambiguity, which
it cannot see at all. `repetition_notes` from `SceneDescription` is the reading to
act on.

### 3. Pairing is a graph decision priced as a matcher parameter

`pairing: exhaustive` is O(n²) pairs; a sequential window is O(n). This dominates
the cost of the whole stage and it decides the **view graph**, which decides
everything downstream — `graph_components`, track length, whether registration
stalls.

An exhaustive sweep on an unordered collection is usually necessary. A window on a
sequential capture is usually sufficient, and loop closure is what it misses.

### 4. Verification belongs here

Geometric verification is this stage's job, not the tracker's. `inlier_ratio` is
reported over the verified set, and everything downstream assumes it happened.

A consequence worth knowing: **a two-view epipolar check cannot catch an error that
only appears in three views.** Pairs are verified independently, so a correspondence
can satisfy every pairwise constraint and still not be one 3D point. That failure
is the tracker's `trifocal_transfer_px` to find.

### 5. `planarity` is the one metric here whose answer is not a matcher

`planarity` is homography inliers over fundamental inliers, averaged over pairs.
Near 1 it says the correspondences are explained by a *plane* as well as they are
by a *baseline* — and a baseline is what every geometric stage downstream needs.

**It is not a matching failure.** The matches may be perfect; `inlier_ratio` will
often be excellent alongside it. Nothing in this family fixes it, and tuning here
is the wrong response. That is why the metric is in the type at all: it is the
signal to change what you are doing, not how you are doing it.

**Two causes hide behind one number, and the fixes differ.**

| cause | what is true | what to do |
| --- | --- | --- |
| **Pure rotation** — the camera turned without translating | no parallax, so there is no structure to recover from these views at any quality of matching | no parameter helps. Drop the offending frames, or use views that do have translation. If most of the set is like this, the capture cannot be reconstructed and the honest answer is to say so |
| **Planar scene** — real baseline, but the structure is one plane | structure exists; it is the *two-view essential-matrix decomposition* that is ill-conditioned | avoid bootstrapping from two views: `SparseGlobalCOLMAP` solves the view graph globally, and `PoseVGGT` never decomposes an E at all. Or keep the incremental route and raise `init_min_angle_deg` so the seed is chosen from whatever non-planar pair exists |

**Distinguishing the two is not this metric's job.** `planarity` is per-pair and
averaged; it cannot tell "no translation" from "flat wall". What separates them is
whether *other* pairs in the set carry parallax.

**`SceneMotion` separates them before this stage runs**, and it is the one place a
measured number reaches a module choice directly. Its `degeneracy` group holds
`pure_rotation_risk` and `planar_dominance` as two numbers rather than one:
`K₂⁻¹HK₁` is exactly a rotation when the camera only turned, and the residual from
that grows with the baseline-to-depth ratio, so a homography that fits *because
the scene is flat* does not look like one that fits *because nothing moved*.

Read them at planning time, from `sfm_plan_brief`. **Both read zero on the large
majority of captures**, which is what makes a non-zero reading worth acting on
rather than weighing. The readings observed so far, as capture shapes:

| what the pair read | what it meant |
| --- | --- |
| a minority of pairs planar, a smaller minority rotation-only | the planar row above — real baseline, flat structure |
| a minority of pairs planar, rotation-only at zero | the pair working as designed: a flat subject, with the rotation discriminator correctly silent because the camera did translate |
| one pair of many on both | one frame's geometry, not the capture's. Read the seed the scorer chose; not a reason to change solver |

**The capture descriptions that produced these rows have been removed on purpose.**
They were specific enough to identify individual captures, which made the table a
lookup key rather than a rule — a reader recognising its own capture in a row reads
its own prior answer back and calls it confirmation. What generalises is the
*shape* of the reading, which is what the table now carries.

**The fraction is not the actionable half, and as of SceneMotion 1.1.0 you get the
rest.** Every non-zero reading above is one or two pairs of eleven, so no
diagnostic fires and the choice is between changing solver and keeping two views
out of the seed. `degeneracy/pair_planar` and `pair_pure_rotation` name which
pairs, each against its own index, and the artifact note names them in prose.

**Use that to price the fix, and ask the right question.** The question is not
whether the degeneracy is local — it is **whether a clean seed still exists after
the flagged pairs are excluded.** An incremental solver needs exactly one
well-conditioned pair to bootstrap from and then grows by resection.

**First, a correction about what is executable.** Earlier wording here told you to
"exclude that pair" or "keep it out of seed candidacy." **No pose module in this
repository has a pair- or frame-exclusion parameter.** The incremental estimator
exposes one seed lever, `init_min_angle_deg`, and it is a global threshold — the
blunt instrument this passage was written to avoid. So the flagged pairs are a
thing to CHECK THE SEED AGAINST after the run, not a thing to exclude before it.

- **One flagged pair, the rest clean and connected** → the seed is almost certainly
  safe, because the scorer prefers parallax and a degenerate pair has little.
  Run it, read which pair it seeded on, and confirm it is not a flagged one.
  Measured on several captures: it never was.
- **Flagged pairs sharing a common frame** → that frame is the suspect. Same
  procedure: run, read the seed, check. If the seed *did* land on that frame,
  raising `init_min_angle_deg` is the only lever available and it is global —
  which is the point at which the global solver becomes the cheaper answer.
- **Flagged pairs spread across the capture, or covering the only wide-baseline
  pairs** → there is no clean seed to find. Use a solver that does not bootstrap
  from two views.

**The row this table was missing: a high `planarity` with the per-pair probe at
zero.** That is the most common shape in the corpus, not an anomaly — a large flat
surface filling the frame raises the matcher's `planarity` while no *consecutive*
pair is degenerate, and the two numbers then disagree by a wide margin under
near-identical names. They are different measurements: `planarity` is a mean over
the whole verified graph, `planar_dominance` is a boolean fraction over consecutive
pairs only. **Neither overrides the other, and the resolution is a threshold rather
than an argument:** the incremental estimator's own limitations put the level at
which a homography explains the pairs as well as epipolar geometry does at about
0.9, and that figure is now the published ceiling on the metric. Below it, with the
probe silent, there is nothing to act on — measured on six captures reading well
above half with the probe at exactly zero, every one of which seeded at ample
parallax.

**Raising `init_min_angle_deg` is worth one run and rarely more.** Measured across
the corpus it moved the seed on some captures and left every downstream metric
unchanged on most of them; on one it improved every metric at once, and on one it
pushed the seed so wide the local solve diverged. Treat it as a probe with a
known-cheap cost, not as a fix with a known payoff.

**What the global solver costs, measured.** Run on the same matches, on captures
reading up to a fifth of pairs planar, it registered every frame and returned
roughly a third fewer points. **Do not read that as evidence against it** — the
failure it prevents is a *confident wrong model*, and a mis-decomposed essential
matrix yields a full, plausible, well-reprojecting cloud. On a degeneracy
question more points is not better and the usual metrics cannot referee. Treat it
as insurance with a known premium and an unmeasured payout.

**The "third" is a defaults artefact, not a property of the solver.** Measured
twice on different captures: the global solver defaults to `min_track_len: 3` and
the triangulators default to `2`, so their raw point counts are not the same
quantity. At a MATCHED track-length floor the ranking inverts — the global solver
returned 7.5% and 8% MORE points than the incremental chain on the two captures
where both were compared that way. So the premium is not "a third less structure";
it is "no two-view structure", which is a different trade and one some downstream
consumers would take. Compare at matched `min_track_len` or do not compare counts
at all. (This is trap 10 of this same file — a module run at its defaults is not
the module the plan specified — applied to the comparison the paragraph above
invites.)

One caution from the same set: a subject that *looks* planar need not read as
planar. A carved relief panel photographed head-on scores zero, because the
figures project far enough to cast their own shadows. The metric was right and the
intuition was wrong — see `skills/scene_to_pipeline.md`.

When the analysis has not been run, the fallback is still the pose stage's own
behaviour: a seed pair that cannot be found (`init_min_angle_deg` rejecting
everything) points at rotation; a seed that is found and yields a reconstruction
that drifts points at a plane.

**Where it lands downstream.** `PoseEssentialToPnP` fails to seed and names this
metric in its diagnostic; `SparseGlobalCOLMAP` reports degenerate pairs failing
verification correctly; `BundleAdjustmentGlobal`'s limitations read it beside
`median_triangulation_angle`. All three are describing the same upstream fact.

**Null is legal** — it means the matcher was told not to measure it
(`measure_planarity: false`), which is a saving worth taking only when the capture
is already known to have baseline.

---

## Which end to reach for

**Nearest-neighbour / FLANN** when the scene is well-textured and distinctive, or
the pipeline must run on CPU. They are not a fallback; on an easy scene they are
the right answer and cost nothing.

**A learned detector-based matcher** when the scene is repetitive, the baselines
are wide, or illumination varies — and pair it with the detector it was trained
against.

**But check connectivity before repetition — the order matters and is measured.**
Read `overall_magnitude` / `high_motion_tail` from `SceneMotion` first. A capture
reading high on those will produce a sparse view graph, and no matcher choice made
on repetition grounds will save it; the answer there is a learned detector AND
matcher together. Only once the graph is safe does the repetition question decide
anything. On a fast capture with a repetitive subject, both halves of the usual
argument are answering the wrong question — the graph fails before ambiguity gets
a chance to matter. See `skills/scene_to_pipeline.md` §3b.

**When the graph IS safe and the subject repeats, swap only the matcher.** A
jointly-reasoning matcher accepts classical descriptors — `FeatureMatchLightGlue`
carries a `sift` weight set and `auto` reads the producing module off the features
artifact — so this costs **no re-detection**, the same `features/v1` feeds both.
Measured across fourteen captures, that swap gains on well-connected repetitive
subjects and loses a third to a half of the model on well-connected
non-repetitive ones, so it is worth being right about which you have.

**"Being right about which you have" is the hard part, and the evidence says you
often cannot be.** One capture in that set had loud object-level repetition and
still lost roughly 40% of its points to the swap. On it the `repetitiveness` metric
read low and was right, while the description read the repetition as severe and was
wrong — the opposite of the general pattern. Since the two branches share one
detection artifact, the A/B is nearly free: **run both and compare rather than
predicting.** That is the one thing here that settles it, and it costs less than
being wrong does.

---

## A capture can change camera ORIENTATION, and nothing upstream will tell you

A block of frames shot in portrait where the rest are landscape — a roughly 90
degree in-plane roll — is invisible to every analysis metric in this stack, and
it destroys matching between the two blocks.

**Why nothing sees it.** `mixed_resolution` reads 0, because the pixel dimensions
are the same and merely transposed. `rotation_median_deg` reads a small number,
because dense flow could not fit anything across the orientation break and so
reports only the frames it COULD match — the metric is computed on the evidence
the defect removed. No scene-description field asks about framing. The reading
that finally exposes it is `min_image_degree` collapsing toward 1 on a block of
frames, which is a matcher-stage symptom, one stage after the damage.

**Why it matters at this stage rather than at detection.** Descriptor invariance
is the whole question. A rotation-invariant classical descriptor matches across
the break; several learned detectors are trained upright and do not, which
inverts the usual advice — the learned branch is the fragile one here.

**What to do.**

1. **Suspect it whenever `min_image_degree` is healthy for most frames and
   collapses for a contiguous block.** A run of frames that match each other and
   nothing else is the signature; a genuinely hard region degrades gradually.
2. **Look at the frames.** This is one of the few defects where the contact sheet
   answers in seconds what no metric answers at all.
3. **Prefer a rotation-invariant detector**, or a learned detector's
   rotation-augmented weights where it offers them. Measured on one capture:
   swapping to a rotation-invariant classical detector took the affected block
   from a single 17-match bridge edge to 30 edges of up to 615 matches, and
   `min_image_degree` from 3 to 9.

**This used to live in exactly one file** — one learned detector's limitations
page — where a reader choosing a branch would reach it only after already having
chosen. It is stated here because the decision it informs is made here.

## Choosing between two matchers: carry the A/B to a MODEL

**The stage-local metrics do not predict which branch produces the better
reconstruction, and on these captures they were actively misleading.** This is
the most replicated procedural finding in the corpus and it overrides the
temptation to settle the question cheaply.

Measured across a seventeen-capture sweep:

- A branch swept **five of five** upstream quality readings — best inlier ratio,
  best track conflict, best trifocal transfer, best reprojection error — and
  registered **8 of 26 images**.
- A branch that looked better at the matcher on inlier ratio (0.983 against
  0.926) was **33x worse one stage later** on the tracker's `inconsistent_rate`,
  with nine fewer pairs and image degree cut from 10 to 6.
- On another, *every* matching-stage metric preferred the joint matcher and the
  classical branch won after bundle adjustment, by 49% more points and 16% lower
  error at equal registration.

Every reader who chose from matcher metrics chose wrong. Every reader who carried
both branches through to a reconstruction chose right. So:

> **Run both branches to a sparse model before choosing.** Compare at equal
> registration, join on `track_id`, and split the error by observation count so
> that a difference in two-view composition is not read as a difference in
> quality.

**Why the stage-local readings mislead here specifically.** They measure the
agreement of correspondences that survived, and a matcher can raise every one of
them by keeping fewer, safer correspondences — which is exactly what starves the
view graph. The readings are not wrong; they answer "are these matches good"
when the question is "is there enough here to reconstruct". Those come apart
precisely on the captures where the choice matters.

**The one cheap check that IS predictive** is not a quality metric at all:
`min_image_degree`, because it measures the graph's margin rather than the
matches' agreement. A branch that drops it toward 1 is starving a frame no
matter how clean its inlier ratio looks.

## What the comparison costs, so you can budget it

The corpus previously called this A/B "nearly free". That is true of
**re-detection** — a joint matcher can take a classical detector's `features/v1`
directly, so the swap costs no detection — and it is false of the matching
itself, which is the expensive half. The sentence has caused readers to plan an
A/B they could not afford and to skip one they could.

What has been measured, as orders of magnitude rather than promises:

- Exhaustive classical matching on a capture of a few dozen frames, at some tens
  of thousands of keypoints per image, runs in the **tens of minutes** for the
  full pair set. Pairs grow quadratically with frames, so doubling the capture
  roughly quadruples this.
- A joint learned matcher's cost grows with the number of keypoints per pair as
  well as with pairs, and it runs on the GPU rather than the CPU, so the two do
  not trade off the same way. Raising a detector's cap raises its cost faster
  than it raises the classical matcher's.
- **The cheapest honest A/B is not the full pair set.** Both branches on a
  restricted pairing, compared on `min_image_degree` and on the decay of match
  count with frame separation, answers the branch question at a fraction of the
  cost — and if the two branches disagree there, that is when the full comparison
  is worth buying.

None of this is a model of runtime, and it should not be read as one. It is
enough to tell a reader that the exhaustive A/B on a large capture is an hour's
decision rather than a free one.

## Reading the per-pair counts

`pairwise_matches/v1` publishes `pairs/match_count` beside `pairs/image_pair`. The
scalar metrics are a mean and a min over that array; the array is where the
decisions at this stage actually live, because **the same count means opposite
things in different positions.** Three tests, all checkable on a capture nobody has
seen, none of them requiring a corpus.

**Read them in this order, and do not stop at the first one that clears.** The
third has a precondition that ordinary captures break; the first two hold
everywhere and come first. A fourth was cut — see the end of this section for what
it was and why, so it does not get reinvented.

**1. Do the pairs split into two confidence populations?** *(No precondition. It
arbitrates when the others disagree, and it is the only one of these that has ever
identified a specific bad edge in advance.)* Average `matches/confidence` per pair. Every matcher here publishes it,
classical ones included. A group sitting well below the rest, on a handful of
pairs, is usually not *thin* but *wrong* — one capture's marginal pairs carried a
few percent inlier ratio while the good pairs ran above ninety; on another, the
low group at 0.30–0.32 against the rest at 0.42–0.58 was the two ends of a linear
walk matched onto the wrong copy of a repeated structure. Rank within the artifact;
the scale is the matcher's own and means nothing across modules.

**It fires on perhaps a quarter of captures and is silent on the rest, and the
silence is a result.** A smooth continuum with no separated group means the kept
graph holds nothing that is wrong-rather-than-thin — which is worth knowing before
you spend runs hunting for it. What it cannot do is find a problem that lives in
the matches a pair kept rather than in which pairs survived.

**Two things make it pay beyond flagging edges.** First, when it does find a low
group, check whether raising the matcher's quality dial removes exactly those pairs
— on two captures the threshold that fixed the tracker's conflict rate dropped
precisely the pairs this test had named, which turns a coincidence into
corroboration from two stages. Second, and cheaper than any of these tests: the
same array **prices a threshold sweep before you run it.** Thresholding
`matches/confidence` per pair predicts how many matches survive at a candidate
value and which pairs fall under `min_matches`. One capture predicted its surviving
count exactly and named the pair it would lose, turning a six-run search into one
calculation.

**2. Is the weak edge load-bearing, or redundant?** *(No precondition.)* Read
`match_count` against `min_image_degree`. A thin edge on an image that carries nine
others bounds nothing; the same count on an image that carries no other *is* the
graph. Two configurations have been measured with near-identical weakest links —
sixteen against seventeen — where one left two images on a single edge each and the
other gave every image eight or more. No scalar separated them.

**3. Does the count decay with frame separation?** ***Precondition: index distance
must track viewpoint distance, and `ordered: 1` does not establish that.*** Where
it holds, a count that *rises* at large separation is either a genuine loop closure
— **corroborated by its neighbours**, so if the first and last frames really
overlap the second-to-last overlaps the first comparably — or a repetition phantom,
**isolated and asymmetric**. That reading refuted a detector swap that had won every
headline metric.

Where the precondition fails it returns nothing or the wrong answer, and both have
been measured. On a capture whose path reverses, the rank correlation between
separation and count came out near zero, because the far-index pairs are
near-duplicate viewpoints. On another, eight phantom edges **decayed monotonically**
into the `min_matches` floor — exactly the shape this test calls genuine — and only
tests 1 and 4 caught them. Check the precondition first: one adjacent pair rotating
far less than its neighbours is a reversal, and a subsampled capture keeps its
filenames in order while multiplying the viewpoint change between them.

**A fourth test was cut, and the reason is worth keeping so it is not
reinvented.** It read the spatial spread of each pair's matches, on the premise
that a genuine wide-baseline pair concentrates them in the sliver two views share
while a spurious one scatters. Across eighteen capture-applications it produced one
positive — and on that capture test 1 flagged the same edge, more cheaply. Its
premise is false for the most common shape in this work: a compact subject that
stays fully co-visible across an arc, where the genuine pairs scatter and the
marginal ones concentrate, so read literally it inverts. If you notice matches
looking concentrated on a pair, that is not evidence of anything; use test 1.

**Use these before believing a connectivity gain**, and when they disagree, **test
1 wins**. Every one of them is a statement about the capture in front of you, and
none needs to know which dataset it came from.

**Where the tests saturate, there is a further reading.** On a well-connected
capture `pairs_matched` and `min_image_degree` can both sit at their arithmetic
ceilings across every configuration you try, with no diagnostic firing and
`inlier_ratio` spanning a narrow band over runs that differ tenfold in quality.
`cycle_merge_rate` and `cycle_split_rate` still separate them: they count the
matches that pass their own two-view check and contradict themselves once a third
view is compared, which is the failure none of the tests above can see.

**Read the SUM of the two when you are asking what the tracker will report, and
each one separately when you are asking what to fix.** That distinction is measured
and it is not a nicety. The merge rate alone was annotated as the forecast and it
is not one: a capture read 0.0016 on it — clean — and produced a track table 17%
self-contradictory, because all of its signal was in the split term. Over 54 paired
runs the sum moved monotonically with the tracker's `inconsistent_rate` within
every capture, and the constant relating them varies about fourfold between
captures — so **sweep with it, do not threshold on it.**

> **"Monotonically within every capture" has since failed twice, and in a way
> that matters for how you sweep.** On one capture the sum fell 7.7x across a
> sweep while `inconsistent_rate` fell 1.17x; on another `inconsistent_rate`
> moved 0.005 across a sweep whose registration went from 5 frames to 30, and was
> non-monotonic besides. In both, the cycle terms tracked the change cleanly and
> `inconsistent_rate` did not.
>
> The practical consequence is the reverse of what the sentence above implies:
> where the two disagree, **the cycle terms are the more sensitive instrument and
> `inconsistent_rate` is the one that can sit flat through the range that decides
> the run.** Sweep on the cycle terms; use `inconsistent_rate` to confirm, not to
> price.

Which term carries the signal tells you where the repair is:

- **merge high** — the matcher is admitting wrong correspondences. Tighten it.
- **split high, merge clean** — the detector is emitting several keypoints at one
  physical point, which no matcher setting reaches, and which arrives at the
  tracker as an unreachable floor on its `split_rate`.

---

**Detector-free** when the detector is the thing that failed: `keypoints_min` low,
`spatial_coverage` low, a textureless or blurred capture. Expect to tune
`merge_eps_px` in the tracker afterwards, and read the tracker's
`inconsistent_rate` and `split_rate` together when you do — each is blind to the
error the other catches.

**Nothing here at all** is also an option: `FeatureTrackVGGSfM` and
`FeatureTrackTapir` consume `features/v1` directly, so a pipeline can go
scene → detect → track with no matcher. See [tracking.md](tracking.md).

---

## What has NOT been measured

| Question | Needs |
| --- | --- |
| **How much a learned matcher buys on repetitive structure** | A repetitive scene. Everything measured here so far is a well-textured object with no repetition, where the ratio test is not under stress. |
| **Where detector-free overtakes detector-based** | A sweep along texture strength. The rule "reach for detector-free when the detector fails" has a direction and no threshold. |
| **Whether `merge_eps_px` can be derived rather than tuned** | Its right value is known to depend on matcher and resolution. Whether it is predictable *from* the matcher's own reported precision is open, and would remove a manual step. |
| **The cost of an exhaustive sweep against what it recovers** | Loop closures found per extra pair, on a sequential capture. This decides pairing on every large set and is currently a guess. |
