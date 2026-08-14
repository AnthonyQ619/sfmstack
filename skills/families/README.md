# families/ — choosing WITHIN a stage

**Answers:** "I know I need a tracker. Which one, for this scene?"

The tier that was missing. The others cannot hold this:

| Tier | Why not this |
| --- | --- |
| `modules/` | Per module. A module's skills describe that module; none of them can say how it compares, and none of them should — a module advertising its own superiority is not evidence. |
| `judgment/` | Human-authored and subjective. This is measured. |
| `runs/` | One scene's episode. This is a family-level trade that generalises across scenes, or is explicit about not doing so. |
| `workflow/` | "Which stage is my problem in", not "which member of this stage". |

Read **before running anything**, alongside `judgment/triage.md` and the scene's
traits, when composing a pipeline. That is the point: a comparison you can only
make after running all the candidates is not a selection aid.

## What a family file holds

1. **The axis or axes the family trades along** — the thing that is structurally
   true and does not depend on the dataset.
2. **What each end is for**, keyed on metrics available *before* the choice is
   made, so it can be read while planning rather than after running everything.
3. **What has NOT been measured**, and what evidence each open question needs.

A **measured table** may be added to any of those, and must state its scene. One
scene's numbers are not a pass-down: they say what happened once, and a reader
cannot tell from them what will happen on their own capture. Structure generalises;
magnitudes do not until several scenes agree.

## Status

One file per stage of the pipeline, because each stage is a family.

| Family | File | Produces |
| --- | --- | --- |
| Feature detection | [detection.md](detection.md) | `features/v1` |
| Feature matching | [matching.md](matching.md) | `pairwise_matches/v1` |
| Feature tracking | [tracking.md](tracking.md) | `tracks/v1` |
| Pose estimation | [pose.md](pose.md) | `poses/v1` |
| Sparse reconstruction | [sparse.md](sparse.md) | `sparse_model/v1` |
| Optimization | [optimization.md](optimization.md) | `sparse_model/v1` |
| Dense reconstruction | [dense.md](dense.md) | `dense_model/v1` |

Scene analysis now has two modules — `SceneTriage` and `SceneMotion`, both
producing `scene_analysis/v1` — and still has no file here, because of the
recording protocol below: it has not been asked for. The trade is a real one and
worth a file eventually (appearance from a CPU pass against geometry from a GPU
one, and what each can see that the other cannot). Until then the two modules'
own `SKILL.md` files carry it, and each names the other.

**Everything currently written here is structural and nothing is quantified.** The
axes follow from where each family's numbers come from, not from any dataset, and
the guidance is keyed on upstream metrics available *before* the choice is made.
Every file ends with what it would take to put numbers on it — that section is the
map of what is still unknown, and it is the more useful half today.

## Recording protocol

**Nothing is written here without being asked for first.** A finding that looks
like a family-level trade is proposed, reviewed, and only then recorded. That
holds during module bring-up; the agent-driven sessions will define their own
process.

Every entry states its scene, so a reader can weigh it. A single-scene finding
says so in its own heading.
