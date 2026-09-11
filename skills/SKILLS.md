# sfmstack — Knowledge Index

The only file always in context. Everything else is one tool call away, and the
tree is organised by **the moment you are standing in**, because that is the one
thing you always know about yourself:

| Moment | Tier | Answers | Reach it via |
| --- | --- | --- | --- |
| **before anything runs** | [plan/](plan/) | "what do this capture's numbers imply, and which member of each stage?" | `sfm_plan_brief` bundles the guide and the stage files; or `sfm_workflow_skill("plan/<topic>")` |
| **a run finished, numbers in hand** | [judge/](judge/) | "tuning stopped paying — swap, build, or spend more?" | `sfm_workflow_skill("judge/swap_or_build")`, `("judge/tradeoffs")` |
| **a sparse model exists** | [health/](health/) | "is this reconstruction healthy? if not — fixable, or bounce to build?" | the run summary's health digest anchors here; `sfm_workflow_skill("health/ladder")`, `("health/smells")`, `("health/bounce")` |
| **checking or citing a claim** | [evidence/](evidence/) | "where did this claim come from, and how much is it worth?" | `sfm_workflow_skill("evidence/EVIDENCE")`; campaign files beside it |
| **any module, any moment** | `modules/` | "what does this tool do, and how do I move its numbers?" | `sfm_describe_module`, `sfm_module_skill` |
| **session ends** | [distill/](distill/) | "I learned something — what shape does it get written in?" | `sfm_workflow_skill("distill/SKILL")` |
| — | `docs/` | the design record and full experiment write-ups | `sfm_workflow_skill("import_lessons")`, `("design/DECISIONS")` |

**Every path in this table is reachable by a call.** If a link in any skill file
resolves to a path `sfm_workflow_skill` cannot reach, that is a defect worth
reporting.

## plan/ — before anything runs

- **[scene_to_pipeline.md](plan/scene_to_pipeline.md)** — how to read a capture's
  measured numbers into a plan: what each metric decides, the observed ranges and
  what corpus scopes them, the traps in the order they have bitten. The most-read
  file in the tier, and `sfm_plan_brief` returns it with the analysis it reads.
- **One stage file per family** — the axis each stage trades along, what each end
  is for keyed on metrics available *before* the choice, and what has not been
  measured: [detection](plan/detection.md) · [matching](plan/matching.md) ·
  [tracking](plan/tracking.md) · [pose](plan/pose.md) · [sparse](plan/sparse.md) ·
  [optimization](plan/optimization.md) · [dense](plan/dense.md)

Stage files are structural, none quantified; each ends with what it would take to
put numbers on it. A measured table may be added only with its scene count stated,
and **nothing is recorded here without being asked for first**. Scene analysis has
no stage file — the trade (appearance from a CPU pass against geometry from a GPU
one) has not been asked for; the two modules' own `SKILL.md` files carry it.

## judge/ — a run finished, and the numbers are in hand

- **[swap_or_build.md](judge/swap_or_build.md)** — when tuning stops and the
  module is the problem; when nothing in the registry fits at all. Organised by
  family. *Honest that most of it is structural rather than measured.*
- **[tradeoffs.md](judge/tradeoffs.md)** — what actually costs time, when to spend
  it, and the axis normally left out: the cost of a run that dies partway.

## health/ — a sparse model exists

- **[ladder.md](health/ladder.md)** — when a result is good enough. The objective
  (as much structure as possible from a model you have reason to trust), the
  constraint ladder, the **seven-rung health profile** the run summary reports
  against the reference corpus, the procedure for comparing two models, and when
  to stop turning a dial.
- **[smells.md](health/smells.md)** — results that look fine numerically and are
  wrong. Every entry is a case where the metrics were individually correct and the
  conclusion drawn from them was not.
- **[bounce.md](health/bounce.md)** — when an unhealthy model means BUILD: the
  weakest rung of the health profile, low and immobile across the swaps and sweeps
  already tried. Hands off to `judge/swap_or_build` §BUILD. *Skeleton until the
  reference campaign runs.*

> judge/ and health/ are human-authored, subjective, authoritative but
> non-binding. Say when you depart from one. Distillation may *propose* edits
> there; it never writes them.

