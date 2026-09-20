---
name: context-structure-design
description: How written context is organised so an agent can select and tune SfM modules from retrieval alone — the layout, what each file is for, what causes it to be read, and what is measured about whether that works.
status: current as of 2026-09-07; describes exactly what is on disk
audience: for review and critique
---

# The context structure

## 0. What this document is

`sfmstack` is a structure-from-motion framework in which every module is an
independent container, artifacts flow between them as typed directories, and **an
agent drives the pipeline over an MCP tool surface using only written context.**
The agent does not read the source. It cannot open `adapter.py`, it has no prior
about which matcher is fashionable, and nothing in its instructions tells it what a
good reprojection error is. Everything it knows, it fetched.

That makes the written context a component of the system rather than
documentation about it, and it can therefore be wrong in the way a component is
wrong. The goal is a body of context from which an agent can **select and tune
modules for a capture it has never seen**, including captures outside the corpus
the context was written on.

This document describes the current layout, says what each file is for, says
**what causes it to be read**, and reports what has been measured about whether
that works. It is written to be argued with. §8 lists the places I think the
design is weakest. (The design history — what the tree looked like before this
organisation and why it changed — is in
[`docs/design/knowledge-system.md`](design/knowledge-system.md); nothing below
depends on it.)

---

## 1. The constraint that shapes everything

Context is **retrieved, not resident**. Exactly one file is always in the agent's
window (`skills/SKILLS.md`, ~9 KB). Everything else costs a tool call, and the
agent decides whether to spend it, without having seen the contents.

Two consequences run through the whole design:

1. **A file that is never fetched does not exist.** Correctness is necessary and
   nowhere near sufficient. A perfectly written page that nothing causes anyone to
   open is indistinguishable from an empty file.
2. **The decision to fetch is made from a name and a one-line description.** So
   files must be *individuated*: a reader must be able to tell from outside which
   one holds their answer. Two files that could plausibly hold the same fact are
   worse than one longer file, because the reader either fetches both or guesses.

The whole layout below is a response to those two facts. Whether it is a good
response is the thing to critique.

---

## 2. The layout

The global tier is organised by **the moment the reader is standing in** — the
one thing a reader always knows about themselves, even before they can name
their problem:

```
skills/
  SKILLS.md              ~9 KB   ALWAYS RESIDENT. The index; routes by moment.

  plan/                  ~185 KB  BEFORE ANYTHING RUNS
    scene_to_pipeline.md   how to read a capture's measured numbers into a plan (74 KB)
    detection.md … dense.md  one per stage: which member, for this scene

  judge/                 ~20 KB  A RUN FINISHED, NUMBERS IN HAND
    swap_or_build.md       tuning stopped paying — is the module wrong, or is there no module?
    tradeoffs.md           what the next attempt costs, incl. a run that dies partway

  health/                ~22 KB  A SPARSE MODEL EXISTS
    ladder.md              the constraint ladder + the SEVEN-RUNG HEALTH PROFILE
    smells.md              results that look fine numerically and are wrong
    bounce.md              weakest rung low AND immobile across attempts → BUILD

  evidence/                      CHECKING OR CITING A CLAIM (scene names live here, only here)
    EVIDENCE.md            campaign index + the reliability ladder
    <campaign>.md          one file per campaign, raw per-capture tables
    reference_profile.yaml GENERATED: the distribution the health digest scores against
    INDEX.md               precedent table keyed on OBSERVED capture kind, one
                           row per worked capture, no measurements — see §7.4
    CORPUS.txt             the captures every quoted range was fitted on

  distill/               ~24 KB
    SKILL.md               how to write new context; §9 is the recording protocol
                           [THE LOOP HAS NEVER RUN — see §7]

modules/<name>/
  module.yaml                    THE MANIFEST. Params, metrics, diagnostics, types.
  skills/
    SKILL.md                     router + orientation + provenance line
                                 (inlined into every describe call)
    tuning.md                    how to move this module's numbers, and which
                                 bands rest on nothing
    limitations.md               what this module cannot do
    artifact.md                  the payload it writes
    sources.md                   cite-only citation table: claim → what it rests on
```

