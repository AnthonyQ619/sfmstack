---
name: context-structure-design
description: How written context is organised so an agent can select and tune SfM modules from retrieval alone — the layout, what each file is for, what causes it to be read, and what is measured about whether that works.
status: current as of 2026-09-02; the layout described here is what is on disk
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

This document describes the layout, says what each file is for, says **what causes
it to be read**, and reports what has been measured about whether that works. It is
written to be argued with. §8 lists the places I think the design is weakest.

---

## 1. The constraint that shapes everything

Context is **retrieved, not resident**. Exactly one file is always in the agent's
window (`skills/SKILLS.md`, ~12 KB). Everything else costs a tool call, and the
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

```
skills/
  SKILLS.md              12 KB   ALWAYS RESIDENT. The index and the judgment digest.
  scene_to_pipeline.md   80 KB   How to read a capture's measured numbers into a plan.
  families/                      Choosing WITHIN a stage. 8 files, one per stage + README.
    README.md · detection · matching · tracking · pose · sparse · optimization · dense
  judgment/                      Practitioner calls. Human-authored, subjective, non-binding.
    swap_or_build · stopping · smells · priors · tradeoffs
  runs/                          Evidence, with scene names.
    INDEX.md               trait-keyed retrieval table  [NO ROWS — see §7]
    EVIDENCE.md            per-capture citation record
    CORPUS.txt             the captures every quoted range was fitted on
  distill/
    SKILL.md               how to write new context      [THE LOOP HAS NEVER RUN — see §7]

modules/<name>/
  module.yaml                    THE MANIFEST. Params, metrics, diagnostics, types.
  skills/
    SKILL.md                     router + orientation    (inlined into every describe call)
    tuning.md                    how to move this module's numbers
    limitations.md               what this module cannot do
    artifact.md                  the payload it writes
    sources.md                   where claims come from, and what rests on nothing
```

**Scale.** 28 modules across 8 stages (source 1, analysis 3, detection 4, matching
6, tracking 3, pose 2, sparse 5, optimization 2, dense 2), declaring 238
parameters, 329 metrics and 126 diagnostics between them. 141 per-module skill
files: five per module, plus one extra (`SceneDescription/rubric.md`, §4). By
volume the module tier is about 675 KB and the global tier about 265 KB.

It is reachable through `sfm_workflow_skill("context-structure-design")` like
any other document beside `skills/`.

**Nineteen MCP tools** reach it, of which four are the ones that matter here:
`sfm_describe_module`, `sfm_module_skill`, `sfm_workflow_skill`, `sfm_plan_brief`.

---

## 3. What each file is for

### 3.1 The global tier

| File | The question it answers | Not this |
| --- | --- | --- |
| `SKILLS.md` | "What exists, and what should I be worried about?" | Any actual guidance. It is an index and a digest. |
| `scene_to_pipeline.md` | "I have numbers off this capture. What do they imply for my plan?" | A decision. It translates measurements into the vocabulary the family files are written in. |
| `families/<stage>.md` | "I know I need a tracker — which one, for this scene?" | Which stage to look at. That is the file above. |
| `judgment/*.md` | "Is this good enough? Which of these claims do I trust?" | Anything measured. This tier is explicitly subjective and non-binding. |
| `runs/EVIDENCE.md` | "Where did this claim come from? How do I re-run it?" | A plan. See §3.3. |
| `runs/INDEX.md` | "Has a capture like mine been solved before?" | Currently anything — it has no rows. |
| `distill/SKILL.md` | "I learned something. Where does it go and in what shape?" | Currently anything — it has never been executed. |

The five `judgment/` files divide by the *kind of doubt* a reader has, which is
different from the kind of question:

- **`swap_or_build`** — the doubt is about the module. Tuning has stopped paying;
  is the tool wrong, or is there no tool?
- **`stopping`** — the doubt is about the result. The objective is as much
  structure as possible from a model you have reason to trust, and this file
  carries the constraint ladder (registration → conditioning → composition →
  coverage → error) and the procedure for comparing two models.
- **`smells`** — the doubt is about the reading. Seven cases where every metric
  was individually correct and the conclusion drawn from them was wrong.
- **`priors`** — the doubt is about the context itself. Which parts of this corpus
  to believe when they contradict each other or your own measurement.
- **`tradeoffs`** — the doubt is about the spend. What actually costs time,
  including the axis normally left out: the cost of a run that dies partway.

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
| `sources.md` | "where is this claim from, and what is it worth?" | fetched (rarely — §4) |

Two rules follow from the moment, and both were applied as edits rather than
stated as aspirations:

**A metric that misleads belongs in `tuning.md`, not `artifact.md`.** `artifact.md`
describes the payload; a warning that a number reads better than the model is
belongs where the reader is deciding what to do about it. Twenty-two such sections
were moved, and `artifact.md` fell from 115 KB to 84 KB.

