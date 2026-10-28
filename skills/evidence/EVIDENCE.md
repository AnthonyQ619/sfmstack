# The evidence tier — what was measured, and how much to trust it

This tier is the record. Scene names are kept deliberately, and **only here**, so a
claim stated elsewhere as a scene *property* ("a controlled rig against a lit
backdrop") can be traced back to the capture it was measured on and re-run.

**Cite it; do not plan from it.** A plan for a new capture cannot use a row from a
campaign file — only the reasoning built on the rows, which lives in
[`plan/`](../plan/scene_to_pipeline.md), [`judge/`](../judge/swap_or_build.md) and
[`health/`](../health/ladder.md). Matching your own readings against a row to find
"the capture like mine" is the failure mode this tier is most likely to cause: a
reading that agrees to several digits usually means you are reading your own
capture back. [INDEX.md](INDEX.md) is the file to match against — one row per worked
capture, keyed on observed capture kind, carrying no measurements.

## The campaigns, by topic

One file per campaign. A campaign file holds the raw per-capture tables, the protocol
they were measured under, and a map from each derived claim back to the rows that
support it. Each campaign appears once, under the topic its findings mostly serve;
where a finding serves another topic its row says so. Within a topic the rows are in
date order, and a later campaign narrows or corrects an earlier one more often than it
repeats it — so where two rows seem to disagree, the later one is the one to read first.

### Detection and matching

What produces correspondences, and which source to try first. These campaigns held everything downstream fixed and varied the detector, the matcher or its weights.

| File | What ran | What was derived from it |
| --- | --- | --- |
| [detector-matcher-2026-08](detector-matcher-2026-08.md) | 14 captures × 3 detector/matcher pairs, each to a sparse model | `plan/scene_to_pipeline.md` §3b; the swap signals in `judge/swap_or_build.md` |
| [detection-phase-2026-08](detection-phase-2026-08.md) | 5 captures, detection stage driven cold | `plan/detection.md` §3 and §5; the coverage-denominator finding |
| [detector-free-2026-10](detector-free-2026-10.md) | both detector-free matchers at both weight settings on 7 corpus captures spanning `studio`/`indoor`/`outdoor`, on one stored scene artifact each | RoMa first in `plan/matching.md`; that the zero-of-seventy-five preference for it was already right; that the weights setting discriminates on interior captures only |
| [detector-free-global-2026-10](detector-free-global-2026-10.md) | correspondences carrying no keypoint index through a pairs-consuming reconstructor: the mechanism, four falsified explanations, and twenty-four corpus captures x two sources once a transform supplies the identity | that the route needs an index and what repairs it; that the repair reaches parity on this corpus and wins on traversals; that the cycle rates read the correspondence source and forecast nothing; that track yield is not a proxy for pose accuracy |
| [superglue-weights-2026-10](superglue-weights-2026-10.md) | SuperGlue with each of its two weight sets on nine corpus interiors at ten views, one fixed composition, scored against reference poses | that neither weight set was ahead more often on interiors |

### Tracking

The modules that turn correspondences into tracks, and the preconditions under which they return nothing.

| File | What ran | What was derived from it |
| --- | --- | --- |
| [features-only-tracking-2026-10](features-only-tracking-2026-10.md) | the two trackers that consume features rather than matches, run on 8 corpus captures against the table each capture actually delivered, holding the stored scene and detector fixed | the uniform-resolution precondition and the incumbent-transfer-error crossing in `plan/tracking.md`; `trifocal_samples` as the reading that separates a null verdict from a good one |

### Pose, and choosing a sparse model

Readings that say whether a sparse model's cameras are right, what to deliver when the geometric core comes back short, and what a rebuild by the other route adds. The two-estimator reading runs through most of these in both its forms, rotation and centre; read the rows in date order, since each later one narrows what the earlier one claimed.

| File | What ran | What was derived from it |
| --- | --- | --- |
| [sparse-pose-2026-09](sparse-pose-2026-09.md) | seventy-five captures of five families driven cold to a refined sparse model, ten views each, scored against reference extrinsics as pair-wise AUC, then the verifier run over all seventy-five delivered models | that the verifier's pixel veto misses most wrong models on a short-focal camera and its angular reading does not; the hybrid rule and the frozen fill in `plan/pose.md`; the registration rung's denominator in `health/ladder.md`; that the reading does not transfer to the dense path as that path has so far been run |
| [consensus-2026-09](consensus-2026-09.md) | thirty-five delivered captures of three families, each re-read by two correspondence-free pose estimators run from the scene alone, compared by similarity fit over camera centres | that a delivered model can satisfy every reading built on its own correspondences and still be the outlier; why the reading needs TWO independent estimators and what a single one gets wrong in both directions; the measure-don't-swap rule in `plan/pose.md`; the second-reference rule on `health/bounce.md`'s pose rung; [four candidate cautions that all failed](consensus-2026-09.md#the-false-positive-which-is-not-a-false-reading) |
| [second-solve-2026-09](second-solve-2026-09.md) | every configuration where points escaped the pose stage, re-solved through refinement under each candidate rule; the held-out verifier on every finished model; the sixteen captures re-run through the current service | the second solve's trigger, width, keep rule and registration tolerance; the retry for refused cameras; the verifier as a veto, and its blind spot |
| [view-graph-support-2026-09](view-graph-support-2026-09.md) | the delivered sparse model of all 19 corpus captures of the two dense campaigns, each checked against the correspondences it was built from | `SparseVerification`'s component reading and its band; why that reading uses the all-correspondence residual and not the held-out one; the one reading in `health/ladder.md` that survives behind a global reconstructor |
| [short-core-2026-10](short-core-2026-10.md) | the 75-capture pose batch re-read for every capture whose geometric core came back short, with each available correspondence-free estimator's own model scored beside what shipped | the `registered_fraction` preference in `plan/pose.md` and the split of its fourth row; that row five permitted the swap and twenty captures took the core anyway; three captures promoted to the corpus to carry the rule, the open row and the exception |
| [estimator-outvote-2026-10](estimator-outvote-2026-10.md) | 54 delivered models carrying both correspondence-free estimators, re-read with the two-estimator reading in its centre and rotation forms and scored against reference rotations; every refinement of an estimator model; geometric stereo and the learned dense module on estimator poses on three corpus captures; then every fired model the agents built, both clouds scored against the scan | that the rotation form fires on folds and the centre form on camera position; that refining an estimator model damages it; that stereo on estimator poses does not go one way; that where the rotation form fires the feed-forward cloud wins six of nine and nothing predicts the losses; that a fill keeps a folded core; that a dense score does not certify the poses |
| [global-rebuild-2026-10](global-rebuild-2026-10.md) | seven corpus captures holding an incremental model short of its own capture, each rebuilt by the global reconstructor on that model's own matches and scored against the best incremental model on those same matches; then ten captures densified on both reconstructors' models and scored as-placed and best-fit | that the global reconstructor places frames an incremental model left behind without dropping any of its own, and closes one to three whatever the gap, so it is a last push and not a route from a badly short model; `plan/pose.md` §4's two regimes and the load a shortfall is read at; that the dense gain is small, of either sign, does not follow the drift penalty (Spearman inverted against a pre-registered threshold) and has no agent-side trigger |
| [fill-and-view-graph-2026-10](fill-and-view-graph-2026-10.md) | the fill against the core alone on every ten-view corpus staging whose core came back short with the verifier quiet; agent sessions on the context that added the view-graph rule | three fill cases, too few to decide when to fill; that sessions on wide-spaced captures read the view-graph rule and switched detectors after one classical attempt |

### Dense

Verified stereo and the learned densifier scored against scans; what the sparse model's placement does to a cloud; how far a dense number moves with nothing changed; and the one promoted capture whose dense failure is coverage alone.

| File | What ran | What was derived from it |
| --- | --- | --- |
| [eth-dense-2026-09](eth-dense-2026-09.md) | 9 corpus captures of built and vegetated sites, raw frames to a dense cloud, scored against laser scans under two protocols | the outdoor reading in `modules/dense_mvs/skills/tuning.md`; "per-view depth is not a deliverable" in its `limitations`; the outdoor row in `plan/dense.md` |
| [dtu-dense-promoted-2026-09](dtu-dense-promoted-2026-09.md) | 3 studio-rig captures promoted out of the holdout, each chosen for sitting outside the corpus range on one axis | that the cheap chain does not always register a rig orbit, and in which direction each module choice fails; the conflict rate's real ceiling on clean data; the learned densifier's unreachability; `depth_map_completeness` dilution; the measured stereo runtime and the scaling that actually holds |
| [dense-batch-2026-09](dense-batch-2026-09.md) | the whole loop to a dense cloud over the standard evaluation set of one studio-rig dataset, scored against reference surface geometry | `plan/dense.md`'s sparse-for-dense section and its measured-questions table; the placement floor and the two scoring bases; `health/ladder.md` on what the error rung cannot see; the intrinsics warning in `plan/optimization.md`; the dense modules' coverage, runtime and hole claims |
| [dense-saturated-2026-10](dense-saturated-2026-10.md) | one enclosure capture delivered three times, each sparse model scored under Protocol A, with its cloud and three feed-forward baselines compared on coverage and accuracy | the cheap test in `plan/dense.md` for when a dense number has stopped depending on the sparse stage; that our stereo cloud was the most accurate of four clouds at a third of their coverage |
| [dense-variance-2026-10](dense-variance-2026-10.md) | five corpus captures, two agent sessions each on one context; every delivered dense step replayed twice on its own inputs; every other correct sparse model densified with the delivered settings and read with every reading an agent has; camera centres scored beside rotations | that stereo on a fixed input reproduces itself; that two sessions differ by a third to double on object and enclosure captures and not at all on a rig orbit; that the spread follows placement below 1% of the span; that a rotation share alone does not see placement; that the centre form of the two-estimator reading ranks correct models by placement on object and enclosure captures, and lower reprojection error ranked them the wrong way; that across the two routes on an outdoor object orbit the lower centre form was the worse placement twice, and a quiet global model gave the better cloud on every such capture measured; and that on a site walk a detector-based global chain beat the detector-free one the row names |
| [dense-fixes-2026-10](dense-fixes-2026-10.md) | four dense regressions of the locked-context batch replayed without an agent: kept stereo workspaces re-fused at every fusion setting, kept sparse models densified with one setting or input changed | that off a studio rig orbit a coverage deliverable scored best at fusion 2, past where the doubling rule stops; that on a studio rig orbit the module defaults were at least as good as the delivery anchor; that on a vegetated site walk the detector-free chain's model is what densifies; that `DenseVGGT` on another estimator's poses mis-scales |

### Health readings and bands

Which internal readings track ground truth and which invert, the reference distribution the health digest scores against, and how each module's bands were calibrated as classifiers.

| File | What ran | What was derived from it |
| --- | --- | --- |
| [reference-pipeline-2026-09](reference-pipeline-2026-09.md) | every corpus capture through one fixed pipeline at full frame count | the reference distribution the health digest scores against; two rung definitions it falsified; what ground truth cannot measure |
| [single-stage-swaps-2026-09](single-stage-swaps-2026-09.md) | every module the reference never ran, each as a single-stage swap against it | which rungs track ground truth and which invert; that the reference's collapses were reachable by three different swaps; the preconditions and refusals of the untried modules |
| [band-calibration-2026-10](band-calibration-2026-10.md) | every healthy band in every module scored as a classifier against delivered outcomes, per reading rather than per capture | the band taxonomy in `health/bands.md`; thirteen band changes across nine modules; the retirement of two spatial readings scored on delivered models; that a near-perfect reconstruction still fires ten alarms |
| [triage-bands-2026-10](triage-bands-2026-10.md) | every stored SceneTriage reading on the twenty captures carrying reference geometry, each appearance band scored as a classifier of a poor delivery against a 40% base rate, split by pairing and then within capture family | that `combined_change` discriminates inside each family that holds both classes and keeps its 0.12 ceiling, which works BECAUSE it sits below the population median; the retirement of `color_shift`, whose pooled lead was an artifact of unbalanced families, and of `exposure_shift`, which fired almost only on good deliveries; that under `pairing: all` precision falls to the base rate |

### Which modules win, and repeat noise

How much module choice matters, by capture kind, and the repeat magnitudes behind every claim that compares two runs — including which parts of this stack are reproducible and which are not.

| File | What ran | What was derived from it |
| --- | --- | --- |
| [sparse-compositions-2026-10](sparse-compositions-2026-10.md) | eleven compositions assembled from the registry, each run end-to-end on all twenty-four corpus captures at full coverage, one metric throughout and threads pinned | that how much your module choices matter is a property of the capture and which modules win is not; that the boundary is a single controlled subject against a traversal and NOT benchmark against visual-inertial; the per-module counts of what can return nothing; the repeat magnitudes behind every claim about comparing two runs; that neither correspondence-free estimator's own model is ahead of the other's across the corpus |

### The loop end to end: agent batches

The whole tool loop driven over captures, planning only from context: what the agents delivered, what they rejected, which context lines they followed or missed, and the validation batches on the frozen context.

| File | What ran | What was derived from it |
| --- | --- | --- |
| [agentic-campaign-2026-09](agentic-campaign-2026-09.md) | the whole tool loop driven over every capture at full frame count, planning only from context | the connectivity rule refitted and demoted to a ranking heuristic; coverage as a detector selection effect; the reference recipe's two protocol defects; [the recompute check, and why an artifact id cannot tell you two runs agreed](agentic-campaign-2026-09.md#are-these-models-reproducible); [pose accuracy as AUC@5 and AUC@30](agentic-campaign-2026-09.md#pose-accuracy-auc); [what the composition names actually mean](agentic-campaign-2026-09.md#what-the-composition-names-mean); **[one capture solved seven times, where every rung preferred the model that was ninety times further from truth](agentic-campaign-2026-09.md#are-these-models-reproducible)** |
| [agent-controls-2026-10](agent-controls-2026-10.md) | the whole tool loop on seven corpus captures at ten views, strict context, each delivery and every model it rejected scored against the best a registry module has reached; and one capture's global-route shortfall isolated offline | that a complete detector-free graph is not evidence of overlap and its certainty cannot say so; the veto's domain, which an estimator-only model is outside; that the two joint matchers trade places; that classical detection and matching fail on sparse captures; that a placed camera is not a supported one; the single-fill null; the worst-camera reading's blind spot; the `filter_threshold` step |
| [agent-rerun-2026-10](agent-rerun-2026-10.md) | the ten-view sparse and full-capture dense agent batches run again on the revised context, strict context, one agent per capture, scored against reference poses and the benchmark clouds; one capture twice on the same context | that skipping the two-estimator reading let a fold through that every comparison on the models' own evidence passed, and taking it caught the fold; that on the centre form alone a rebuilt geometric model was the right one; that the ladder's rungs did not choose between the two estimators' models; that a fill's agreement gate does not read where a filled cluster sits relative to the core; that a classical detector's view graph broke first on a wide-spaced subset, and the matcher's readings showed it |
| [final-validation-2026-10](final-validation-2026-10.md) | the ten-view sparse and full-capture dense agent batches on the frozen context, two sessions per capture, every model read by reference and by the two-estimator reading | that on a site walk a threshold rebuild did not clear the centre form while the other reconstruction route placed the cameras; that the centre-form comparison chose the lowest candidate in every session that had more than one; the control rows with their two-session spread; that on a rig orbit the as-placed score moves with camera placement by up to a quarter while the surface does not, so rig-orbit clouds compare on the best-fit score; that on a sparse deliverable the lowest centre-form candidate was not the better one |

[CORPUS.txt](CORPUS.txt) lists the captures this corpus has already been shown the
answer to: the benchmark captures every quoted range in `plan/scene_to_pipeline.md`
was fitted on, and — listed separately at its foot — captures promoted since to carry
a worked lesson in a `plan/` file. `reference_profile.yaml` beside it is the
machine-readable distribution the run-summary health digest scores a new model
against, rebuilt from the reference campaign's own table.

---

# How to read this corpus — the reliability ladder

When two pieces of this corpus disagree with each other, or with your own reading,
this is which to believe. The pattern was set by a seventeen-capture sweep that
falsified six claims written down as measured, and every campaign since has kept to it.

**1. A diagnostic that fired on your run.** Computed from your artifact by the module
that made it. It can be badly *worded* — several were — but it is not describing
someone else's capture.

**2. A metric's `meaning`, and the type contract.** Definitional. `two_view_fraction`
is the share of points seen in exactly two views whatever your scene is. These have
been wrong here only when a producer's *implementation* disagreed with the definition,
which is a code defect and now has a cross-check.

**3. Mechanism claims — "why" rather than "how much".** "A two-view point is exactly
determined, so its residual is near zero by construction." "A homography and a
fundamental matrix agree on a plane, so triangulation is degenerate." These survived
every sweep intact. They are geometry, not statistics on fourteen scenes.

**4. Bands and ranges.** Trustworthy as *descriptions of what has been seen*,
unreliable as thresholds. Every range was fitted under one protocol — twelve-frame head
samples at a fixed working resolution — and per-frame appearance readings transfer to a
full capture while adjacent-motion readings do not, and anything denominated in *pairs*
does not at all, because pairs grow quadratically with frames.

**5. Predictive claims about which module wins.** The least reliable category in this
corpus, by a wide margin. The joint-matcher swap rule, tagged as measured across
fourteen captures, had counter-examples in four currencies; a detector-recovery claim
was contradicted on eight captures; a remedy ladder for a divergence error failed on
seven. The common shape: each was fitted by comparing two configurations on a small
corpus, with at least one of them at a *default* setting of the dial that decides the
comparison. **Treat any "X beats Y when the scene is Z" claim as a reason to run the
comparison, never as a substitute for running it.**

**What has held up** is the other end of the ladder: mechanism and definitional claims,
and the corrections made after measurement. "Bundle adjustment erases the accuracy half
of a triangulator difference" reproduced with the ranking flipping post-BA exactly as
described; `converged` being bookkeeping reproduced on two optimizers; the documented
cross-check that a bundle adjuster's entry error reproduces its producer's published
mean is exact to four decimals for the adjuster that deletes nothing and fails
systematically for the one that does; "registration is a precondition, not a tiebreak"
was confirmed against ground truth, where the models that abandoned most of their
capture scored as well on pose error as fully-registered ones because each kept the one
surviving pair right. An accuracy number computed over what a model kept cannot see
what it discarded.

**A version number did not pin the software that produced a row.** A module's image is
tagged with its manifest version, and the artifact cache keys on that version and never
on the adapter source — so an image built before a code edit keeps its tag and keeps
running the old code. When the reference campaign was first attempted, fifteen of
twenty-eight modules were running images that no longer matched their source. A row is
evidence about the code that ran, which is not automatically the code you can read:
`tools/image_drift.py` performs the check, the docker suite fails when an image drifts,
and campaigns that predate the check are worth less than their numbers suggest. The
seventeen-capture sweep itself — 645 module runs, 108 backtracks — is the evidence
behind most of the corrections across `plan/`, `judge/` and `health/`, and its
transcripts were not preserved: its claims are traceable to their scope and not to rows.

## What a single row is worth

Every entry in this tier is a number produced by a run, and a run is not guaranteed to
repeat. The repeat magnitudes are now measured rather than assumed, and they are the
first thing to read before comparing any two rows:

- A fully pinned geometric chain repeats exactly. An unpinned incremental solve does not
  — a multithreaded bundle adjustment inside the loop sums residuals in a different
  order each run and feeds the difference into its next decision — and one learned
  estimator moved by 0.237 on the pose metric between two draws while the other was
  bit-identical ([sparse-compositions-2026-10 §4](sparse-compositions-2026-10.md#4-the-repeat-measurements--and-why-the-pinning-is-load-bearing)).
  An artifact id derived from a recipe cannot show two runs agreed
  ([agentic-campaign-2026-09](agentic-campaign-2026-09.md#are-these-models-reproducible-mostly-and-the-cache-was-hiding-the-rest)).
- One capture solved seven times from one recipe produced models an order of magnitude
  apart against reference geometry, and the badly wrong ones scored *better* on every
  internal rung than the correct ones. A row that rests on one capture's one run is the
  weakest evidence here, and it is the kind most of the older rows are.
- Stereo on a fixed input reproduces itself, for both dense families. Two agent sessions
  on one context do not: they differed by a third to double on object and enclosure
  captures, by 0.12 F1 on a built interior, and not at all on a rig orbit
  ([dense-variance-2026-10](dense-variance-2026-10.md#finding-2--two-sessions-on-one-context-differ-by-a-third-to-double)).

## Reading a dense comparison

**A dense difference between two agent sessions is a context effect only beyond the
session spread** above. A comparison between two clouds built from fixed inputs in one
session is not subject to it; its noise is the dense module's, which is nil for both
families. And a rotation share alone does not certify a model: read camera centres
beside it ([finding 4](dense-variance-2026-10.md#finding-4--the-rotation-share-does-not-see-placement)).
Where two sessions delivered different sparse models, compare their centre-form readings
before reading the clouds as a context effect: on object and enclosure captures the
lower reading gave the better cloud within one route
([finding 5](dense-variance-2026-10.md#finding-5--the-centre-form-of-the-two-estimator-reading-ranks-placement-below-its-fire-level));
across the incremental and global routes on an outdoor object orbit it did not
([finding 7](dense-variance-2026-10.md#finding-7--across-the-two-routes-on-an-outdoor-object-orbit-the-lower-centre-form-was-the-worse-placement)).

## A standing caution about recall

`sfm_plan_brief` reports `in_planning_corpus`. If it says your capture is a member,
then locating your readings inside these ranges is **recall, not confirmation** — the
ranges were fitted partly on this capture. Several readers disclosed this correctly and
it changed how much their agreement was worth.