**Scale.** 28 modules across 8 stages (source 1, analysis 3, detection 4, matching
6, tracking 3, pose 2, sparse 5, optimization 2, dense 2), declaring 238
parameters, 329 metrics and 126 diagnostics between them. 141 per-module skill
files: five per module, plus one extra (`SceneDescription/rubric.md`, §4). By
volume the module tier is about 625 KB and the global tier about 270 KB.

This document is reachable through `sfm_workflow_skill("context-structure-design")`
like any other document beside `skills/`.

**What is deliberately not in `skills/`.** `docs/` sits beside it, and since 2026-09-20
so does `harness/`, the experiment driver. The line is whether an agent may be *handed*
the document: everything under `skills/` is retrievable through `sfm_workflow_skill`,
and that resolver reads `skills_dir / topic` directly, so anything placed there is
reachable whether or not it was meant to be. The harness is operator tooling plus
`PROCEDURE.md`, which `launch.py` injects as the agent's prompt rather than serving on
request. Keeping it out also keeps a second rule enforceable: every capture named in
the harness is a corpus member, because a holdout named in an example is a holdout
written into the context. See [`harness/README.md`](../harness/README.md).

**Nineteen MCP tools** reach the context, of which four are the ones that matter
here: `sfm_describe_module`, `sfm_module_skill`, `sfm_workflow_skill`,
`sfm_plan_brief`. The resolver takes a path-shaped topic (`plan/tracking`,
`evidence/EVIDENCE`) or a bare name searched across the four moment tiers
(`ladder` finds `health/ladder.md`); superseded topic names from before this
organisation still resolve, silently, to the file's current home — the response
reports only the current name, so nothing advertises names that no longer exist.

---

## 3. What each file is for

### 3.1 The global tier

| File | The moment | The question it answers | Not this |
| --- | --- | --- | --- |
| `SKILLS.md` | always resident | "What exists, and where do I stand?" | Any actual guidance. It is an index that routes by moment. |
| `plan/scene_to_pipeline.md` | before anything runs | "I have numbers off this capture. What do they imply for my plan?" | A decision. It translates measurements into the vocabulary the stage files are written in. |
| `plan/<stage>.md` | before anything runs | "I know I need a tracker — which one, for this scene?" | Which stage to look at. That is the file above. |
| `judge/swap_or_build.md` | a run finished | "Tuning stopped paying — is the module wrong, or is there no module?" | Whole-model doubt. That is `health/bounce.md`. |
| `judge/tradeoffs.md` | a run finished | "What does the next attempt cost, and is it worth it?" | Quality judgements. |
| `health/ladder.md` | a sparse model exists | "Is this good enough? When do I stop?" | An absolute threshold. Everything in it is comparative or corpus-relative. |
| `health/smells.md` | a sparse model exists | "It looks fine — is it?" | Anything a single metric can answer. |
| `health/bounce.md` | a sparse model exists, unhealthy | "Can the registry fix this, or is the right next act building a tool?" | Module-level doubt — that is `judge/swap_or_build.md`, which it hands off to. |
| `evidence/EVIDENCE.md` | checking a claim | "Where did this come from, and how much is it worth?" | A plan. See §3.3. |
| `evidence/INDEX.md` | planning | "Has a capture like mine been solved before, and what solved it?" | A reading to expect. It carries no measurements at all — those are one hop away in the campaign files. |
| `distill/SKILL.md` | session ends | "I learned something. Where does it go and in what shape?" | Currently anything — it has never been executed. |