**A claim true of a payload TYPE does not belong in any module's file.** Seven
type-level blocks were duplicated across producer modules, which is seven places
for one fact to go stale. They now live in the type schema, and
`sfm_describe_module` returns a `type_contracts` field for every type a module
consumes or produces — so the fact is delivered on the highest-traffic call in the
system instead of being duplicated behind five low-traffic ones.

**`SKILL.md` opens with a router**, in all 28: a four-row table saying which of the
other four files to fetch, with a module-specific hook in each row derived from
that module's own manifest ("9 parameters, starting with `weights`"; a real "It
cannot…" heading from its own limitations). This exists because `SKILL.md` is
inlined, so it is the one place a pointer is guaranteed to be seen.

**`sources.md` carries two mandatory sections, in all 28**, generated from a
per-module audit of the manifest:

- **"What is asserted without a source"** — the healthy bands no diagnostic reads,
  the numeric tuning advice with no citation, and the scope of the measurements
  (how many runs of *this* module, at what version, on what corpus).
- **"Review triggers"** — the events that should send someone back to this file: a
  version change, a capture unlike the corpus, a reading crossing a band with
  nothing firing.

These are module-specific by construction, never blanket. `PoseEssentialToPnP`'s
names its own uncited metrics and "109 runs at 1.2.0"; `DenseMVS`'s says plainly
that it was run zero times and that nothing in it has been exercised end to end.

### 3.3 The one file that must not be used for its obvious purpose

`runs/EVIDENCE.md` holds per-capture measurement tables **with scene names**, which
exist nowhere else — every claim elsewhere is deliberately stated as a scene
*property* ("a controlled rig against a lit backdrop") rather than a scene name,
because a name does not transfer to a capture from outside the corpus.

The tables are there so a claim can be **traced and re-run**, and the file says at
the top that planning from a row is the misuse it is most likely to cause: a reader
who matches their own readings against a row to find "the capture like mine" is
usually reading their own capture back to themselves.

This is why `INDEX.md` and `EVIDENCE.md` were split apart in this round. They had
been one file, and they answer incompatible questions: retrieval wants a row you
match against; citation exists to be cited and not matched. Anyone fetching the
file to plan got a page of scene-named tables under a heading promising precedent.

---

## 4. What actually causes a file to be read

This is the part of the design with real evidence behind it, and it is the part
most likely to be wrong in a way that matters.

**The measurement.** Seventeen captures were driven to a sparse reconstruction in
full by agents with no repository access — reading only through the tool surface —
with every context read logged. 645 module runs, 108 backtracks.

**The result: 141 of 182 context files were never opened.**

The four delivery mechanisms, ordered by what the log showed:

**1. Inlining into a manifest call — by far the strongest.**
`sfm_describe_module` was called **204 times**; every per-module skill fetch
combined came to **70**. Anything the describe call carries reaches every reader.
This is why `SKILL.md` carries the router and why the type contract moved into
`describe_module`'s response. It is also a discovery about a file's real role:
`SKILL.md` was not an unread file, it was the *most-delivered* file in the corpus,
and it had no consistent job.

**2. Refusal — a module that will not complete without a file being read.**
`SceneDescription/rubric.md` has **zero** `see_also` pointers and was read **30
times**, on every capture. The module refuses to produce a description without it.
This is the only mechanism in the system with a 100% hit rate, and it is used once.

**3. A diagnostic firing.** 126 diagnostics carry a `see_also`, all of them
anchored to a specific heading, naming 62 distinct files: 64 point into
`tuning.md`, 53 into `limitations.md`, 8 into `artifact.md`, 1 into `SKILL.md`.
These get read **when the diagnostic actually fires**, not because the pointer
exists.

**4. A pointer nobody is standing on — the weakest, and it is close to zero.**
`SceneMotion/limitations.md` is named by four `see_also` pointers and was opened
**zero** times. Of the 62 files named by a pointer, roughly seven were ever
opened.

**The conclusion, stated as sharply as the evidence allows: files are read when
something compels them, not when something points at them.** Pointers are
necessary and are nowhere near sufficient. The natural fix — "add more
`see_also`" — is falsified by the two cases above: 4 pointers and 0 reads against 0
pointers and 30 reads.

**A consequence the numbers make hard to argue with.** `sources.md` is 141 KB, the
second-largest of the five, and **zero of the 126 diagnostic pointers point into
it**. Nothing in the system compels it. Its content is real — provenance, and the
audit of what rests on nothing — but on current evidence it is written for a reader
who has already decided to be suspicious. Whether that reader exists often enough
to justify 141 KB is an open question and it is on the list in §8.

