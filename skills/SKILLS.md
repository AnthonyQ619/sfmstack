# sfmstack — Knowledge Index

The only file always in context. Everything else is one tool call away.

Design: [../docs/design/knowledge-system.md](../docs/design/knowledge-system.md).

## Tiers

| Tier | Answers | Reach it via |
| --- | --- | --- |
| [judgment/](judgment/) | "What would a practitioner do? Is this good enough?" | digest below; full text on demand |
| [workflow/](workflow/) | "Which stage is my problem in? How do I approach this?" | by topic |
| [families/](families/) | "I know I need a tracker — which one, for this scene?" | [families/README.md](families/README.md) |
| [modules/](modules/) | "What does this tool do, and how do I move its numbers?" | `sfm_describe_module`, `sfm_module_skill` |
| [runs/](runs/) | "Has a scene like this been solved before?" | `sfm_workflow_skill("runs/INDEX")` |
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
  stop turning a dial. *Written.* The objective is as much structure as possible
  from a model you have reason to trust, and it carries the constraint ladder and
  the model-comparison procedure that go with that.
- **priors** — which module families to trust, and where. *Not written, and the
  link has been removed rather than left dead.* What exists of this is inside
  [`families/`](families/) per stage and in
  [`judgment/swap_or_build.md`](judgment/swap_or_build.md); note that the family
  files' predictive claims about which branch wins are the part of this corpus
  that has failed most often, so a `priors` file written today would mostly be
  recording that the question is open.

Three files were planned here and cut. `triage.md` was to hold what to read off a
scene before running anything — that is now
[scene_to_pipeline.md](scene_to_pipeline.md), which carries the measured ranges
behind each call and is reached through `sfm_plan_brief`. `smells.md` duplicated
material already spread through `families/` and the modules' own `tuning.md`, and
a second copy of a claim is a second place for it to go stale. `tradeoffs.md`
never earned a page of its own.

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

## Workflow guides

**Not written. Nothing here is fetchable, and the six titles this section used to
list have been removed rather than left as links.** They were requested 24 times
across a seventeen-capture sweep, each request raising rather than returning a
miss, and the `Available:` list that came back with the error did not name the
documents that *do* exist — so a reader who followed one pointer concluded the
whole tier was gone.

Where their content currently lives, until this tier is written:

- composing a pipeline, and which stage a symptom belongs to →
  [`scene_to_pipeline.md`](scene_to_pipeline.md) and
  [`families/README.md`](families/README.md)
- sweep mechanics and when to stop turning a dial →
  [`judgment/stopping.md`](judgment/stopping.md)
- reading an artifact and each payload type → each module's `artifact` skill
- surprises not attributable to one module → `scene_to_pipeline.md` §3, "the
  traps, in the order they have bitten"
- signals that nothing existing fits →
  [`judgment/swap_or_build.md`](judgment/swap_or_build.md)

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
  ├─ runs/INDEX.md by trait        has this been solved?          [EMPTY]
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