judge/ and health/ divide by the *kind of doubt* a reader has: doubt about the
module (`swap_or_build`), about the spend (`tradeoffs`), about the result
(`ladder`), about the reading (`smells`), about the whole approach (`bounce`).
Doubt about the corpus itself — which claims to believe when two of them
contradict — is the **reliability ladder** at the top of `evidence/EVIDENCE.md`,
because doubt about the corpus is resolved by looking at how the corpus was
measured, and that is the evidence tier's question.

### 3.1b The health profile — the first designed-in push channel

`health/ladder.md` defines a **seven-rung health profile**: registration
fraction, conditioning (median triangulation angle), composition (support per
point), coverage evenness, composition-adjusted error, yield (structure kept /
structure available, recorded in both track- and observation-form until the
reference campaign decides between them), and pose agreement (final relative
poses against the pairwise two-view estimates — the reading reprojection error
is structurally blind to). Each rung is scene-size invariant and computable
without ground truth; each is reported as a **percentile within the reference
corpus**, and the scalar is the **minimum percentile** — the weakest rung,
matching the ladder's semantics.

**The rungs are read only after the sparse reconstruction step, never against an
upstream stage** — upstream stages have their own diagnostics, and judging the
model from upstream readings is the first entry in `health/smells.md`. The
digest enforces the scope mechanically: the run payload carries it exactly when
a run produces a `sparse_model/v1`.

The per-scene reference values were recorded by the reference campaign in
`evidence/`, and the digest scores against them now. The campaign also falsified
two rung definitions on its own first reading — one had the same value on every
capture in the corpus, the other's filter admitted every point — which is the
process working rather than a defect in it, and both are corrected. What it could
not do is validate a rung; see §7.2. `health/bounce.md` reads the profile across a run's
frontier of attempts: a rung that is low says unhealthy; a rung that is low
**and immobile** across the swaps and bracketed sweeps already tried says the
registry has been given its chance and declined — take the failing rung's
capability gap to `judge/swap_or_build.md` §BUILD.

**It is no longer the only push at that instant.** After a refinement step the
same payload carries the verifier's veto and, when the pose stage reported
escaped points, the second solve's decision; §4 says why neither is left to a
pointer.

### 3.2 The per-module five, and why they are five

Each of the five answers a question a reader has at a **different moment**, and
that is the individuation rule. If two of them could hold the same sentence, the
split has failed.

| File | The moment | Delivery |
| --- | --- | --- |
| `SKILL.md` | before choosing this module | **inlined** into every `sfm_describe_module` |
| `tuning.md` | a number is out of band; which dial, which way, how far | fetched, usually from a diagnostic |
| `limitations.md` | tuning is not working; can this module do the thing at all | fetched, usually from a diagnostic |
| `artifact.md` | reading what it wrote | fetched |
| `sources.md` | "which evidence backs this claim?" | cite-only, like the evidence tier — deliberately not written to be fetched (§4) |

Two placement rules follow from the moment, and both are enforced as edits
rather than stated as aspirations:

**A metric that misleads belongs in `tuning.md`, not `artifact.md`.**
`artifact.md` describes the payload; a warning that a number reads better than
the model is belongs where the reader is deciding what to do about it.

**A claim true of a payload TYPE does not belong in any module's file.**
Type-level facts live in the type schema, and `sfm_describe_module` returns a
`type_contracts` field for every type a module consumes or produces — the fact
is delivered on the highest-traffic call in the system instead of being
duplicated behind five low-traffic ones.

**`SKILL.md` opens with a router**, in all 28: a four-row table saying which of
the other four files to fetch, with a module-specific hook in each row derived
from that module's own manifest ("9 parameters, starting with `weights`"; a real
"It cannot…" heading from its own limitations). **It ends with a provenance
line** — how many runs of this module, at what version, on what corpus, or "run
zero times in any pipeline; nothing here is exercised end to end". Both exist
because `SKILL.md` is inlined: it is the one place a fact is guaranteed to be
seen (§4).

