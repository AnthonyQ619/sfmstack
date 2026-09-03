# sfmstack — Knowledge Index

The only file always in context. Everything else is one tool call away.

Design: [../docs/design/knowledge-system.md](../docs/design/knowledge-system.md).

## Tiers

| Tier | Answers | Reach it via |
| --- | --- | --- |
| [judgment/](judgment/) | "What would a practitioner do? Is this good enough?" | digest below; full text on demand |
| [families/](families/) | "I know I need a tracker — which one, for this scene?" | [families/README.md](families/README.md) |
| [modules/](modules/) | "What does this tool do, and how do I move its numbers?" | `sfm_describe_module`, `sfm_module_skill` |
| [runs/](runs/) | "Has a scene like this been solved before?" (INDEX, still empty) and "where does this claim come from?" (EVIDENCE) | `sfm_workflow_skill("runs/INDEX")`, `sfm_workflow_skill("runs/EVIDENCE")` |
| `docs/` | "Where are the numbers behind a claim, and what was actually run?" | `sfm_workflow_skill("import_lessons")`, `sfm_workflow_skill("design/DECISIONS")` |

**Every path in this table is reachable by a call**, and that has not always been
true. The family files and module skills cite `docs/import_lessons.md` and
`docs/design/DECISIONS.md` repeatedly as where the per-capture magnitudes and the
full experiments live, and until recently neither could be fetched by any means a
reader had — so every quoted range arrived with no way to check its scope. A reader
who cannot follow a citation is being shown evidence they cannot examine, which is
worse than a claim with no citation at all. If a link in any skill file resolves to
a path you cannot reach with `sfm_workflow_skill`, that is a defect worth
reporting.

## Judgment digest

> Human-authored, subjective, authoritative but non-binding. Say when you depart
> from one. Distillation may *propose* edits here; it never writes them.

- **[swap_or_build](judgment/swap_or_build.md)** — when tuning stops and the
  module is the problem; when nothing in the registry fits at all. Organised by
  family. *Written, and honest that most of it is structural rather than measured.*
- **[stopping](judgment/stopping.md)** — when a result is good enough; when to
  stop turning a dial. The objective is as much structure as possible from a
  model you have reason to trust, with the constraint ladder and the
  model-comparison procedure.
- **[smells](judgment/smells.md)** — results that look fine numerically and are
  wrong. Every entry is a case where the metrics were individually correct and
  the conclusion drawn from them was not.
- **[priors](judgment/priors.md)** — which parts of THIS corpus to trust when
  they disagree with each other or with your reading. Mechanism claims held up
  across seventeen captures; predictive "X beats Y" claims failed six times.
- **[tradeoffs](judgment/tradeoffs.md)** — runtime against quality; what actually
  costs time, when to spend it, and the cost of a run that dies partway.
- **triage** — *not a file.* What to read off a scene before running anything is
  [`scene_to_pipeline.md`](scene_to_pipeline.md), which carries the measured
  ranges behind each call and is reached through `sfm_plan_brief`.

**This tier is complete.** One planned file was cut rather than written:
`triage.md`, which was to hold what to read off a scene before running anything.
That is [scene_to_pipeline.md](scene_to_pipeline.md), which carries the measured
ranges behind each call and is reached through `sfm_plan_brief` — so the entry
above points at it by name rather than leaving a link that resolves to nothing.

`smells.md` and `tradeoffs.md` were cut once for the reasons that used to be
printed here — that they duplicated `families/` and that they had not earned a
page — and both reasons turned out to be wrong. The material that became
`smells.md` was not a duplicate: every entry is a case where each metric was
individually correct and the conclusion drawn from them was not, which is a claim
about *reading* and had no home in a file organised by stage. And the cost of a
run that dies partway, which is most of `tradeoffs.md`, appeared in no file at
all. A tier is not finished because its remaining topics look small.

**Trait thresholds are NOT here any more.** The analysis modules emit numbers and
`scene_to_pipeline.md` says how to read them; this tier says what to do once you
have.

## Family comparisons

> Measured, not judged. One file per stage, holding the axis that stage trades
> along and the evidence for it. Read before running anything, beside
> `scene_to_pipeline.md`. Nothing is recorded here without being asked for first.

- **[detection.md](families/detection.md)** — invariance by construction or by
  training; the descriptor type decides the matcher; coverage beats count
- **[matching.md](families/matching.md)** — detector-based or detector-free, and
  that choice reaches forward into how the tracker must merge
- **[tracking.md](families/tracking.md)** — track length and positional precision
  move in opposite directions
- **[pose.md](families/pose.md)** — geometric or feed-forward; and a third option
  that skips the stage entirely
- **[sparse.md](families/sparse.md)** — ray intersection or a learned prior; poses
  as input or as output; the scale a prior carries