**A second consequence, about economics rather than discoverability.** The five
per-module files total ~37.9 KB per module across five separate calls. The
describe call returns ~14 KB of curated prose in one. An agent optimising its own
context budget will prefer the manifest, and did. That is not a failure of
discovery; it is a rational choice, and any fix that assumes readers simply did not
know the files were there will not work.

---

## 5. Why the tier structure is organised the way it is

The original design had four tiers split as **`workflow/` for mechanical knowledge
and `judgment/` for subjective knowledge**. That split sorts context by *who
authored a claim*. It has been retired, and the reason is the most transferable
finding here:

> **Organise context by the question a reader is holding, not by the kind of
> knowledge it is.**

A reader with a broken reconstruction does not know or care whether their answer is
mechanical or subjective. They know what went wrong. Sorted the other way,
`workflow/` had no natural content and was never written — while
`scene_to_pipeline.md`, which is keyed on a question someone actually has ("what do
these numbers mean for my plan?"), was written without being designed and became
the most-read file in the tier (36 fetches, all 17 captures).

`workflow/` was requested **24 times across the sweep and returned an error every
time**. The cost was not the missing content. The error's `Available:` list did not
name the documents that do exist, so readers who followed a pointer into it
concluded the whole knowledge base was missing, and one said so in writing. The
directory has been deleted **and the resolver's search path removed with it** — a
search path pointing at nothing manufactures misses — with a redirect table left in
`SKILLS.md` so the retirement is discoverable rather than silent.

The four questions the sweep showed readers actually asking, with demand:

| The question, as readers phrased it | Answered by | Fetches |
| --- | --- | --- |
| "What do these scene numbers mean for my plan?" | `scene_to_pipeline.md` | 36, all 17 captures |
| "Which member of this stage, for this scene?" | `families/<stage>.md` | 2–6 each, ≤6 captures |
| "Is this good enough, and is it actually right?" | `judgment/stopping.md`, `smells.md` | 8 requests *before either existed* |
| "How do I move this number?" | the module's `tuning.md`, via a diagnostic | 64 diagnostics route there |

`judgment/stopping.md` being the single most-requested missing document — asked for
8 times by readers who could not decide whether a finished model was good enough —
is the clearest demand signal the sweep produced, and nothing ever asked for the
atomic lesson cards the original design centred on.

---

## 6. How a claim is supposed to be written

Three conventions constrain what may be recorded. They exist because the goal is
generalisation to captures outside the corpus, and the natural way to write a
lesson defeats that.

**Describe the scenario, never the scene.** "A controlled rig against a lit
backdrop", not `DTU_scan33`. A scene name is a lookup key for this corpus and
carries nothing to a new capture. Scene names survive in exactly one place,
`runs/EVIDENCE.md`, as provenance.

**A band is an observed range over a named corpus, not a threshold.** Quoted
ranges say what was seen across the captures in `runs/CORPUS.txt`. The distinction
that keeps being got wrong: **a corpus maximum is the largest of N draws, not a
limit** — the next capture exceeding it is expected, not anomalous. Bands are
written so that reading one as a cut point is visibly a misuse.

**An escape names a capability, never a module.** `limitations.md` says
"something producing `tracks/v1` that does not consume `pairwise_matches/v1`", not
"use LoFTR". Module names go stale; capability queries resolve against the live
registry.

**And a correction goes where the reader is standing.** A caveat about a metric,
written in the file that introduces the metric, does not reach the reader who meets
it two stages later inside a diagnostic's suggested action. Corrections are
repeated at every point the claim is acted on, which is deliberate duplication and
the one place the design accepts it.

---

## 7. What is not done

Listed by how much it undermines the claims above.

### 7.1 Twelve of 28 modules have never been run in a pipeline

`BundleAdjustmentLocal`, `DenseMVS`, `DenseVGGT`, `FeatureDetectionORB`,
`FeatureMatchLoFTR`, `FeatureMatchRoMa`, `FeatureMatchSuperGlue`, `PoseVGGT`,
`SparseMapAnything`, `SparseVGGT`, `FeatureTrackTapir`, `FeatureTrackVGGSfM`.

Their prose is from isolated testing or carried from the predecessor codebase.
Each one's `sources.md` now says so in those words — but **saying so is not testing
it**.

The argument for running them is that every correction made in this round came from
a module that *was* run, and the most-run modules (`PoseEssentialToPnP` 109 runs,
`BundleAdjustmentGlobal` 88, `FeatureTrackUnionFind` 84) are where the corrections
concentrated — the converged-solve claim, the local-BA window default, the
triangulation-angle reading, the matcher's tuning criterion. Nothing was corrected
on a module that never ran, and the honest reading of that is that nothing was
*checked* there. This is the largest outstanding item.

This also means the family files are asymmetrically evidenced. `families/dense.md`
compares two modules neither of which has run; `families/sparse.md` compares five
of which three have.

### 7.2 The distillation loop has never executed

`distill/SKILL.md` (16 KB) specifies how a session becomes context: what shape a
lesson takes, that selection and tuning context need different shapes, that a
metric claim owes a denominator, that the evidence is a shape and never a cut
point. It was fetched once across seventeen captures and the loop it describes has
never run. Every edit in this repository's context has been written by hand.

**Held deliberately, with a proposal on the table:** seed `runs/` from the
seventeen-capture sweep, which is the first body of evidence large enough that hand
transcription is the wrong move. Until that is decided, `distill/SKILL.md` is a
specification for a process that does not exist, which is a form of staleness even
though every sentence in it is defensible.

### 7.3 `runs/INDEX.md` is empty, and is blocked upstream

Its retrieval is a set intersection between a capture's derived traits and a run's
recorded traits. **Nothing derives traits.** `scene_analysis/v1` declares a `traits`
group and neither analysis module fills it, by design: traits were to be derived by
the orchestrator from thresholds held in `judgment/`, so that revising "narrow
baseline" would not cost a re-run.

Those thresholds do not exist, and their absence is a position rather than an
omission — `scene_to_pipeline.md` records observed ranges over a named corpus and
refuses to name cut points the evidence does not support (§6). So the blockage is
now a stated disagreement about whether cut points should exist at all, which is a
better place to be than an unwritten file, but the capability is still blocked.

The plumbing under it is live: the orchestrator already binds each run to its scene
on the first step that touches one, so nothing needs re-plumbing when rows arrive.

### 7.4 Bands with no diagnostic reading them

`SparseMapAnything` and `SparseVGGT` publish 11 healthy bands each that no
diagnostic reads; `SparseGlobalCOLMAP` and `SparseTriangulationGTSAM` 10 each. A
band nothing reads is a trap: it looks like a judgement and is a description of the
captures measured so far. Each such band needs either a diagnostic or a widening,
and which is a per-band decision.

### 7.5 Claims caveated rather than re-derived

At least one falsified claim was corrected by adding a caveat where it needs an
experiment — the detector-recovery finding in `scene_to_pipeline.md` §3b, which was
observed on a subset of frames and needs both branches re-run at full frame count
on the same captures. A caveat is honest and it is not a result.

### 7.6 All 28 `SKILL.md` files exceed the size cap they were designed to

The router was added without truncating what was there, so the tier grew (73 → 101
KB) where the plan said it would shrink. Trimming is a content judgement per module
rather than something to automate: `SceneDescription/SKILL.md` is 6.5 KB and its
two-call flow is load-bearing — it drives the refusal mechanism in §4, the only
delivery mechanism in the system that works every time.

---

## 8. Where I think this is weakest — for critique

1. **The compulsion finding may be over-generalised.** It rests on one strong
   positive case (`rubric.md`, 30/30) and a set of negatives. "Make more modules
   refuse" is the obvious response and it is also how you build a system that
   annoys its users into ignoring it. There is no measurement of where refusal
   stops being worth it.

2. **`sources.md` is 141 KB with zero compulsion.** Either something should point
   into it or it should be much smaller. The current answer — that it serves a
   reader who has already decided to be suspicious — is unfalsified because it is
   nearly unfalsifiable.

3. **The refusal to name thresholds may be costing more than it saves.** It is
   principled (§6) and it is what blocks trait derivation and therefore
   `runs/INDEX.md` (§7.3). A provisional cut point that is labelled provisional and
   revised might dominate no cut point at all. I do not know, and the experiment
   that would settle it has not been designed.

4. **The evidence base is two benchmark families.** Every range was fitted on DTU
   and ETH3D captures. The context is written to describe scenarios rather than
   scenes precisely so it transfers — but that transfer has been tested on exactly
   one out-of-corpus capture.

5. **Nothing measures whether the context is *right*, only whether it is read.**
   The read log says which files were opened. It does not say whether the decision
   that followed was better than the decision an agent with no context would have
   made. There is no control arm.

6. **The corrections are self-graded.** The claims that were falsified this round
   were falsified by reading agents who were themselves working from this context.
   That is not independent.

---

## 9. Related documents

- [`docs/design/knowledge-system.md`](design/knowledge-system.md) — the original
  design and a STATUS table of what was built. **Read its STATUS section first**;
  parts of the design below it were never implemented.
- [`docs/design/module-skills.md`](design/module-skills.md) — the specification for
  the per-module five.
- [`docs/mcp-tools.md`](mcp-tools.md) — the tool surface, and §4 on which tiers each
  tool reads.
- [`skills/SKILLS.md`](../skills/SKILLS.md) — the resident index itself.
- [`skills/distill/SKILL.md`](../skills/distill/SKILL.md) — how new context is
  supposed to be written.
