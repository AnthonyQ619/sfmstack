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
| [runs/](runs/) | "Has a scene like this been solved before?" | [runs/INDEX.md](runs/INDEX.md) filtered by trait |

## Judgment digest

> Human-authored, subjective, authoritative but non-binding. Say when you depart
> from one. Distillation may *propose* edits here; it never writes them.

*Empty — to be written. One line per entry, full text in the linked file.*

- **[triage](judgment/triage.md)** — what to read off a scene before running anything
- **[stopping](judgment/stopping.md)** — when a result is good enough; when to stop tuning
- **[tradeoffs](judgment/tradeoffs.md)** — runtime vs quality; when GPU hours are worth spending
- **[smells](judgment/smells.md)** — results that look fine numerically and are wrong
- **[priors](judgment/priors.md)** — which module families to trust, and where

Trait thresholds live here too: the analysis modules emit numbers, and
`judgment/` decides what counts as "narrow baseline" or "repetitive texture".

## Family comparisons

> Measured, not judged. One file per stage, holding the axis that stage trades
> along and the evidence for it. Read before running anything, beside
> `judgment/triage.md`. Nothing is recorded here without being asked for first.

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

*Empty — to be written.*

- [pipeline_principles.md](workflow/pipeline_principles.md) — how to compose a pipeline
- [diagnosing_failures.md](workflow/diagnosing_failures.md) — symptom → which stage is at fault
- [parameter_discipline.md](workflow/parameter_discipline.md) — sweep mechanics
- [artifact_guide.md](workflow/artifact_guide.md) — reading `artifact.md` and each payload type
- [gotchas.md](workflow/gotchas.md) — surprises not attributable to one module
- [when_to_build_a_module.md](workflow/when_to_build_a_module.md) — signals nothing existing fits

## Loop

```
SKILLS.md (this file)
  ├─ sfm_open_scene → scene/v1     (+ SceneTriage auto-run)
  ├─ sfm_run(SceneMotion) → scene_analysis/v1 → TRAITS
  ├─ judgment/triage.md            what those traits imply
  ├─ runs/INDEX.md by trait        has this been solved?
  ├─ families/<stage>.md           which member of each stage, and why
  ├─ sfm_list_modules(produces=…)  candidate pipeline
  │
  └─ run → metrics + diagnostics(see_also)
        ├─ tuning.md          principled gradient + observed episodes
        ├─ sfm_replay(...)    suspect upstream? branch the DAG
        ├─ judgment/stopping  good enough?
        ├─ limitations.md     stuck? + workflow/diagnosing_failures.md
        └─ sfm_find_alternatives(...) or scaffold a new module
  │
  └─ session ends → distill → reviewed diff (judgment/ proposed, not applied)
```

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
