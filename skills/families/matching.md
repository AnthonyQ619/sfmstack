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

| what was captured | what the pair read | what it meant |
| --- | --- | --- |
| a near-planar built surface walked past nearly parallel, with a mirrored object in front of it | a fifth of pairs planar, a tenth rotation-only | genuinely the planar row above — real baseline, flat structure |
| a wall of flat panels shot nearly square-on | a fifth of pairs planar, rotation-only at zero | the cleanest confirmation the pair works: a flat subject, with the rotation discriminator correctly silent because the camera did translate |
| an orbit around an object with one overhead pass across a flat roof plane | one pair of eleven on both | a single frame's geometry, not the capture's. Watch the seed; not a reason to change solver |

**The fraction is not the actionable half, and as of SceneMotion 1.1.0 you get the
rest.** Every non-zero reading above is one or two pairs of eleven, so no
diagnostic fires and the choice is between changing solver and keeping two views
out of the seed. `degeneracy/pair_planar` and `pair_pure_rotation` name which
pairs, each against its own index, and the artifact note names them in prose.

**Use that to price the fix, and ask the right question.** The question is not
whether the degeneracy is local — it is **whether a clean seed still exists after
the flagged pairs are excluded.** An incremental solver needs exactly one
well-conditioned pair to bootstrap from and then grows by resection.

- **One flagged pair, the rest clean and connected** → the seed is safe. Exclude
  that pair, stay incremental, and name the pair you excluded.
- **Flagged pairs sharing a common frame** → that frame is the problem, not the
  geometry. Keep it out of seed candidacy.
- **Flagged pairs spread across the capture, or covering the only wide-baseline
  pairs** → there is no clean seed to find. Use a solver that does not bootstrap
  from two views.

**What the global solver costs, measured.** Run on the same matches, on captures
reading up to a fifth of pairs planar, it registered every frame and returned
roughly a third fewer points. **Do not read that as evidence against it** — the
failure it prevents is a *confident wrong model*, and a mis-decomposed essential
matrix yields a full, plausible, well-reprojecting cloud. On a degeneracy
question more points is not better and the usual metrics cannot referee. Treat it
as insurance with a known premium and an unmeasured payout.

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
