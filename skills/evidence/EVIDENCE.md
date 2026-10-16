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
capture back.

## The campaigns

One file per campaign. A campaign file holds the raw per-capture tables, the
protocol they were measured under, and a map from each derived claim back to the
rows that support it.

| File | What ran | What was derived from it |
| --- | --- | --- |
| [detector-matcher-2026-08](detector-matcher-2026-08.md) | 14 captures × 3 detector/matcher pairs, each to a sparse model | `plan/scene_to_pipeline.md` §3b; the swap signals in `judge/swap_or_build.md` |
| [detection-phase-2026-08](detection-phase-2026-08.md) | 5 captures, detection stage driven cold | `plan/detection.md` §3 and §5; the coverage-denominator finding |
| [eth-dense-2026-09](eth-dense-2026-09.md) | 9 corpus captures of built and vegetated sites, raw frames to a dense cloud, scored against laser scans under two protocols | the outdoor reading in `modules/dense_mvs/skills/tuning.md`; "per-view depth is not a deliverable" in its `limitations`; the outdoor row in `plan/dense.md` |
| [dtu-dense-promoted-2026-09](dtu-dense-promoted-2026-09.md) | 3 studio-rig captures promoted out of the holdout, each chosen for sitting outside the corpus range on one axis | that the cheap chain does not always register a rig orbit, and in which direction each module choice fails; the conflict rate's real ceiling on clean data; the learned densifier's unreachability; `depth_map_completeness` dilution; the measured stereo runtime and the scaling that actually holds |
| [reference-pipeline-2026-09](reference-pipeline-2026-09.md) | every corpus capture through one fixed pipeline at full frame count | the reference distribution the health digest scores against; two rung definitions it falsified; what ground truth cannot measure |
| [single-stage-swaps-2026-09](single-stage-swaps-2026-09.md) | every module the reference never ran, each as a single-stage swap against it | which rungs track ground truth and which invert; that the reference's collapses were reachable by three different swaps; the preconditions and refusals of the untried modules |
| [agentic-campaign-2026-09](agentic-campaign-2026-09.md) | the whole tool loop driven over every capture at full frame count, planning only from context | the connectivity rule refitted and demoted to a ranking heuristic; coverage as a detector selection effect; the global reconstructor's five-for-five rescue; the reference recipe's two protocol defects; [the recompute check, and why an artifact id cannot tell you two runs agreed](agentic-campaign-2026-09.md#are-these-models-reproducible); [pose accuracy as AUC@5 and AUC@30](agentic-campaign-2026-09.md#pose-accuracy-auc); [what the composition names actually mean](agentic-campaign-2026-09.md#what-the-composition-names-mean); **[one capture solved seven times, where every rung preferred the model that was ninety times further from truth](agentic-campaign-2026-09.md#are-these-models-reproducible)** |
| [dense-batch-2026-09](dense-batch-2026-09.md) | the whole loop to a dense cloud over the standard evaluation set of one studio-rig dataset, scored against reference surface geometry | `plan/dense.md`'s sparse-for-dense section and its measured-questions table; the placement floor and the two scoring bases; `health/ladder.md` on what the error rung cannot see; the intrinsics warning in `plan/optimization.md`; the dense modules' coverage, runtime and hole claims |
| [second-solve-2026-09](second-solve-2026-09.md) | every configuration where points escaped the pose stage, re-solved through refinement under each candidate rule; the held-out verifier on every finished model; the sixteen captures re-run through the current service | the second solve's trigger, width, keep rule and registration tolerance; the retry for refused cameras; the verifier as a veto, and its blind spot |
| [view-graph-support-2026-09](view-graph-support-2026-09.md) | the delivered sparse model of all 19 corpus captures of the two dense campaigns, each checked against the correspondences it was built from | `SparseVerification`'s component reading and its band; why that reading uses the all-correspondence residual and not the held-out one; the one reading in `health/ladder.md` that survives behind a global reconstructor |
| [sparse-pose-2026-09](sparse-pose-2026-09.md) | seventy-five captures of five families driven cold to a refined sparse model, ten views each, scored against reference extrinsics as pair-wise AUC, then the verifier run over all seventy-five delivered models | that the verifier's pixel veto misses most wrong models on a short-focal camera and its angular reading does not; the hybrid rule and the frozen fill in `plan/pose.md`; the registration rung's denominator in `health/ladder.md`; that the reading does not transfer to the dense path as that path has so far been run |
| [consensus-2026-09](consensus-2026-09.md) | thirty-five delivered captures of three families, each re-read by two correspondence-free pose estimators run from the scene alone, compared by similarity fit over camera centres | that a delivered model can satisfy every reading built on its own correspondences and still be the outlier; why the reading needs TWO independent estimators and what a single one gets wrong in both directions; the measure-don't-swap rule in `plan/pose.md`; the second-reference rule on `health/bounce.md`'s pose rung; [four candidate cautions that all failed](consensus-2026-09.md#the-false-positive-which-is-not-a-false-reading) |
| [short-core-2026-10](short-core-2026-10.md) | the 75-capture pose batch re-read for every capture whose geometric core came back short, with each available correspondence-free estimator's own model scored beside what shipped | the `registered_fraction` preference in `plan/pose.md` and the split of its fourth row; that row five permitted the swap and twenty captures took the core anyway; three captures promoted to the corpus to carry the rule, the open row and the exception |
| [detector-free-2026-10](detector-free-2026-10.md) | both detector-free matchers at both weight settings on 7 corpus captures spanning `studio`/`indoor`/`outdoor`, on one stored scene artifact each | RoMa first in `plan/matching.md`; that the zero-of-seventy-five preference for it was already right; that the weights setting discriminates on interior captures only |
| [sparse-compositions-2026-10](sparse-compositions-2026-10.md) | eleven compositions assembled from the registry, each run end-to-end on all twenty-four corpus captures at full coverage, one metric throughout and threads pinned | that how much your module choices matter is a property of the capture and which modules win is not; that the boundary is a single controlled subject against a traversal and NOT benchmark against visual-inertial; the per-module counts of what can return nothing; the repeat magnitudes behind every claim about comparing two runs; that neither correspondence-free estimator's own model is ahead of the other's across the corpus |
| [detector-free-global-2026-10](detector-free-global-2026-10.md) | correspondences carrying no keypoint index through a pairs-consuming reconstructor: the mechanism, four falsified explanations, and twenty-four corpus captures x two sources once a transform supplies the identity | that the route needs an index and what repairs it; that the repair reaches parity on this corpus and wins on traversals; that the cycle rates read the correspondence source and forecast nothing; that track yield is not a proxy for pose accuracy |
| [agent-controls-2026-10](agent-controls-2026-10.md) | the whole tool loop on seven corpus captures at ten views, strict context, each delivery and every model it rejected scored against the best a registry module has reached; and one capture's global-route shortfall isolated offline | that a complete detector-free graph is not evidence of overlap and its certainty cannot say so; the veto's domain, which an estimator-only model is outside; that the two joint matchers trade places; that classical detection and matching fail on sparse captures; that a placed camera is not a supported one; the single-fill null; the worst-camera reading's blind spot; the `filter_threshold` step |
| [estimator-outvote-2026-10](estimator-outvote-2026-10.md) | 54 delivered models carrying both correspondence-free estimators, re-read with the two-estimator reading in its centre and rotation forms and scored against reference rotations; every refinement of an estimator model; geometric stereo and the learned dense module on estimator poses on three corpus captures; then every fired model the agents built, both clouds scored against the scan | that the rotation form fires on folds and the centre form on camera position; that refining an estimator model damages it; that stereo on estimator poses does not go one way; that where the rotation form fires the feed-forward cloud wins six of nine and nothing predicts the losses; that a fill keeps a folded core; that a dense score does not certify the poses |
| [agent-rerun-2026-10](agent-rerun-2026-10.md) | the ten-view sparse and full-capture dense agent batches run again on the revised context, strict context, one agent per capture, scored against reference poses and the benchmark clouds; one capture twice on the same context | that skipping the two-estimator reading let a fold through that every comparison on the models' own evidence passed, and taking it caught the fold; that on the centre form alone a rebuilt geometric model was the right one; that the ladder's rungs did not choose between the two estimators' models; that a fill's agreement gate does not read where a filled cluster sits relative to the core; that a classical detector's view graph broke first on a wide-spaced subset, and the matcher's readings showed it |
| [dense-variance-2026-10](dense-variance-2026-10.md) | five corpus captures, two agent sessions each on one context; every delivered dense step replayed twice on its own inputs; every other correct sparse model densified with the delivered settings and read with every reading an agent has; camera centres scored beside rotations | that stereo on a fixed input reproduces itself; that two sessions differ by a third to double on object and enclosure captures and not at all on a rig orbit; that the spread follows placement below 1% of the span; that a rotation share alone does not see placement; that the centre form of the two-estimator reading ranks correct models by placement on object and enclosure captures, and lower reprojection error ranked them the wrong way |
| [superglue-weights-2026-10](superglue-weights-2026-10.md) | SuperGlue with each of its two weight sets on nine corpus interiors at ten views, one fixed composition, scored against reference poses | that neither weight set was ahead more often on interiors |
| [fill-and-view-graph-2026-10](fill-and-view-graph-2026-10.md) | the fill against the core alone on every ten-view corpus staging whose core came back short with the verifier quiet; agent sessions on the context that added the view-graph rule | three fill cases, too few to decide when to fill; that sessions on wide-spaced captures read the view-graph rule and switched detectors after one classical attempt |
| [dense-saturated-2026-10](dense-saturated-2026-10.md) | one enclosure capture delivered three times, each sparse model scored under Protocol A, with its cloud and three feed-forward baselines compared on coverage and accuracy | the cheap test in `plan/dense.md` for when a dense number has stopped depending on the sparse stage; that our stereo cloud was the most accurate of four clouds at a third of their coverage |
| [band-calibration-2026-10](band-calibration-2026-10.md) | every healthy band in every module scored as a classifier against delivered outcomes, per reading rather than per capture | the band taxonomy in `health/bands.md`; thirteen band changes across nine modules; the retirement of two spatial readings scored on delivered models; that a near-perfect reconstruction still fires ten alarms |
| [triage-bands-2026-10](triage-bands-2026-10.md) | every stored SceneTriage reading on the twenty captures carrying reference geometry, each appearance band scored as a classifier of a poor delivery against a 40% base rate, split by pairing and then within capture family | that `combined_change` discriminates inside each family that holds both classes and keeps its 0.12 ceiling, which works BECAUSE it sits below the population median; the retirement of `color_shift`, whose pooled lead was an artifact of unbalanced families, and of `exposure_shift`, which fired almost only on good deliveries; that under `pairing: all` precision falls to the base rate |
| [global-rebuild-2026-10](global-rebuild-2026-10.md) | seven corpus captures holding an incremental model short of its own capture, each rebuilt by the global reconstructor on that model's own matches and scored against the best incremental model on those same matches; then ten captures densified on both reconstructors' models and scored as-placed and best-fit | that the global reconstructor places frames an incremental model left behind without dropping any of its own, and closes one to three whatever the gap, so it is a last push and not a route from a badly short model; `plan/pose.md` §4's two regimes and the load a shortfall is read at; that the dense gain is small, of either sign, does not follow the drift penalty (Spearman inverted against a pre-registered threshold) and has no agent-side trigger |
| [features-only-tracking-2026-10](features-only-tracking-2026-10.md) | the two trackers that consume features rather than matches, run on 8 corpus captures against the table each capture actually delivered, holding the stored scene and detector fixed | the uniform-resolution precondition and the incumbent-transfer-error crossing in `plan/tracking.md`; `trifocal_samples` as the reading that separates a null verdict from a good one |

[CORPUS.txt](CORPUS.txt) lists the captures this corpus has already been shown the
answer to: the benchmark captures every quoted range in `plan/scene_to_pipeline.md`
was fitted on, and — listed separately at its foot — captures promoted since to carry
a worked lesson in a `plan/` file. [INDEX.md](INDEX.md) is the precedent
table — a different question ("has a capture like mine been solved before, and
what solved it?"), kept separate because retrieval wants a row you match against
and this tier exists to be cited and not matched. It is keyed on observed capture
kind and carries no measurements at all; each of its rows links back into a
campaign file here for those, which is the one direction between the two tiers
that is safe.

**The single-stage swaps have run too.** [single-stage-swaps-2026-09](single-stage-swaps-2026-09.md)
is where a rung stops being a designed reading: it produced models of one capture
that register the same images, which is the only condition under which
ground-truth accuracy can rank two models, and it scored every rung on them. Read
it before quoting a rung as evidence of anything: over seventeen such
comparisons, two rungs ranked every one correctly and three — error,
conditioning and composition — landed at 10, 9 and 6, which is chance or worse.

**The reference campaign has run.** [reference-pipeline-2026-09](reference-pipeline-2026-09.md)
carries the per-scene values of the health profile (defined in
[`health/ladder.md`](../health/ladder.md)) with ground truth beside them, and
`reference_profile.yaml` next to it is the machine-readable distribution the
run-summary health digest scores a new model against. Two rung definitions did
not survive their own first reading and were corrected; the campaign file says
which and why.

---

# How to read this corpus — the reliability ladder

When two pieces of this corpus disagree with each other, or with your own reading,
this is which to believe. It exists because a seventeen-capture sweep falsified six
claims that were written down as measured, and the ones that survived and the ones
that failed form a pattern worth stating.

**1. A diagnostic that fired on your run.** It was computed from your artifact by
the module that made it. It can be badly *worded* — several were — but it is not
describing someone else's capture.

**2. A metric's `meaning`, and the type contract.** Definitional. `two_view_fraction`
is the share of points seen in exactly two views whatever your scene is. These
have been wrong here only when a producer's *implementation* disagreed with the
definition, which is a code defect and now has a cross-check.

**3. Mechanism claims — "why" rather than "how much".** "A two-view point is
exactly determined, so its residual is near zero by construction." "A homography
and a fundamental matrix agree on a plane, so triangulation is degenerate."
These survived the sweep intact. They are geometry, not statistics on fourteen
scenes.

**4. Bands and ranges.** Trustworthy as *descriptions of what has been seen*,
unreliable as thresholds.

**5. Predictive claims about which module wins.** The least reliable category in
this corpus, by a wide margin.

## Where the corpus has actually failed

**Predictive module claims failed six times in one sweep.** The joint-matcher
swap rule — tagged as measured across fourteen captures — has counter-examples in
four different currencies, at least two on captures the original fourteen
included. A detector-recovery claim was contradicted on eight. A remedy ladder
for a divergence error failed on seven, with one reader exhausting every rung.

**The common shape:** each was fitted by comparing two configurations on a small
corpus, and at least one of them appears to have been compared at a *default*
setting of the dial that decides the comparison. A prediction produced that way
is a statement about the experiment, not about the modules.

**So: treat any "X beats Y when the scene is Z" claim as a reason to run the
comparison, never as a substitute for running it.** The A/B is cheap relative to
being wrong, and it has disagreed with the prediction every time it was carried
to a model.

**Bands did not survive leaving the corpus's protocol.** Every range here was
fitted on twelve-frame head samples at a fixed working resolution. Per-frame
appearance readings transfer to a full capture; adjacent-motion readings do not,
because "adjacent" means something different; anything denominated in *pairs*
does not at all, because pairs grow quadratically with frames.

**A version number did not pin the software that produced a row.** A module's
image is tagged with its manifest version, and the artifact cache keys on that
version and never on the adapter source — so an image built before a code edit
keeps its tag, keeps satisfying the cache, and keeps running the old code while
every skill file describes the new one. Measured when the reference campaign was
first attempted: **fifteen of twenty-eight modules were running images that no
longer matched their source**, one of them missing a guard its own repository
docstring describes, which killed a whole exhaustive matching run on the one
image pair it could not solve.

The consequence for reading this tier: **a row is evidence about the code that
ran, which is not automatically the code you can read.** Any campaign recorded
here states the check; `tools/image_drift.py` performs it, and the docker suite
fails when an image drifts. A campaign run without that check is worth less than
its numbers suggest, and older campaigns here predate the check.

## Where it held up

The claims that survived contact with seventeen full captures were **mechanism
claims and definitional ones**, and the corrections made after measurement:

- "Bundle adjustment erases the accuracy half of a triangulator difference" —
  reproduced, with the ranking flipping post-BA exactly as described.
- The yield ceiling on an all-view triangulator — predicted 1.4% headroom,
  delivered 0.2%.
- `converged` being bookkeeping — reproduced to four decimal places.
- A producer's published mean matching a bundle adjuster's independent reading of
  the same artifact — matched twice.
- `converged` being bookkeeping, again on a **second** optimizer: it read 0 on
  every capture in the corpus while the window error it was solving fell by
  between an eighth and a half, every time. A flag that is never 1 on a module
  that always improves is not reporting on the model.
- The documented cross-check that a bundle adjuster's entry error should
  reproduce its producer's published mean — run for the first time, and exact to
  four decimals on every capture for the adjuster that deletes nothing. It is a
  working check, not a slogan; the adjuster that *does* delete fails it
  systematically and in the direction its own filter predicts.
- The tracker reading that exposes a predictive tracker's real quality —
  reproduced on a capture where every confidence and consistency reading was the
  best in the corpus and the model came out empty.
- "Registration is a precondition, not a tiebreak" — the single sentence that
  prevented the worst decision of the sweep, and since confirmed **against ground
  truth**: in the reference campaign the models that abandoned most of their
  capture scored at least as well on true pose error as every fully-registered
  reconstruction, because each kept two images and got the one surviving pair
  right. An accuracy number computed over what a model kept cannot see what it
  discarded.

**The pattern to carry:** this corpus is reliable about *what a number means* and
*why a mechanism behaves as it does*, and unreliable about *what will happen if
you swap a module*. Weight it accordingly.

**One caution that sits above all of the above, because it limits what a single
reading is worth at all.** Every entry in this tier is a number produced by a
run, and a run is not guaranteed to repeat. One capture solved seven times from
the same recipe produced models an order of magnitude apart in error against
reference geometry, and the badly wrong ones scored *better* on every internal
rung than the correct ones. So a row here is one draw from a process that
sometimes has more than one answer, not a measurement of a pipeline. Where a
claim rests on a single capture's single run, that is the weakest kind of
evidence in this corpus, and it is the kind most of these rows are. Re-running
is the only way to find out which rows are which, and it has been done for two
captures out of sixteen.

## Reading a dense comparison

**A dense difference between two agent sessions is a context effect only beyond the
session spread.** With nothing changed, two sessions on one context differed by a third
to double on three object and enclosure captures, by 0.12 F1 on a built interior, and not
at all on a rig orbit ([dense-variance-2026-10](dense-variance-2026-10.md#finding-2--two-sessions-on-one-context-differ-by-a-third-to-double)).
A comparison between two clouds built from fixed inputs in one session is not subject to
this; its noise is the dense module's, which is nil for both families. And a rotation share
alone does not certify a model: read camera centres beside it
([finding 4](dense-variance-2026-10.md#finding-4--the-rotation-share-does-not-see-placement)).
Where two sessions delivered different sparse models, compare their centre-form readings
before reading the clouds as a context effect: on object and enclosure captures the lower
reading gave the better cloud
([finding 5](dense-variance-2026-10.md#finding-5--the-centre-form-of-the-two-estimator-reading-ranks-placement-below-its-fire-level)).

## A standing caution about recall

`sfm_plan_brief` reports `in_planning_corpus`. If it says your capture is a
member, then locating your readings inside these ranges is **recall, not
confirmation** — the ranges were fitted partly on this capture. Several readers
disclosed this correctly and it changed how much their agreement was worth.

---

## Not yet recorded here

A seventeen-capture sweep driven to a sparse reconstruction in full — 645 module
runs, 108 backtracks — is the evidence behind most of the corrections made across
`plan/`, `judge/`, `health/` and the module skills. **Its raw per-capture record
is not in this tier**; its transcripts were not preserved. The captures it ran on
are listed in [CORPUS.txt](CORPUS.txt), which is what pins the scope of every
range in `plan/scene_to_pipeline.md`, but the per-run numbers are not citable.

[reference-pipeline-2026-09](reference-pipeline-2026-09.md) closes part of that
gap: it is the same corpus re-run durably, with per-capture rows and the image
digests that produced them. It does **not** reproduce the sweep — one fixed
pipeline is not seventeen agent-driven sessions with their backtracks — so the
sweep's own claims remain traceable to their scope and not to their rows.