**`tuning.md` ends with the manifest audit** — which of this module's healthy
bands no diagnostic reads (a band with no diagnostic is a description of the
captures measured so far, not a judgement on yours), and which numeric advice is
a setting that worked here rather than a published result. It sits there because
`tuning.md` is delivered when a diagnostic fires, which is the exact moment a
reader is about to trust a band.

**`sources.md` is a cite-only table**: one row per claim, naming what the claim
rests on — a paper, a verified API behaviour, a direct measurement, the
predecessor codebase, or **nothing**. It is module-major on purpose: the
evidence tier is scene-major (per-campaign, per-capture rows), and this is the
one place that answers "everything this module's files claim, and what each
claim rests on" without grepping five files. Scene names are allowed here, as in
the evidence tier — both are citation records.

### 3.3 The tier that must not be used for its obvious purpose

The `evidence/` campaign files hold per-capture measurement tables **with scene
names**, which exist nowhere else — every claim elsewhere is deliberately stated
as a scene *property* ("a controlled rig against a lit backdrop") rather than a
scene name, because a name does not transfer to a capture from outside the
corpus.

The tables exist so a claim can be **traced and re-run**, and the tier says at
the top that planning from a row is the misuse it is most likely to cause: a
reader who matches their own readings against a row to find "the capture like
mine" is usually reading their own capture back to themselves. Each campaign
file ends with a map from the derived claims stated elsewhere back to the rows
that support them, so any single claim can be checked without re-deriving all of
them.

`INDEX.md` is a separate file because it answers the *incompatible* question:
retrieval ("has a capture like mine been solved before?") wants a row you match
against, and citation exists to be cited and **not** matched. One file cannot
serve both without inviting the misuse above. `EVIDENCE.md` is the campaign
index, and carries the reliability ladder (§3.1) plus the standing recall
caution: `sfm_plan_brief` reports `in_planning_corpus`, and when the capture in
front of you is a corpus member, locating your readings inside the quoted ranges
is recall, not confirmation.

---

## 4. What actually causes a file to be read

This is the part of the design with real evidence behind it, and it is the part
most likely to be wrong in a way that matters.

**The measurement.** Seventeen captures were driven to a sparse reconstruction in
full by agents with no repository access — reading only through the tool surface —
with every context read logged. 645 module runs, 108 backtracks.

**The headline result: most context files were never opened** (141 of the 182
that existed at the time). The four delivery mechanisms, ordered by what the log
showed:

**1. Inlining into a manifest call — by far the strongest.**
`sfm_describe_module` was called **204 times**; every per-module skill fetch
combined came to **70**. Anything the describe call carries reaches every
reader. This is why `SKILL.md` carries the router and the provenance line, and
why the type contract is in `describe_module`'s response.

**2. Refusal — a module that will not complete without a file being read.**
`SceneDescription/rubric.md` has **zero** pointers at it and was read **30
times**, on every capture: the module refuses to produce a description without
it. The only mechanism in the system with a 100% hit rate, and it is used once.

**3. A diagnostic firing.** 126 diagnostics carry a `see_also`, all anchored to
a specific heading: 64 point into `tuning.md`, 53 into `limitations.md`, 8 into
`artifact.md`, 1 into `SKILL.md`. These get read **when the diagnostic actually
fires**, not because the pointer exists.

**4. A pointer nobody is standing on — the weakest, and it is close to zero.**
One `limitations.md` named by four pointers was opened zero times; of the 62
files named by any pointer, roughly seven were ever opened.

**The conclusion, stated as sharply as the evidence allows: files are read when
something compels them, not when something points at them.** Pointers are
necessary and nowhere near sufficient — 4 pointers and 0 reads against 0
pointers and 30 reads falsifies "add more pointers" as a fix.

Three current design decisions are this finding, applied:

- **`sources.md` is cite-only** because zero of the 126 diagnostic pointers
  point into it — nothing in the system compels it, so nothing load-bearing is
  allowed to live only there. Its two load-bearing facts ride the two strongest
  mechanisms instead: the provenance line on the inlined router (mechanism 1),
  and the unsourced-band audit in `tuning.md` beside the bands (mechanism 3).