- **[optimization.md](families/optimization.md)** — scope against cost, and the
  trap that error is never comparable across differing model sizes
- **[dense.md](families/dense.md)** — verification against prediction; holes are
  the honest part

All structural, none quantified. Each file ends with what it would take to put
numbers on it.

## The retired workflow tier

**`skills/workflow/` no longer exists, and this section is here so nothing tries
to recreate it.** Six cross-cutting stage guides were designed for it and none was
ever written. Across a seventeen-capture sweep it was requested 24 times, and every
request raised rather than returned — a tier that is only ever an error is worse
than no tier, because a reader who follows one pointer into a miss concludes the
whole knowledge base is gone, and one said so in writing.

The diagnosis is not that nobody got around to it. The original split was
`workflow/` for the mechanical half and `judgment/` for the subjective half, which
is a distinction about **who authored a claim**, not about **what question a reader
is holding**. A reader with a broken reconstruction does not know or care which
half their answer lives in; they know what went wrong. Organised that way, the
mechanical half had nowhere natural to go and its content settled where readers
were already standing:

| The question that sent readers to `workflow/` | Where it is answered |
| --- | --- |
| composing a pipeline; which stage a symptom belongs to | [`scene_to_pipeline.md`](scene_to_pipeline.md), [`families/README.md`](families/README.md) |
| sweep mechanics, and when to stop turning a dial | [`judgment/stopping.md`](judgment/stopping.md) |
| a surprise spanning modules | `scene_to_pipeline.md` §3, "the traps, in the order they have bitten" |
| reading an artifact and each payload type | each module's `artifact` skill, plus the type contract `sfm_describe_module` now returns |
| signals that nothing existing fits | [`judgment/swap_or_build.md`](judgment/swap_or_build.md) |
| a result that looks fine and is not | [`judgment/smells.md`](judgment/smells.md) |

The search path was removed with the directory, so `sfm_workflow_skill` no longer
looks under `workflow/` for a bare topic. **Do not add the path back without the
files**; that combination is what produced the 24 misses.

## Loop

```
SKILLS.md (this file)
  ├─ sfm_run(SceneLoader) → scene/v1
  ├─ sfm_run(SceneTriage), sfm_run(SceneMotion)     → scene_analysis/v1, measured
  ├─ sfm_run(SceneDescription) ×2 + sfm_artifact_image ×3   → asserted
  │
  ├─ sfm_plan_brief(scene)         ONE call, and it gathers:
  │    ├─ the analysis above       metrics, diagnostics, narrative
  │    ├─ scene_to_pipeline.md     how to READ those numbers — measured ranges,
  │    │                           what each cannot tell you, the known traps
  │    ├─ families/<stage>.md      which member of each stage, and why
  │    └─ sfm_list_modules(...)    the live menu
  │  → you write the plan. The tool prepares; it does not decide.
  │
  ├─ runs/INDEX.md by trait        has this been solved?      [NO ROWS YET]
  ├─ runs/EVIDENCE.md              where did this claim come from?
  ├─ judgment/swap_or_build.md     tuning stopped - now what?
  │
  └─ run → metrics + diagnostics(see_also)
        ├─ tuning.md          principled gradient + observed episodes
        ├─ sfm_replay(...)    suspect upstream? branch the DAG
        ├─ judgment/stopping  good enough? when to stop a sweep
        ├─ limitations.md     stuck? what this module cannot do
        └─ sfm_find_alternatives(...) or scaffold a new module
  │
  └─ session ends → distill → reviewed diff (judgment/ proposed, not applied)
                              see distill/SKILL.md for the SHAPE to write in
```

## Writing new context

**[distill/SKILL.md](distill/SKILL.md)** — what to record after a session and what
shape to record it in, so an agent reading it cold reaches the same decision for the
same reason. Selection context and tuning context need different shapes; a metric
claim owes a denominator; the evidence is a shape, never a cut point. Read it before
adding to any file below.

**Read it as a specification, not as a description of what happens.** The loop it
defines has never executed: every line of context in this tree was written by hand.
That does not make its rules wrong — they are the rules the hand-written edits were
held to — but nothing automatic is maintaining any of this, so a claim's age is the
age of the last person who looked at it.

## Conventions

- Cross-module guidance is an **advisory pointer**, never an ordering rule. A
  module's skills never dictate what to do first.
- `limitations.md` escapes name a **capability**, never a module — "something
  producing `tracks/v1` that doesn't consume `pairwise_matches/v1`", not "LoFTR".
  Module names go stale; capability queries resolve against the live registry.
- Every quantitative claim in a *principled* section carries a source tag.
  Every *observed* card carries a run backlink, scene context, and confidence.
- Confidence tracks **evidence breadth** — how many runs, scenes, datasets — not
  who ran them. Everything here is human-led or human-reviewed.