## evidence/ — the record

- **[EVIDENCE.md](evidence/EVIDENCE.md)** — the index of campaigns, and the
  reliability ladder: when two pieces of this corpus disagree, which to believe.
  One file per campaign beside it, raw per-capture tables with scene names —
  **cite, never match**. [INDEX.md](evidence/INDEX.md) is the opposite file and
  the one to match against: one row per worked capture, keyed on observed
  capture kind, carrying no measurements and naming the move that decided each
  one. [CORPUS.txt](evidence/CORPUS.txt) pins what every quoted range was fitted
  on — and every INDEX row is a member of it, so check `in_planning_corpus`
  before treating a match as retrieval.

Scene names live in this tier and nowhere else; every claim elsewhere describes
the *scenario*. Trait thresholds are nowhere: the analysis modules emit numbers,
`plan/scene_to_pipeline.md` says how to read them, and judge/ and health/ say
what to do once you have.

## Retired names

The tree was reorganised from knowledge-kind tiers (`families/`, `judgment/`,
`runs/`) into the moment tiers above. Any pre-reorganisation topic still
resolves — `sfm_workflow_skill` redirects it silently to the file's current
home — but nothing should cite the old names: use the paths in this file.

**`skills/workflow/` no longer exists and must not be recreated.** Across a
seventeen-capture sweep it was requested 24 times and raised every time — a tier
that is only ever an error is worse than no tier. Its planned content settled
where readers actually stand: composing a pipeline and cross-stage surprises →
`plan/scene_to_pipeline.md` (§3 for the traps); sweep mechanics and when to stop →
`health/ladder.md`; reading an artifact → the module's `artifact` skill plus the
type contract `sfm_describe_module` returns; nothing fits → `judge/swap_or_build`;
looks fine but is not → `health/smells`. The resolver's search path was removed
with the directory; do not add either back without the files.

## Loop

```
SKILLS.md (this file)
  ├─ sfm_run(SceneLoader) → scene/v1
  ├─ sfm_run(SceneTriage), sfm_run(SceneMotion)     → scene_analysis/v1, measured
  ├─ sfm_run(SceneDescription) ×2 + sfm_artifact_image ×3   → asserted
  │
  ├─ sfm_plan_brief(scene)         ONE call, and it gathers:
  │    ├─ the analysis above       metrics, diagnostics, narrative
  │    ├─ plan/scene_to_pipeline   how to READ those numbers
  │    ├─ plan/<stage>.md          which member of each stage, and why
  │    └─ sfm_list_modules(...)    the live menu
  │  → you write the plan. The tool prepares; it does not decide.
  │
  ├─ evidence/INDEX by capture kind has this been solved, and by what move?
  │
  └─ run → metrics + diagnostics(see_also)
        ├─ tuning.md              principled gradient + observed episodes
        ├─ sfm_replay(...)        suspect upstream? branch the DAG
        ├─ judge/swap_or_build    tuning stopped — now what?
        ├─ limitations.md         stuck? what this module cannot do
        └─ produces sparse_model/v1 →
              health digest in the run summary (seven rungs vs the reference corpus)
                ├─ health/ladder   good enough? stop the sweep?
                ├─ health/smells   looks fine — is it?
                └─ health/bounce   weakest rung immobile → BUILD
  │
  └─ session ends → distill → reviewed diff (judge/ & health/ proposed, not applied)
                              see distill/SKILL.md for the SHAPE to write in
```

## Writing new context

**[distill/SKILL.md](distill/SKILL.md)** — what to record after a session and what
shape to record it in. Selection and tuning context need different shapes; a
metric claim owes a denominator; the evidence is a shape, never a cut point. Its
§9 carries the recording protocol for the planning guide and the stage files.

**Read it as a specification, not as a description of what happens.** The loop it
defines has never executed: every line of context in this tree was written by
hand, so a claim's age is the age of the last person who looked at it.

**One review rule replaces the per-module boilerplate:** re-check a module's
claims when its version changes, when a capture unlike the corpus arrives, or
when a reading crosses a band with nothing firing. This used to be printed in all
28 `sources.md` files; it is the same rule everywhere and it lives here now.

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
