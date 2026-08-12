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
2. **A measured table**, with the scene stated.
3. **What each end is for**, in terms a scene's traits can be matched against.
4. **What has NOT been measured**, explicitly. This tier is worth more for being
   honest about its coverage than for being complete.

## Status

| Family | File | Evidence |
| --- | --- | --- |
| Feature detection | — | not written |
| Feature matching | — | not written |
| Feature tracking | [tracking.md](tracking.md) | one scene (DTU scan1), all three trackers |
| Pose estimation | — | not written |
| Sparse reconstruction | — | not written; data exists from module bring-up |
| Optimization | — | not written |
| Dense reconstruction | — | not written; data exists from module bring-up |

Empty files are deliberately absent rather than stubbed. A stub invites being
filled with a guess, and a guess here is worse than a gap: it is read at the
moment nothing has been measured yet.

## Recording protocol

**Nothing is written here without being asked for first.** A finding that looks
like a family-level trade is proposed, reviewed, and only then recorded. That
holds during module bring-up; the agent-driven sessions will define their own
process.

Every entry states its scene, so a reader can weigh it. A single-scene finding
says so in its own heading.