- **The health digest exists** because the health moment otherwise has no
  compelled delivery at all: nothing fires a diagnostic for "your finished model
  is worse than it looks". The run payload pushing the profile at the instant a
  sparse model exists is mechanism 3, built for the one moment that had none.
- **The verifier's veto and the second solve run inside the service.** After a
  refinement step, `SparseVerification` checks the model against the matches it
  was never fitted on, and when the pose stage reported escaped points the chain
  is re-solved at a wider window; both verdicts arrive in that step's own result.
  Left to the agent, the only grounds for skipping either would be the
  self-reported readings a coherently wrong model satisfies, so neither rides a
  pointer. Added after the logged sweep: their read rate is designed, not
  measured.
- **The resolver never searches a path that has no files behind it.** Measured:
  a search path pointing at nothing manufactured 24 errored fetches in the
  sweep, and readers who followed a pointer into the miss concluded the whole
  knowledge base was gone — one said so in writing.

**A second consequence, about economics rather than discoverability.** The five
per-module files cost five separate calls; the describe call returns ~14 KB of
curated prose in one. An agent optimising its own context budget will prefer the
manifest, and did. That is a rational choice, and any fix that assumes readers
simply did not know the files were there will not work.

---

## 5. Why the tiers are organised by moment

> **Organise context by the question a reader is holding, not by the kind of
> knowledge it is.**

A reader with a broken reconstruction does not know or care whether their answer
is mechanical or subjective, measured or judged. They know **where in the loop
they are standing** — planning, judging a finished run, evaluating a model,
checking a claim — and that is the index the directory names implement. Each
moment also gets a delivery mechanism matched to it: `plan/` is bundled into
`sfm_plan_brief`, the module tier is routed by firing diagnostics, `health/` is
pushed by the run payload's digest, and `evidence/` is the citation target of
everything else.

The sweep's demand evidence, question by question:

| The question, as readers phrased it | Answered by | Measured demand |
| --- | --- | --- |
| "What do these scene numbers mean for my plan?" | `plan/scene_to_pipeline.md` | 36 fetches, all 17 captures — the most-read file in the tier |
| "Which member of this stage, for this scene?" | `plan/<stage>.md` | 2–6 fetches each, ≤6 captures |
| "Is this good enough, and is it actually right?" | `health/ladder.md`, `health/smells.md` | requested 8 times *before either existed* — the clearest demand signal the sweep produced |
| "How do I move this number?" | the module's `tuning.md`, via a diagnostic | 64 diagnostics route there |

Two things about that table shaped the design. The most-read file is the one
keyed on a question someone actually has, written in the reader's situation
("I have numbers, what do they imply?") rather than by topic. And the
most-requested *missing* document was the health question — readers who could
not decide whether a finished model was good enough — which is why the health
moment now has both its files and the only push channel in the system. Nothing
in the sweep ever asked for atomic lesson cards or any per-episode memory
format; demand was for question-shaped documents, and that is what the tiers
hold.

---

## 6. How a claim is supposed to be written

Three conventions constrain what may be recorded. They exist because the goal is
generalisation to captures outside the corpus, and the natural way to write a
lesson defeats that. The full recording protocol is `distill/SKILL.md` §9.

**Describe the scenario, never the scene.** "A controlled rig against a lit
backdrop", not a dataset-and-scan name. A scene name is a lookup key for this
corpus and carries nothing to a new capture. Scene names survive in the citation
records only — the `evidence/` tier and the modules' `sources.md`.

**A band is an observed range over a named corpus, not a threshold.** Quoted
ranges say what was seen across the captures in `evidence/CORPUS.txt`. The
distinction that keeps being got wrong: **a corpus maximum is the largest of N
draws, not a limit** — the next capture exceeding it is expected, not anomalous.
Bands are written so that reading one as a cut point is visibly a misuse.

