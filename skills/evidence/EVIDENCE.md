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

[CORPUS.txt](CORPUS.txt) lists the captures every quoted range in
`plan/scene_to_pipeline.md` was fitted on. [INDEX.md](INDEX.md) is the trait-keyed
retrieval table — a different question ("has a capture like mine been solved
before?"), kept separate because retrieval wants a row you match against and this
tier exists to be cited and not matched.

**The reference campaign is not yet here.** When the reference re-run of the corpus
executes, its campaign file lands in this directory carrying the per-scene values
of the seven-rung health profile (defined in [`health/ladder.md`](../health/ladder.md)),
the ground-truth validation columns, and a machine-readable
`reference_profile.yaml` beside it that the run-summary health digest reads.
Until then the digest reports every rung as unevaluable, and says so.

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
- "Registration is a precondition, not a tiebreak" — the single sentence that
  prevented the worst decision of the sweep.

**The pattern to carry:** this corpus is reliable about *what a number means* and
*why a mechanism behaves as it does*, and unreliable about *what will happen if
you swap a module*. Weight it accordingly.

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
The reference campaign above exists in part to close this gap with a record that
is durable this time.
