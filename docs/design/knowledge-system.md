---
name: knowledge-system
description: The knowledge architecture the driving agent reasons over — a human-authored judgment tier, per-module skills, a corpus of worked runs, and the distillation loop. Read the STATUS section first: the cross-cutting workflow tier this document designs was measured, found to be pure cost, and has been retired.
status: partly built, partly retired — see STATUS, measured 2026-09-02
---

# Knowledge System

Part of [target-architecture.md](target-architecture.md). Per-module files are
specified in [module-skills.md](module-skills.md); this document covers the tier
above them, the worked-run corpus, and the distillation loop.

**For what is actually on disk today, read
[`docs/context-structure-design.md`](../context-structure-design.md) instead.** It
describes the current layout, what causes each file to be read, and what is
measured about whether that works. This document is the original design plus a
STATUS section recording where it diverged.

Modelled on the structure in
[KunalMGupta/interioragent](https://github.com/KunalMGupta/interioragent):
hand-distilled markdown as the master index, `skills/workflow/*.md` guides above
per-item skills, a large corpus of worked examples indexed by tags, atomic lesson
cards cross-referenced from those examples, reasoning-based retrieval with no
embeddings, and a loop that ends in *distil lessons back into files*.

## REORGANISED 2026-09-07 — the tiers below now live under different names

The knowledge-kind tiers this document designs were reorganised into **moment
tiers** — organised by where in the loop the reader is standing, which is the
lesson the `workflow/` retirement taught. The mapping (old → new):
`scene_to_pipeline.md` and `families/` → `plan/`; `judgment/swap_or_build` and
`judgment/tradeoffs` → `judge/`; `judgment/stopping` → `health/ladder`,
`judgment/smells` → `health/smells`, plus a new `health/bounce`;
`judgment/priors` folded into `evidence/EVIDENCE.md`; `runs/` → `evidence/`,
with per-campaign files and `EVIDENCE.md` as their index. Old topic names
redirect at the resolver. Every path in the STATUS table and the design below is
pre-reorganisation; [`docs/context-structure-design.md`](../context-structure-design.md)
describes what is on disk now.

## STATUS — what is built, measured 2026-09-02 (paths pre-reorganisation)

**This document is the DESIGN. Most of the tier structure below was never built,
and a seventeen-capture sweep measured what that costs.** Read the table before
the design, because readers have followed this document's descriptions to files
that do not exist and concluded the evidence behind the stack was missing.

| Tier | Designed | Actually built | Measured use across 17 full pipelines |
| --- | --- | --- | --- |
| `SKILLS.md` | master index | **built** | 22 fetches, all 17 captures |
| `scene_to_pipeline.md` | not in this design | **built**, 81 KB | 36 fetches, all 17 — the workhorse |
| `families/` | one per stage | **built**, 8 files | 2–6 fetches each, at most 6 of 17 captures |
| `judgment/` | triage, stopping, priors, tradeoffs, smells | **5 of 5 present** as of 2026-09-02 (`swap_or_build`, `stopping`, `smells`, `priors`, `tradeoffs`); `triage` deliberately not written | `stopping` was requested 8 times before it existed |
| `workflow/` | six guides | **RETIRED 2026-09-02** — directory deleted, resolver search path removed | 24 requests across the sweep, every one an error |
| `runs/` | RUN.md corpus + tagged INDEX | **SPLIT 2026-09-02** into `INDEX.md` and `EVIDENCE.md`; **no RUN.md corpus exists and none will** — the working unit is a generated campaign file. `INDEX.md` **populated 2026-09-10** with 16 precedent rows, keyed on observed capture kind rather than on derived traits | 4 fetches during the sweep, when there was nothing to retrieve |
| lesson cards (`L-00NN`) | atomic, cross-referenced | **never built** | — |
| distillation loop | end-of-session, reviewed diff | `distill/SKILL.md` describes it; not run | 1 fetch |

**Three retrieval tiers this document describes as live are unpopulated**, and
until 2026-09-02 `SKILLS.md` linked all of them. The links are now removed rather
than left dead. Two consequences worth carrying into any redesign:

- **Demand is measurable and it did not match the design.** The single most
  requested missing document was `judgment/stopping.md` — asked for 8 times
  across 5 captures, by readers who could not decide whether a finished model was
  good enough. It has now been written. Nothing ever asked for a lesson card.
- **The tier that carries the traffic is not in this design at all.**
  `scene_to_pipeline.md` was written after it and absorbs the role `workflow/`
  was meant to play. Any redesign should start from that file's existence rather
  than from the six guides that were never written.

**Also corrected here:** this document's worked walkthrough previously called
`sfm_open_scene` and `judgment/triage.md`. Neither exists — the scene is loaded
by running `SceneLoader` like any other module, and triage guidance lives in
`scene_to_pipeline.md`.

## The layout this tier should have

The design below was written before `scene_to_pipeline.md` existed and before any
of it was exercised. What a seventeen-capture sweep measured suggests a different
organising principle, recorded here so the next reorganisation starts from
evidence rather than from the original sketch.

**Organise by the QUESTION a reader is holding, not by the kind of knowledge.**
The original split — mechanical `workflow/` versus subjective `judgment/` — is a
distinction about how a file was *authored*. A reader mid-run does not know or
care which they need; they know what has gone wrong. That is why `workflow/` was
never written and `scene_to_pipeline.md` was: the latter is keyed on a question
someone actually has.

The four questions the sweep showed readers actually asking, with what answers
them:

| The question, as readers phrased it | Answered by | Measured demand |
| --- | --- | --- |
| "What do these scene numbers mean for my plan?" | `scene_to_pipeline.md` | 36 fetches, all 17 captures |
| "Which member of this stage, for this scene?" | `families/<stage>.md` | 2-6 each, at most 6 captures |
| "Is this good enough, and is it actually right?" | `judgment/stopping.md`, `judgment/smells.md` | 8 requests before either existed |
| "How do I move this number?" | the module's `tuning`, reached from a diagnostic | 64 diagnostics route there |

**Two structural findings that should shape any reorganisation:**

- **The manifest is the surface, not the skill files.** `sfm_describe_module` was
  called 204 times against 70 for every per-module skill fetch combined, and it
  already inlines each module's `SKILL.md` and now each type's contract. Content
  that must reach every reader belongs there; content behind a separate fetch
  reaches whoever is already stuck.
- **Files are read when something compels them, not when something points at
  them.** 62 skill files are named by a diagnostic `see_also`; about seven were
  ever opened. The one file read on every single capture is the one a module
  refuses to complete without. Pointers are necessary and are not sufficient.

**What to do with the tiers that were never populated:**

- `workflow/` — **DONE, retired 2026-09-02.** The six guides were not written and
  will not be. Their content is already distributed across `scene_to_pipeline.md`
  (composition, traps), `judgment/stopping.md` (sweep mechanics), `families/`
  (choosing within a stage), and per-module `artifact` files plus the type contract
  (payload reading). The directory was deleted *and* the resolver's search path
  removed with it, because a path pointing at nothing is what manufactured the 24
  misses. `SKILLS.md` carries the redirect table so the retirement is discoverable
  rather than silent.
- `runs/` — **DONE, split 2026-09-02.** The trait table and the branch-comparison
  evidence table were sharing a file and answer incompatible questions: one wants a
  row you match your capture against, the other exists to be cited and explicitly
  must not be matched. They are now `runs/INDEX.md` and `runs/EVIDENCE.md`.
  **`INDEX.md` was populated on 2026-09-10**, on a different key than this
  document designs: observed capture kind from a `SceneDescription` reading
  rather than traits derived by thresholding. It was empty until then because
  the cut points this design assumes were never written, and the one that was
  published did not survive a refit. See
  [`context-structure-design.md`](../context-structure-design.md) §7.4.
- lesson cards and the distillation loop — never built, never requested, **held**.
  `distill/SKILL.md` describes a process that has never executed. The seed-from-
  the-sweep proposal was overtaken by a fact: the sweep's raw records were not
  preserved. The decided replacement (2026-09-07) is a **reference campaign** — a
  deterministic re-run of the corpus that seeds `evidence/` with durable
  per-capture rows and the reference values for the seven-rung health profile
  defined in `health/ladder.md`.

## Layout

**This listing is the DESIGN. `[built]` / `[EMPTY]` markers show what exists —
see the status table above.**

```
skills/
  SKILLS.md                        # [built] master index — always in context
  scene_to_pipeline.md             # [built] NOT IN THIS DESIGN. 81 KB, the most-read
                                   #   file in the tier; absorbed workflow/'s role
  judgment/                        # YOUR tacit knowledge. Human-authored, subjective.
    swap_or_build.md               # [built] NOT IN THIS DESIGN, and the one that gets read
    stopping.md                    # [built 2026-09-02] requested 8x before it existed
    triage.md                      # [NEVER BUILT] superseded by scene_to_pipeline.md
    tradeoffs.md                   # [built 2026-09-02] incl. the cost of a run that dies
    smells.md                      # [built 2026-09-02] right metrics, wrong conclusion
    priors.md                      # [built 2026-09-02] requested 3x before it existed
                                   # workflow/ WAS HERE and is [RETIRED]. Six guides
                                   #   were designed, none written, 24 requests and
                                   #   24 errors. Directory deleted and the resolver
                                   #   path removed. Do not restore either alone.
  modules/<ModuleName>/            # per-module — see module-skills.md
    SKILL.md · tuning.md · limitations.md · artifact.md · sources.md
  runs/                            # worked examples, the long-form references
    INDEX.md                       # [built 2026-09-10] 16 precedent rows keyed on
                                   #   OBSERVED capture kind; no measurements in it
    EVIDENCE.md                    # [built 2026-09-02] per-capture citation record,
                                   #   split out of INDEX.md. Cite it; never plan from it
    CORPUS.txt                     # [built] the captures every range is fitted on
    2026-08-07-dtu-scan1-sparse/   # [NEVER BUILT] no RUN.md corpus exists
      RUN.md                       #   [EMPTY]
      trace.json                   #   [EMPTY]
  distill/
    SKILL.md                       # the compaction procedure
```

Four tiers, and the ordering is deliberate:

| Tier | Answers | Authored by | Loaded |
| --- | --- | --- | --- |
| `judgment/` | "What would a practitioner do here? Is this good enough?" | **you**, by hand | digest always; full text on demand |
| ~~`workflow/`~~ **[RETIRED]** | "Which stage is my problem in? How do I approach this at all?" — a real question; this was not the answer. It is `scene_to_pipeline.md`. | curated + promoted lessons | — |
| `modules/<name>/` | "What does this tool do, and how do I move its numbers?" | curated + distilled lessons | `SKILL.md` with `describe_module`, rest on demand |
| `runs/` | "Has anyone solved a scene like this before? What did they do?" | run record + your narrative | on demand, via `INDEX.md` |

`workflow/` exists because a large share of real SfM knowledge is not
module-local. *"Matcher inlier yield below 0.15 means the tracker is not your
problem"* spans two modules and belongs to neither. Putting it in a module's
`tuning.md` would either duplicate it or arbitrarily assign it to one side.

**Cross-module guidance is advisory, never an ordering rule.** `workflow/`
documents describe where to look; the agent decides what to do and in what order.
If it tunes a tracker for three runs and only then concludes the matcher was at
fault, that is a legitimate path — and the episode it writes back is more valuable
than a rule that would have forbidden it.

## The judgment tier

Some of what makes an SfM practitioner effective is not in any paper and does not
follow from any metric. *When is a reconstruction good enough? Is 0.8px
reprojection error over 4,000 points better than 0.6px over 900? Does this scene
look like it will defeat classical matching before I have run anything?* That is
taste, it is subjective, and it needs a home that is honest about being
subjective — rather than being laundered into `workflow/` as if it were derived.

`judgment/` is that home. Its defining properties:

- **You write it, in your own voice, first person.** No source tags. The
  authority is that you have done this before, and saying so plainly is more
  useful to the agent than a fake citation.
- **Authoritative but non-binding.** The agent should weight these heavily and
  say when it is departing from one — but they are heuristics, not gates. This is
  consistent with leaving the stopping rule free: the guidance lives here as
  judgment rather than in `parameter_discipline.md` as a hard threshold.
- **Distillation may propose, never write.** Every other tier accretes
  automatically from runs. This one does not. A distillation pass that finds a
  candidate judgment lesson raises it as a suggested edit for you to accept,
  reword, or reject. It is your voice; the loop does not get to forge it.
- **Dated, and allowed to change its mind.** Taste evolves as the module set
  grows. Entries carry a date, and a revision **replaces** the old text outright —
  only the current view is kept. Superseded judgment is not archived inline; the
  file should read as what you think now, not as a changelog. (Git history is
  there if you ever need the old version.)

Example shape:

```markdown
---
topic: stopping
updated: 2026-08-11
---

## When a sparse reconstruction is good enough

I stop when reprojection error is under ~1px **and** the point count is within
about 2× of what the scene should plausibly support. Sub-0.5px error on 400
points is not a good reconstruction, it is an overfit one — the optimizer threw
away everything hard. I would rather have 0.9px on 6,000 points.

If I have run four sweeps and the target metric has moved less than ~5% total,
I stop tuning and change something structural. Not because 5% is a magic
number, but because past that point I have almost always been on the wrong
module rather than the wrong parameters.

## When to keep going anyway

If the scene is one I care about for the paper, and the current result is
merely *acceptable*, spend the GPU hours. The runs are cheap relative to
redoing the figure.
```

`SKILLS.md` — the only file always in context — carries a **digest** of this
tier: the one-line version of each entry with a link to the full document. That
way the agent always has the gist at decision points and can go deeper when it
matters, without paying for the whole tier every session.

The point of separating this from `workflow/` is that the two age differently and
have different authority. A `workflow/` claim is wrong when the evidence changes.
A `judgment/` claim is wrong when **you** change your mind — and nothing else
should be allowed to overwrite it.

## The worked-run corpus

> **SUPERSEDED 2026-09-10. Read
> [`docs/context-structure-design.md`](../context-structure-design.md) §7.4 for
> what was built.** Three things in the design below were tried and did not
> survive contact, and they are kept here as history rather than as a plan:
>
> - **`RUN.md` was never written and will not be.** The unit of evidence that
>   actually works is a **generated campaign file** under `skills/evidence/` —
>   per-capture rows, the image digests behind them, and a map from each derived
>   claim back to the rows supporting it. It is produced by a script from a run
>   record rather than narrated by hand, so it cannot drift from what happened,
>   which is the failure mode a hand-written narrative has by construction. Five
>   campaigns exist.
> - **Lesson cards were never built and were never asked for.** Across a
>   seventeen-capture sweep nothing requested one. The routing table below
>   survived the idea that produced it: the *questions* it routes are real, and
>   `skills/distill/SKILL.md` §8 carries the live version.
> - **Traits are not derived by thresholding, and the retrieval key is not
>   `scene_traits` as specified below.** The cut points this design assumes were
>   never written, because the evidence does not support naming them; the one
>   that was published was later refitted and withdrawn. `evidence/INDEX.md` is
>   keyed on **observed capture kind** from a `SceneDescription` reading, drawn
>   from a closed vocabulary the file itself defines.
>
> What did survive is the *shape* of the idea: a table of worked captures, matched
> by reasoning over recorded semantic traits rather than by embedding similarity,
> pointing at fuller records. That part is built and populated.

### `RUN.md` — the narrative

```markdown
---
run: 2026-08-11-eth-facade-sparse
dataset: ETH3D          scene: facade          images: 76
recon: sparse           calibrated: true       driver: claude, human-supervised
# derived from scene_analysis/v1, not hand-written — see scene-analysis.md
scene_traits: [outdoor, repetitive-texture, planar-dominant, wide-baseline]
modules: [FeatureDetectionSIFT, FeatureMatchFlannPair, FeatureTrackFromPairsUnionFind,
          FeatureTrackingVGGSfM, SparseSceneEstimationCOLMAPGlobal]
outcome: success-after-switch
runtime: 47min          gpu_hours: 0.6
lessons: [L-0061, L-0063, L-0064]
---

## What we were trying to do
...

## What happened
Classical path first: SIFT 4096 → FLANN → union-find. Tracks collapsed —
survival_ge_3 0.22 and it would not move across three sweeps ...

## Decision log
| # | Observed | Did | Result |
|---|----------|-----|--------|
| 1 | survival_ge_3 0.22 | max_keypoints 4096→8192 | 0.24. No. |
| 2 | inlier_yield 0.09  | RANSAC 1.0→3.0 | 0.26. Marginal. |
| 3 | plateau            | switched to VGGSfM direct tracker | 0.71. |

## What we'd do differently
The repetitive brick was visible in the input mosaic. Three sweeps were avoidable.

## Lessons distilled
- L-0061 → modules/FeatureTrackFromPairsUnionFind/limitations.md
- L-0063 → workflow/diagnosing_failures.md
- L-0064 → workflow/gotchas.md
```

`trace.json` is the machine record — every job, params, metrics, artifact ids,
durations — generated from the run DAG, not written by hand. Distillation reads
`trace.json` for facts and `RUN.md` for intent.

### Retrieval — reasoning, not embeddings

`runs/INDEX.md` is a table with the frontmatter fields above. The agent reads the
index, reasons about which rows resemble the scene in front of it (traits,
calibration, recon type, outcome), and opens two or three. This is what
interioragent does, and it beats embedding search here because the useful match is
*"outdoor, repetitive texture, wide baseline"* — semantic traits already written
down — not surface text similarity.

The markdown structure **is** the index. Decision-log tables, `##` headings, and
lesson-card blockquotes are parseable, which is what keeps new lessons findable.

## Lesson cards

The atomic unit. One observation, one takeaway, routed to exactly one file.

```markdown
> **L-0061 · Union-find tracking plateaus on repetitive facades**
> **Run:** the per-run record (superseded by `skills/runs/INDEX.md`)
> **Seen in:** 2 runs · **Confidence:** medium
> **Context:** ETH3D facade + courtyard, outdoor, repetitive texture, 70-90 images, calibrated.
> **Observed:** survival_ge_3 stuck at 0.22-0.26 across max_keypoints
> {4096, 8192, 16384} × RANSAC {1.0, 2.0, 3.0}. Matcher inlier_yield never above 0.09.
> **Takeaway:** two flat sweeps with inlier_yield below 0.10 is enough evidence
> to switch capability rather than keep tuning.
> **Untested:** indoor repetitive texture; sequences under 40 images.
```

Required fields, and why each earns its place:

| Field | Why |
| --- | --- |
| `Run` backlink | auditability — same discipline as `sources.md` |
| `Seen in` | a lesson from one run is a datapoint; from five it is a rule |
| `Confidence` | low / medium / high, driven by `Seen in` and breadth of context |
| `Context` | **the transfer test.** A DTU turntable number may not hold on ETH3D. Without context a card is a trap. |
| `Observed` | real numbers, real parameter values. No prose-only lessons. |
| `Takeaway` | the actionable sentence |
| `Untested` | explicit boundary — stops over-generalisation |

### Routing

Each card lands in exactly one file:

| Lesson is about | Goes to |
| --- | --- |
| moving one module's metrics with its own params | `modules/<name>/tuning.md` → Observed episodes |
| giving up on a module and switching | `modules/<name>/limitations.md` → Observed switches |
| interpreting or inspecting a module's output | `modules/<name>/artifact.md` |
| which stage is at fault given a symptom | ~~`workflow/diagnosing_failures.md`~~ → `scene_to_pipeline.md` §3 |
| a surprise, caveat, or footgun spanning modules | ~~`workflow/gotchas.md`~~ → `scene_to_pipeline.md` §3, "the traps, in the order they have bitten" |
| sweep mechanics (how to vary, what to hold fixed) | ~~`workflow/parameter_discipline.md`~~ → `judgment/stopping.md` |
| no module fits; one should be built | ~~`workflow/when_to_build_a_module.md`~~ → `judgment/swap_or_build.md` |
| a result that looks fine numerically and is not | `judgment/smells.md` |
| the raw per-capture numbers behind any of the above | `runs/EVIDENCE.md`, with scene names |
| a matter of taste — "good enough", worth the cost | **proposed** to `judgment/`, never written by the loop |

**The four struck rows are the retirement of `workflow/` reaching this table.**
The destinations changed; the routing question each row asks did not, which is
the evidence that those questions were real and the tier that was to answer them
was not. `skills/distill/SKILL.md` §8 carries the live version of this table.

**Promotion.** When the same lesson appears in three or more runs across
different modules or datasets, it graduates from a module's Observed section to
the cross-cutting file for that question — in practice `scene_to_pipeline.md` or
a `families/` file — and is rewritten as principle. Cards are never silently
deleted; the module file keeps a one-line pointer to where it went.

## The distillation skill

This is the thing you asked for: a procedure that compacts a long human-led
session into structured updates across the knowledge base. It lives at
`skills/distill/SKILL.md` and is invoked as a task, by you or by me, after a
session.

```
Input:  a run's trace.json (facts) + RUN.md draft or session transcript (intent)
Output: a reviewed diff across scene_to_pipeline.md, families/, modules/*/,
        runs/EVIDENCE.md, SKILLS.md
```

**Procedure**

1. **Reconstruct the trace.** Read `trace.json`, never memory. Every module
   invoked, every parameter, every metric, every duration. Facts come from the
   record; the transcript supplies only *why*.
2. **Segment into episodes.** An episode is one decision → action → observed
   outcome. A 40-step session is typically 6–12 episodes.
3. **Classify each episode:**
   - `tuning` — a parameter moved a metric (or didn't)
   - `switch` — abandoned a module for another
   - `gotcha` — surprising behaviour, silent failure, footgun
   - `gap` — nothing available did the job → new-module signal
   - `confirmation` — existing guidance held (increments `Seen in`, no new card)
   - `noise` — incidental, discard
4. **Draft a card per keeper episode**, with all required fields. Numbers from
   `trace.json`, context from the run frontmatter.
5. **Dedupe.** Match against existing cards by (module, metric, direction of
   change). If it already exists: increment `Seen in`, widen `Context`, raise
   `Confidence`, extend `Untested` — do **not** append a near-duplicate. This is
   what keeps the corpus from bloating into unusable length.
6. **Route** per the table above.
7. **Check promotion** — any card now at `Seen in: 3+` gets flagged for
   graduation out of the module file into the cross-cutting file for the question
   it answers: `scene_to_pipeline.md` for a symptom-to-stage claim, a `families/`
   file for a within-stage trade, `judgment/` for a call about taste (proposed,
   never written).
8. **Validate** — every metric named exists in the module's manifest, every
   escape resolves to a capability query with at least one live module, every
   link resolves, `SKILLS.md` and `runs/INDEX.md` updated.
9. **Report the diff for review.** Distillation proposes; a human accepts. The
   corpus is the system's long-term memory and should not accrete unreviewed.

**What it must capture** — directly from your list, mapped to routing:

| You said | Card type | Destination |
| --- | --- | --- |
| what tools worked | `confirmation` / `tuning` | module `tuning.md` |
| what didn't | `switch` | module `limitations.md` |
| what to create, why | `gap` | `judgment/swap_or_build.md` |
| how to optimize parameters | `tuning` | module `tuning.md` |
| limitations of specific tools | `switch` | module `limitations.md` |
| surprises, gotchas, caveats | `gotcha` | `scene_to_pipeline.md` §3 |

**Anti-goals.** No summarising for its own sake — a card that says "SIFT worked
well" with no numbers, context, or takeaway is worse than nothing, because it
costs context and answers nothing. If an episode cannot produce a card with all
required fields, it is `noise`.

## How this changes the agent loop

```
read SKILLS.md (index + judgment digest)
      │
      ├─ sfm_run(SceneLoader) → scene/v1   (there is no sfm_open_scene)
      ├─ sfm_run(SceneMotion) → scene_analysis/v1 → TRAITS   see scene-analysis.md
      ├─ scene_to_pipeline.md → what those traits imply (no judgment/triage.md)
      ├─ runs/INDEX.md by observed capture kind            "has this been solved?"
      │                                (SceneDescription supplies the key, not thresholds)
      ├─ families/<stage>.md + scene_to_pipeline.md         "what shape of pipeline?"
      │                                (workflow/pipeline_principles.md was retired)
      ├─ sfm_list_modules(produces=...) + describe_module    "which tools?"
      │
      └─ run → metrics + diagnostics(see_also) ─┐
                                                 │
            ┌────────────────────────────────────┘
            ├─ tuning.md: principled gradient + observed episodes → adjust, re-run
            ├─ upstream suspect? sfm_replay(from_artifact, overrides) → new branch
            ├─ good enough? judgment/stopping.md · judgment/smells.md
            ├─ stuck? limitations.md + scene_to_pipeline.md §3
            ├─ still stuck? sfm_find_alternatives(...) → different module
            └─ nothing fits? judgment/swap_or_build.md → scaffold + build
      │
      └─ session ends ─► distill ─► reviewed diff into the corpus
                                    (judgment/ edits proposed, not applied)
```

The loop closes. Each session leaves the corpus better than it found it, and the
next session starts from a real prior instead of from the papers alone.

## Resolved

**`sfm_replay` — adopted.** `sfm_replay(from_artifact, overrides)` re-executes the
recorded downstream chain from a given point, reusing each step's previously-used
parameters except where overridden. Upstream changes will be frequent, and making
one cost a single call instead of five is the difference between the agent
exploring upstream freely and avoiding it.

**No staleness flagging — surface lineage instead.** I raised this and I now think
it was wrong. "Stale" implies the newer branch supersedes the older one, and that
is a value judgment the orchestrator cannot make: re-running an upstream module
with different parameters often produces a *worse* result. Both branches are
equally valid records.

So: nothing is ever marked stale. What the orchestrator does instead is surface
**lineage divergence at comparison time** — when `sfm_compare` is given two
artifacts, it reports where their ancestry differs:

```
sparse_A   ← tracks_A   ← pairs_A ← features_A (SIFT max_keypoints=4096)
sparse_B   ← tracks_B   ← pairs_A ← features_A
                            ^ diverges at tracks: min_track_len 2 → 3
```

That is strictly more useful than a staleness flag and carries no implied
judgment. It also stops the agent silently comparing two results whose difference
came from three stages up rather than the parameter it thinks it changed.

**Stopping rule — no hard threshold.** The agent decides freely. The judgment
that would have gone into `workflow/parameter_discipline.md` as a rule instead
lives in `judgment/stopping.md` as your stated practice, which the agent consults
and may depart from with reason. `parameter_discipline.md` keeps only the
mechanical part: vary one thing at a time, hold the scene fixed, record the
baseline first.

**Distillation cadence — after every run, for now.** All sessions are human-led
during corpus construction, so every run carries signal. Later, when autonomous
runs start, this becomes gated: distillation produces the diff and waits for
review before applying.

**Confidence — evidence-based, not provenance-based.** Since every lesson is
human-led or human-reviewed, provenance no longer discriminates between cards.
`Confidence` therefore tracks **evidence breadth alone**: how many runs, how many
distinct scenes, how many datasets, and whether the contexts were similar or
varied. A card seen three times on three DTU scans is weaker than one seen twice
across DTU and ETH3D, and the field should say so.

**Superseded judgment — replace, do not archive.** A revision overwrites the
entry. `judgment/` reads as your current view; git carries the history.

**Runs are Claude-driven, human-supervised.** You set the goal and review; I do
the tool-calling. Distillation runs after every session and reports a diff for
your review. There is no config-driven CLI — the MCP surface is the only entry
point.

## Open question

**Judgment digest size.** `SKILLS.md` is always in context, so the `judgment/`
digest has a real budget. One line per entry under topic headings — keeping the
whole index under ~100 lines — or a short paragraph per topic? I lean the former,
with the full documents one tool call away.