**An escape names a capability, never a module.** `limitations.md` says
"something producing `tracks/v1` that does not consume `pairwise_matches/v1`",
not a module name. Module names go stale; capability queries resolve against the
live registry.

**And a correction goes where the reader is standing.** A caveat about a metric,
written in the file that introduces the metric, does not reach the reader who
meets it two stages later inside a diagnostic's suggested action. Corrections
are repeated at every point the claim is acted on, which is deliberate
duplication and the one place the design accepts it.

---

## 7. What is not done

Listed by how much it undermines the claims above.

### 7.1 Two of 28 modules have still never been run in a pipeline

`DenseMVS` and `DenseVGGT`. They are deferred deliberately — dense comes after
the strict-context holdout in the standing three-step plan — rather than
overlooked.

Ten others were in this list until the alternate-leg campaign, and their prose
was from isolated testing or carried from the predecessor codebase.
Each one's provenance line says so on every describe call — but **saying so is
not testing it**. The argument for running them: every correction in the current
corpus came from a module that *was* run, and the corrections concentrated on
the most-run modules (109, 88 and 84 runs). Nothing was ever corrected on a
module that never ran, and the honest reading is that nothing was *checked*
there.

**Both phases of the reference campaign have now run.** Phase A re-ran the
reference pipeline deterministically over the whole corpus, seeding `evidence/`
with durable per-capture rows and the reference distribution for the health
profile. Phase B ran ten of the twelve in the situation each exists for — the
detector-free matchers where classical detection starves, the feed-forward
pose/sparse modules on the worst-registration captures, the alternate trackers,
local BA against global — each as a **single-stage swap against the reference**,
so every comparison has one variable in it. The two dense modules stay deferred
by the standing plan (dense comes after the strict-context holdout).

**Ten modules moved from unrun to measured**, which closes the asymmetry above
for every family except dense. What Phase B could not close is the *quality* of
that evidence: one capture per situation is a characterisation, not a ranking,
and the campaign was explicitly not a sweep of any module's dials.

The asymmetry that remains is one family wide: `plan/dense.md` still compares
two modules neither of which has run, and is the only stage file in that
position.

### 7.2 The health profile has a reference corpus, and is still not validated

Phase A ran: one fixed pipeline over all sixteen corpus captures, and
`evidence/reference-pipeline-2026-09` plus its generated `reference_profile.yaml`
are the distribution the digest now scores against. Two rung definitions did not
survive their own first reading — composition read the same value on every
capture in the corpus, and the error rung's "well-supported" filter admitted
every point — and both were corrected against the data rather than defended.

What the campaign could **not** do is validate a rung. It computed ground-truth
pose error beside every internal reading, and that check collapsed for a reason
worth more than the intended result: true pose error is measured over the images
a model registered, so the three models that abandoned most of their capture
scored at least as well as every fully-registered one. A single accuracy number
cannot see what a model discarded — which vindicates the vector-with-registration-
first design and disqualifies the cross-capture correlation as a test.

Validating a rung needs two models of the same capture at equal registration.
That is what the alternate legs were shaped to produce, and **they have now run**
— `evidence/alternate-legs-2026-09`. Two conditions supplied comparable models:
a swap at or after the pose stage cannot add or drop a camera, and several
captures ended with three or four *different* pipelines each registering the
capture in full. Seventeen comparisons resulted, and each rung was scored on
whether it ranked the pair the way ground truth did.

**Coverage and observation-yield ranked all seventeen correctly. Composition
ranked six.** Conditioning and composition turn out to be *conditional* readings
rather than rungs: both rise when short, weakly-triangulated points are
discarded, so on the nine comparisons where the two models differed only by a
point-retention rule they were right once and never; on the eight where the
difference was a genuine change of branch, conditioning was right eight times.
Yield is the reading that says which case you are in, which is the argument
yield was put in the profile to make, now measured on both sides. The error rung
was right twice of eight across branches. Pose agreement ranked fourteen of the
fifteen it could be computed on — and is unevaluable on a pipeline with no
matching stage, since its two-view estimates are re-derived from a matches
artifact.

