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
| [branch-comparison-2026-08](branch-comparison-2026-08.md) | 14 captures × 3 detector/matcher branches to a sparse model | `plan/scene_to_pipeline.md` §3b; the swap signals in `judge/swap_or_build.md` |
| [detection-phase-2026-08](detection-phase-2026-08.md) | 5 captures, detection stage driven cold | `plan/detection.md` §3 and §5; the coverage-denominator finding |
| [eth-dense-2026-09](eth-dense-2026-09.md) | 9 corpus captures of built and vegetated sites, raw frames to a dense cloud, scored against laser scans under two protocols | the outdoor reading in `modules/dense_mvs/skills/tuning.md`; "per-view depth is not a deliverable" in its `limitations`; the outdoor row in `plan/dense.md` |
| [reference-pipeline-2026-09](reference-pipeline-2026-09.md) | every corpus capture through one fixed pipeline at full frame count | the reference distribution the health digest scores against; two rung definitions it falsified; what ground truth cannot measure |
| [alternate-legs-2026-09](alternate-legs-2026-09.md) | every module the reference never ran, each as a single-stage swap against it | which rungs track ground truth and which invert; that the reference's collapses were reachable by three different swaps; the preconditions and refusals of the untried modules |
| [agentic-campaign-2026-09](agentic-campaign-2026-09.md) | the whole tool loop driven over every capture at full frame count, planning only from context | the connectivity rule refitted and demoted to a ranking heuristic; coverage as a detector selection effect; the global reconstructor's five-for-five rescue; the reference recipe's two protocol defects; [the recompute check, and why an artifact id cannot tell you two runs agreed](agentic-campaign-2026-09.md#are-these-models-reproducible); [pose accuracy as AUC@5 and AUC@30](agentic-campaign-2026-09.md#pose-accuracy-auc); [what the leg names actually mean](agentic-campaign-2026-09.md#what-the-leg-names-mean); **[one capture solved seven times, where every rung preferred the model that was ninety times further from truth](agentic-campaign-2026-09.md#are-these-models-reproducible)** |
| [dense-batch-2026-09](dense-batch-2026-09.md) | the whole loop to a dense cloud over the standard evaluation set of one studio-rig dataset, scored against reference surface geometry | `plan/dense.md`'s sparse-for-dense section and its measured-questions table; the placement floor and the two scoring bases; `health/ladder.md` on what the error rung cannot see; the intrinsics warning in `plan/optimization.md`; the dense modules' coverage, runtime and hole claims |
| [second-solve-2026-09](second-solve-2026-09.md) | every configuration where points escaped the pose stage, re-solved through refinement under each candidate rule; the held-out verifier on every finished model; the sixteen captures re-run through the current service | the second solve's trigger, width, keep rule and registration tolerance; the retry for refused cameras; the verifier as a veto, and its blind spot |

[CORPUS.txt](CORPUS.txt) lists the captures every quoted range in
`plan/scene_to_pipeline.md` was fitted on. [INDEX.md](INDEX.md) is the precedent
table — a different question ("has a capture like mine been solved before, and
what solved it?"), kept separate because retrieval wants a row you match against
and this tier exists to be cited and not matched. It is keyed on observed capture
kind and carries no measurements at all; each of its rows links back into a
campaign file here for those, which is the one direction between the two tiers
that is safe.

**The alternate legs have run too.** [alternate-legs-2026-09](alternate-legs-2026-09.md)
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

**5. Predictive claims about which branch wins.** The least reliable category in
this corpus, by a wide margin.

## Where the corpus has actually failed

**Predictive branch claims failed six times in one sweep.** The joint-matcher
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