**The yield-form decision is still open.** Observation-yield ranked 17 of 17 and
track-yield 16, which is one comparison of difference and not enough to choose
on; observation-yield stays the provisional default on the argument that it also
punishes truncating long tracks.

What is still not settled is whether the rungs discriminate *within* a healthy
band. Every comparison here is between models that differ visibly, and a corpus
of one pipeline means an alternate leg is scored against a distribution that
never contained its kind — the weakest-rung scalar saturates and ties exactly
where the vector still separates.

### 7.3 The distillation loop has never executed

`distill/SKILL.md` specifies how a session becomes context: what shape a lesson
takes, that selection and tuning context need different shapes, that a metric
claim owes a denominator, that the evidence is a shape and never a cut point.
The loop it describes has never run; every line of context in this tree was
written by hand, so a claim's age is the age of the last person who looked at
it. The reference campaign doubles as the first body of evidence the loop could
be exercised on.

### 7.4 `evidence/INDEX.md` is populated, on a different key than designed

**It was empty for a long time and the reason was a real disagreement, not an
unwritten file.** The original design derived traits by thresholding
`scene_analysis/v1` numbers, with the cut points held in the global tier so that
revising "narrow baseline" would not cost a re-run. `scene_analysis/v1` still
declares a `traits` group that neither analysis module fills, and a test asserts
they do not. The cut points were never written because §6 refuses to name cut
points the evidence does not support, so retrieval had no key.

**What broke the deadlock was evidence against the threshold approach rather
than a decision to relax §6.** The one published cut point — the connectivity
band in `plan/scene_to_pipeline.md` §3b — was refitted on sixteen full captures
over seven statistics and two definitions of fragmentation and produced no clean
separation under any of them, and it was withdrawn. A key built on thresholds
would have been built on the one thing this corpus has now falsified twice.

**So the key is an observed capture kind rather than a derived one.** Traits are
recorded from a `SceneDescription` reading — what a reader looked at and graded
under a fixed rubric — from a closed vocabulary written into `INDEX.md` itself:
setting, capture shape, subject, target surface, repetition, hazards. Three
properties make this work where thresholding did not:

- **It cannot drift.** A category someone assigned by looking can be wrong, and
  it stays wrong in a visible way; a cut point silently changes meaning every
  time the corpus grows.
- **It is already compelled.** `SceneDescription` refuses to produce a report
  without its rubric being fetched, which is the only delivery mechanism in this
  system measured at a 100% hit rate (§4). A planner who needs to place their own
  capture in the vocabulary reaches it through a module that will not complete
  otherwise.
- **It says things nothing else measures.** Coherent versus diffuse reflection,
  whether a flat region is wanted or backdrop, whether an empty region is clipped
  or merely dim, movers, lens flare. Those are the traits that changed decisions
  across the campaign, and not one of them is derivable from a number this stack
  produces.

**The rows carry no measurements.** Every point count, error and profile reading
stays in the campaign files, reached through a per-capture anchor that
`tools/phase_c_report.py` now emits (`#cap-<slug>`). That keeps §3.3's split
intact while giving the precedent tier a route to the evidence tier, which it
previously lacked: the outcome column routes a reader to `health/ladder.md` when
a model is finished, and to `judge/swap_or_build.md` when the registry may not
hold the answer.

**What is still open.** The outcome vocabulary has no `unsolved` rows, so the
file cannot illustrate the case it routes to most consequentially. All sixteen
rows are corpus members, so any corpus capture matches its own answer key —
a stronger form of the recall problem than the range tables have, and the file
says so at the top. And the vocabulary has been applied by one reader across one
corpus of two benchmark families; whether two readers would assign the same
traits to the same capture has not been tested.

### 7.5 Bands with no diagnostic reading them

Four sparse-stage modules publish 10–11 healthy bands each that no diagnostic
reads. The `tuning.md` audits now warn about every one of them at the moment
they might be trusted, but a warning is not a fix: each such band needs either a
diagnostic or a widening, and which is a per-band decision that mostly waits on
Phase A/B giving the never-run modules real numbers.

### 7.6 Claims caveated rather than re-derived

At least one falsified claim was corrected by adding a caveat where it needs an
experiment — the detector-recovery finding in `plan/scene_to_pipeline.md` §3b,
observed on a subset of frames and needing both branches re-run at full frame
count on the same captures. A caveat is honest and it is not a result.

### 7.7 All 28 `SKILL.md` files exceed the size cap they were designed to

The router and the provenance line were added without trimming what was there,
so the inlined tier sits at ~111 KB against a design cap of 1.5 KB per file.
Trimming is a content judgement per module rather than something to automate:
`SceneDescription/SKILL.md` is the largest and its two-call flow is
load-bearing — it drives the refusal mechanism in §4, the only delivery
mechanism that works every time.

---

## 8. Where I think this is weakest — for critique

1. **The compulsion finding may be over-generalised.** It rests on one strong
   positive case (`rubric.md`, 30/30) and a set of negatives. "Make more modules
   refuse" is the obvious response and it is also how you build a system that
   annoys its users into ignoring it. There is no measurement of where refusal
   stops being worth it.

2. **The cite-only citation tables have zero compulsion, by design.** Nothing
   will ever cause `sources.md` to be fetched; the bet is that its load-bearing
   facts are all promoted onto compelled channels and what remains only matters
   to a reader who is already suspicious. That bet is cheap now (~70 KB across
   28 modules) — but "cheap enough to be fine" is exactly the kind of claim this
   corpus has been wrong about before.

3. **The health profile still is not validated, only exercised.** The reference
   campaign falsified two of its rung definitions, which is evidence the process
   works — but the ground-truth check it was meant to end with turned out to be
   confounded by registration (§7.2), so no rung has been shown to order two
   models the way truth does. The corpus is also sixteen draws from two
   benchmark families, so a percentile is coarse and provincial at once.

4. **The refusal to name thresholds has now been tested once, and survived.** It
   is principled (§6), and it blocked trait derivation for as long as retrieval
   was designed around cut points. The one published cut point was then refitted
   on full captures and withdrawn, which is evidence for the refusal rather than
   against it, and `evidence/INDEX.md` was keyed on observed capture kind
   instead (§7.4). That is one falsified threshold, not a general result: a
   provisional cut point that is labelled provisional and revised might still
   dominate no cut point at all for some decisions, and nothing here has tested
   that.

5. **The evidence base is two benchmark families.** Every range was fitted on
   the captures in `evidence/CORPUS.txt`, all from two benchmark datasets. The
   context describes scenarios rather than scenes precisely so it transfers —
   but that transfer has been tested on exactly one out-of-corpus capture.

6. **Nothing measures whether the context is *right*, only whether it is read.**
   The read log says which files were opened. It does not say whether the
   decision that followed was better than the decision an agent with no context
   would have made. There is no control arm.

7. **The corrections are self-graded.** The claims that were falsified were
   falsified by reading agents who were themselves working from this context.
   That is not independent.

---

## 9. Related documents

- [`docs/design/knowledge-system.md`](design/knowledge-system.md) — the original
  design and the record of how the tree evolved into this organisation. History
  lives there, not here.
- [`docs/design/module-skills.md`](design/module-skills.md) — the specification
  for the per-module five.
- [`docs/mcp-tools.md`](mcp-tools.md) — the tool surface, and §4 on which tiers
  each tool reads.
- [`skills/SKILLS.md`](../skills/SKILLS.md) — the resident index itself.
- [`skills/distill/SKILL.md`](../skills/distill/SKILL.md) — how new context is
  supposed to be written.
