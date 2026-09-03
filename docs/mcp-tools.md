---
name: mcp-tools
description: The 19 MCP tools and the exact files each one reads or writes. Where the agent's context comes from, and which tools are currently blocked on the empty knowledge tiers.
status: current as of 2026-08-16
---

# The tools and their context

Nineteen tools in five groups. The count does not grow with the module count —
modules are *discovered* through `sfm_list_modules` / `sfm_describe_module`, never
enumerated as tools, so this surface is the same at 2 modules and at 200.

It grows, rarely, on two other axes.

The number of **payload kinds** the surface can carry: `sfm_artifact_image` was
the eighteenth, added 2026-08-15 — artifacts could always hold pictures and there
was no way to hand one back, so anything that needed looking at required
filesystem access outside this protocol.

And a **step of the loop with no tool behind it**: `sfm_plan_brief` is the
nineteenth, added 2026-08-16. Choosing the first pipeline was the step where the
agent was most on its own — the type system says what *can* follow and the family
files say what *should*, and nothing joined either to the numbers step 2
produces. Measured: of the 29 metrics the three analysis modules emit, exactly
two are named anywhere in `skills/families/`.

Every tool's context comes from one of four stores. Knowing which one answers
"why does the agent know this" and, more usefully, "why does it not".

---

## 1. The four stores

### A. Module manifests — `modules/*/module.yaml`

28 files. Loaded once at server start by `ModuleRegistry.load_dir`, and again on
`sfm_reload_modules`. Each one carries the module's whole machine contract:
identity, image tag, resources, input and output slots with payload types, the
full parameter schema with defaults / ranges / enums / per-parameter `tuning`
notes, every metric with its `direction` / `healthy` band / `meaning`, and every
diagnostic with its `severity` / `suggested_actions` / `see_also`.

**This is the only store consulted by every tool group.** Type checking, capability
queries, parameter validation, cache-key computation and image builds all read it.

### B. Type schemas — `packages/sfmkit/src/sfmkit/types/*.yaml`

Eight files, one per payload type. They declare the file groups and arrays a
payload must carry, and the metrics a producer is *required* to emit with a fixed
`direction`.

Read at registry load — a module whose manifest omits a required metric fails
there, before any container starts — and again inside the producing container at
seal time, where the actual arrays are validated.

**The agent never fetches these directly.** There is no `sfm_describe_type`. What
reaches the agent is their consequence: the types in `consumes` / `produces`, and
the refusal message when a slot is wired wrong.

### C. Curated knowledge — `modules/*/skills/*.md` and `skills/**`

Prose, written by hand, fetched on demand. Two tiers with two different tools:

```
modules/<m>/skills/SKILL.md        <- inlined by sfm_describe_module
modules/<m>/skills/tuning.md       <- sfm_module_skill(m, "tuning")
modules/<m>/skills/limitations.md  <- sfm_module_skill(m, "limitations")
modules/<m>/skills/artifact.md     <- sfm_module_skill(m, "artifact")
modules/<m>/skills/sources.md      <- sfm_module_skill(m, "sources")

skills/SKILLS.md                   <- sfm_workflow_skill("SKILLS.md")
skills/scene_to_pipeline.md        <- sfm_workflow_skill("scene_to_pipeline")
skills/families/*.md               <- sfm_workflow_skill("families/tracking.md")
skills/judgment/*.md               <- sfm_workflow_skill("stopping")
skills/runs/INDEX.md               <- sfm_workflow_skill("runs/INDEX.md")   [NO ROWS]
skills/runs/EVIDENCE.md            <- sfm_workflow_skill("runs/EVIDENCE.md")
skills/distill/SKILL.md            <- sfm_workflow_skill("distill/SKILL.md")
docs/*.md, docs/design/*.md        <- sfm_workflow_skill("import_lessons")
```

`sfm_workflow_skill` resolves a topic against `skills/<topic>`,
`skills/<topic>.md`, `skills/judgment/<topic>.md`, and then the same two forms
beside `skills/` — `docs/<topic>.md` and `docs/design/<topic>.md`. So a bare topic
reaches the judgment tier by name, the design and lessons documents the skill files
cite are fetchable, and anything else in the tree is reachable by relative path. A
miss returns every topic under both roots, printed as it must be *typed*, which
makes wrong guesses self-correcting.

**There is no `skills/workflow/` candidate and that is deliberate** — see §4.

### D. The artifact and run store — `<store>/`

```
<store>/artifacts/<id>/artifact.md   manifest (YAML frontmatter) + narrative (body)
<store>/artifacts/<id>/data/*.npz    the payload
<store>/runs/<run_id>/run.md         the attempt DAG: every step, its params, its metrics
```

Written by module containers, read by the inspection tools. `run.md` is a *tree*,
not a history: because ids come from the recipe, re-running with new parameters
appends a step and keeps the old one.

---

## 2. Tool by tool

### Discovery

| Tool | Reads | Writes |
| --- | --- | --- |
| `sfm_list_modules` | **A** — every `module.yaml`, projected to name/version/kind/summary/consumes/produces/gpu/terminal | — |
| `sfm_describe_module` | **A** — one `module.yaml`, in full; **C** — that module's `skills/SKILL.md`, inlined, plus the stems of its other skill files as `available_skills` | — |

`sfm_describe_module` is the progressive-disclosure boundary. One call gives the
machine contract and the module's overview; `tuning`, `limitations`, `artifact`
and `sources` cost a second call each, so context spend scales with how stuck the
caller is rather than with the module count.

### Execution

| Tool | Reads | Writes |
| --- | --- | --- |
| `sfm_check` | **A** for the parameter schema and slot types; **D** for each input artifact's manifest (to read its type) and for whether the planned output ids already exist | — |
| `sfm_run` | everything `sfm_check` reads; then in the container, `/module/module.yaml` and `/module/adapter.py`; **B** at seal time | **D** — a new artifact directory and an appended step in `run.md` |
| `sfm_replay` | **D** — `run.md`, to find the step that produced an artifact and everything downstream of it | **D** — new artifacts on a new branch; the original is untouched |
| `sfm_job` | in-memory job table only | — |
| `sfm_list_jobs` | in-memory job table only | — |

Three things worth being precise about:

**Type checking happens in `sfm_check`, before anything spawns.** A wrong wiring
costs one round trip. The refusal names the modules that produce the type the
slot wanted, resolved from **A** at the moment of failure — so it cannot go stale.

**The cache key is the recipe**, computed from `(module, module_version, slot,
resolved params, input ids)`. It does not cover adapter *source*, which is why a
code edit needs a fresh store or a rebuilt image rather than just a re-run.

**Metrics come back inline.** `sfm_run` returns `metrics`, `diagnostics` and
`notes` — the last being the narrative body the adapter wrote into `artifact.md`.
No second call is needed to see how a step went.

### Inspection

| Tool | Reads | Writes |
| --- | --- | --- |
| `sfm_artifact` | **D** — `artifact.md` frontmatter, the array inventory, the sidecar list, and (with `full`) the narrative body | — |
| `sfm_artifact_image` | **D** — one image sidecar's bytes, returned as an `ImageContent` block beside its provenance | — |
| `sfm_run_summary` | **D** — `run.md`: every step attempted with params and metrics, plus the leaf artifacts nothing consumed | — |
| `sfm_compare` | **D** — the manifests of the named artifacts, plus their ancestry walked back through `inputs` | — |
| `sfm_plan_brief` | **A + C + D** — every `scene_analysis/v1` in the store whose `scene` is this one, `skills/scene_to_pipeline.md`, six `skills/families/*.md`, and the 27 manifests that consume `scene/v1` | — |

**`sfm_plan_brief` is the only tool that reads three stores at once**, and that is
the point of it. Step 3 needs the measurements (**D**), the prose that ranks each
stage (**C**), and the live menu (**A**) in the same breath — split across six
calls, the early ones have fallen out of context by the time the argument is
made. It reports `analysis_missing` rather than quietly planning from a partial
picture, and it decides nothing: like `SceneDescription` rendering a contact
sheet, it prepares and stops.

**It also reads the artifact payloads, not only their manifests** — the one place
in the tool surface that opens an npz to answer a question. Every metric an
analysis module reports is a median, a p75 or a fraction over the set, and the
advice attached to those metrics is per-frame and per-pair: *open the soft frame
before dropping it*, *keep the planar pair out of the seed*. Six independent
readers of the first briefs hit the same wall — the instruction named a frame and
the response carried one scalar. So each analysis entry now has a `series` block
holding the stored arrays as the artifact groups them, and `scene.images` carries
the index those series are in. Above 200 elements a series arrives summarised at
both extremes rather than truncated to a prefix, since a prefix of a per-frame
array is the first frames rather than the interesting ones.

`sfm_compare`'s lineage-divergence report is the part that earns its place:
without it, two results differing because of a change three stages upstream look
like evidence about the parameter just turned.

`sfm_artifact_image` **resolves and vets a path; it never decodes.** The
orchestrator has no image library and should not acquire one — pixels are a
container concern, and serving bytes a container already wrote is inspection. It
refuses a name that resolves outside the artifact's data directory, a non-image
extension, and anything over 8 MiB, naming what is available in each case. With
no `name` it returns the artifact's images, or resolves silently when there is
exactly one — which is the `SceneDescription` contact-sheet case.

### Knowledge

| Tool | Reads | Writes |
| --- | --- | --- |
| `sfm_module_skill` | **C** — `modules/<name>/skills/<topic>.md` | — |
| `sfm_find_alternatives` | **A** only — a capability query against the live registry | — |
| `sfm_workflow_skill` | **C** — the four-candidate resolution above, anywhere under `skills/` | — |

`sfm_find_alternatives` is what a `limitations.md` escape compiles to. The
important argument is `not_consuming`: *"produces `tracks/v1` but does NOT consume
`pairwise_matches/v1`"* is how a skill file says **"use a direct tracker, because
the matcher is the problem"** without naming a module that may be gone.

### Authoring

| Tool | Reads | Writes |
| --- | --- | --- |
| `sfm_scaffold_module` | **B**, to validate the declared payload types | `modules/<new>/` — `module.yaml`, `adapter.py` (raising until implemented), `Dockerfile`, and five skill stubs |
| `sfm_build_module` | `modules/<m>/Dockerfile`; **A** for the image tag | a container image |
| `sfm_reload_modules` | **A** — re-scans the directory | — |
| `sfm_smoke_test` | **A** for the declared metrics and diagnostics; **C** to check every `see_also` names a skill file that exists | **D** — one throwaway artifact |

`sfm_smoke_test` is the contract check: it verifies a module keeps its own
manifest's promises, which is a different question from whether it ran.

A diagnostic is the case where those promises are easiest to break, because
**the manifest and the adapter each hold half of one**. The manifest is the
catalogue `sfm_describe_module` shows before anything runs; the adapter writes
the instance, with the run's numbers in its message, and *that* is what reaches
the caller — the manifest's static text never travels with the artifact. So
against a real run it checks:

| Check | Why |
| --- | --- |
| every raised code is declared | otherwise `sfm_describe_module` cannot warn the module can say it |
| raised `severity` == declared | a warn advertised and an error raised is a different contract |
| raised `see_also` == declared | the manifest's pointer is the one the agent read *before* running |
| raised message and `suggested_actions` are non-empty | the manifest's do not travel; only these do |
| an alarm that fired reads outside its metric's `healthy` band | the firing threshold lives in the adapter and the band in the manifest — two numbers, two files, nothing watching them |

The band check needs the link, so a diagnostic may declare **`metric:`** naming
the metric it is the alarm for. Optional: a diagnostic keyed on a condition
rather than a threshold (`uncalibrated`, `exif_unavailable`) leaves it empty. When
present it is also checked statically, which catches a renamed metric leaving the
alarm pointing at nothing.

**One direction only, deliberately.** Firing while healthy is unambiguous drift.
The reverse — outside the band with no diagnostic — is legitimate hysteresis: a
band says "outside the comfortable range" and a warn says "loud enough to
interrupt", and those are allowed to sit apart. `SceneTriage`'s `repetitiveness`
uses exactly that gap, with a band at 0.75 and a warn at 0.80.

Likewise **a declared diagnostic that did not fire is not a problem.** One smoke
input cannot trip every condition, and demanding it would push modules toward
diagnostics that always fire.

---

## 3. What a first pipeline actually touches

Following DTU scan10 — 49 PNGs plus `calibration_DTU_new.npz` — from an empty
session to a first reconstruction, with the files each step opens.

```
0. orientation
   sfm_list_modules()                  27 module.yaml
   sfm_list_modules(produces=scene/v1) 27 module.yaml -> exactly one answer
   sfm_describe_module(SceneLoader)    modules/scene_loader/module.yaml
                                     + modules/scene_loader/skills/SKILL.md

1. build the scene
   sfm_check(SceneLoader, params)      module.yaml; planned id vs store
   sfm_run(SceneLoader, ...)           container reads /module/*; seals against
                                       types/scene.yaml; writes artifacts/<id>/
                                       and runs/dtu10/run.md
   -> n_images, mixed_resolution, downscale_factor, megapixels, inline

2. characterise the scene            <- NEW, and previously the gap here
   sfm_run(SceneTriage, {scene})       types/scene_analysis.yaml at seal
   -> photometric / texture / metadata groups; combined_change,
      repetitiveness, textureless_fraction, sharpness_ratio, ordered
   sfm_run(SceneMotion, {scene})       same type, disjoint groups
   -> motion / degeneracy groups; overall_magnitude, variability,
      rotation_median_deg, planar_dominance, pure_rotation_risk

3. plan the pipeline                 <- NEW, and previously the gap here
   sfm_plan_brief(scene)               store: every scene_analysis/v1 whose
                                       `scene` is this one
                                     + skills/scene_to_pipeline.md
                                     + skills/families/{detection,matching,
                                       tracking,pose,sparse,optimization}.md
                                     + 27 module.yaml (the menu)
   -> one response holding measurements, the guide that reads them, the prose
      that ranks each stage, and the shape the plan should take.
      It PREPARES. It does not decide.

4. the stage loop, repeated
   sfm_check -> sfm_run -> read the inline metrics
   detect -> match -> track -> pose -> triangulate -> bundle adjust

5. when a number is bad
   sfm_module_skill(<m>, "tuning")       indexed by observed metric state
   sfm_replay(run, artifact, overrides)  that step and everything downstream
   sfm_module_skill(<m>, "limitations")  failure signature + capability query
   sfm_find_alternatives(...)            resolve it against the live registry

6. comparing the branches
   sfm_compare([...])   side by side, plus where the lineages diverge
   sfm_run_summary(run) every step attempted, and the leaves
```

Step 2 is what `SceneTriage` and `SceneMotion` added. Before them the agent's
first real information about scan10's geometry arrived from the *matcher* — it
learned the scene by starting to reconstruct it. Now the loader's bookkeeping
(how much image there is), triage (what the images are like) and motion (how the
camera moved) are all available before a detector is chosen.

**Step 3 is still a judgement, and no tool makes it** — `sfm_plan_brief` gathers
the argument's inputs and stops there, the same way `SceneDescription` renders a
contact sheet and stops. The type system constrains what *can* follow; the family
files say what *should*; `skills/scene_to_pipeline.md` translates the numbers
into the vocabulary those files are written in. What none of them do is decide.

That asymmetry is deliberate, and the remaining gap is narrower than it was: the
translation is now written down and countable, so a threshold that turns out to
be wrong can be corrected in one file rather than re-derived every session.

---

## 4. The tiers that were empty — what filled them, and what did not

`skills/judgment/`, `skills/workflow/` and `skills/runs/INDEX.md` were all empty by
decision, to be filled from the agent-driven runs. Two of the three are resolved,
and the resolutions went in opposite directions. This section records which, so the
remaining gap is a known state rather than a surprise.

### `skills/judgment/` — thresholds and practitioner calls — **FILLED**

| Reached by | How |
| --- | --- |
| `sfm_workflow_skill(topic)` | resolves `skills/judgment/<topic>.md` on a bare topic name |

Five files, all written: `swap_or_build`, `stopping`, `smells`, `priors`,
`tradeoffs`. A sixth, `triage`, was cut rather than written — what to read off a
capture before running anything is `skills/scene_to_pipeline.md`, reached through
`sfm_plan_brief`, and `SKILLS.md` says so by name instead of leaving a link that
resolves to nothing.

**One capability this tier was to unblock is still blocked.** `scene_analysis/v1`
declares a `traits` group and neither analysis module fills it, deliberately:
traits were to be derived by the orchestrator from thresholds held here, so that
revising what counts as "narrow baseline" does not cost a re-run. Those thresholds
are not here — they are in `scene_to_pipeline.md`, as *observed ranges over a named
corpus* rather than as cut points, which is a deliberate refusal to invent a
boundary the evidence does not have. So there is still no derived trait vector, and
traits are the retrieval key `runs/INDEX.md` wants. The blockage is now a stated
disagreement about whether cut points should exist, not an unwritten file.

### `skills/workflow/` — cross-cutting stage guides — **RETIRED**

The directory is gone, and the resolver no longer searches it.

Six guides were designed for it and none was written. Across a seventeen-capture
sweep it was requested 24 times and **every request raised rather than returned**.
The cost of that is not the missing content: the error's `Available:` list did not
name the documents that do exist, so readers who followed a pointer into it
concluded the whole knowledge base was gone, and one said so in writing. A search
path for a directory that does not exist manufactures misses.

The diagnosis is that the original `workflow/`-versus-`judgment/` split sorts by
**who authored a claim**, not by **what question a reader is holding**. A reader
with a broken reconstruction does not know which half their answer is in. So the
mechanical half settled where readers were already standing — `scene_to_pipeline.md`
for routing a symptom to a stage, `families/` for choosing inside one,
`judgment/stopping.md` for sweep mechanics, each module's `artifact` skill plus the
type contract for reading a payload. `SKILLS.md` carries the full redirect table.

**Do not restore the search path without the files.** That combination is what
produced the 24 misses.

### `skills/runs/` — the worked-run corpus — **SPLIT; half still empty**

| File | Reached by | State |
| --- | --- | --- |
| `runs/INDEX.md` | `sfm_workflow_skill("runs/INDEX.md")` — a relative path; the bare-topic form does not find it | header only, no rows |
| `runs/EVIDENCE.md` | `sfm_workflow_skill("runs/EVIDENCE.md")` | two campaigns, per-capture |
| `runs/CORPUS.txt` | not a `.md`; read as a file | the 17 captures every range is fitted on |

These were one file and are now two, because they answer incompatible questions.
`INDEX.md` answers *"has a scene like this been solved before?"* and wants a row
you can match your own capture against. `EVIDENCE.md` answers *"where does this
claim come from?"* and exists to be cited and **not** matched — matching your
readings against it is how a reader leaks their own answer back to themselves.
Sharing a file meant anyone fetching the second got the first's promise.

**`INDEX.md` is still empty, and it is blocked upstream**, not by transcription:
the retrieval it supports is a set intersection between a capture's derived traits
and a run's `scene_traits` frontmatter, and trait derivation is the capability
`judgment/` did not unblock above.

**The machinery underneath it is live.** The orchestrator already binds each run to
its scene on the first step that touches one (`_scene_of`, `orchestrator.py`),
precisely so `INDEX.md` has a stable key to be built from later. Nothing needs
re-plumbing when the rows arrive.

### Summary

| Tier | Files | Tool that reads it | State |
| --- | --- | --- | --- |
| `judgment/` | 5, plus 1 cut | `sfm_workflow_skill` | populated; trait derivation still unblocked |
| `workflow/` | — | — | **retired**; content redistributed, search path removed |
| `runs/INDEX.md` | header only | `sfm_workflow_skill` | blocked on trait derivation |
| `runs/EVIDENCE.md` | 2 campaigns | `sfm_workflow_skill` | populated; the 17-capture sweep not yet transcribed |
| `families/` | 8 | `sfm_workflow_skill` | populated |
| `scene_to_pipeline.md` | 1 | `sfm_workflow_skill`, `sfm_plan_brief` | populated; the largest single file in the tier |
| `distill/SKILL.md` | 1 | `sfm_workflow_skill` | written; the loop it describes has never run |
| `modules/*/skills/` | 141: five per module across 28, plus `SceneDescription/rubric.md` | `sfm_describe_module`, `sfm_module_skill` | populated |

One tool reads every tier above except the module skills, and no new tool was
needed as they filled — which is the point of routing every knowledge tier through
one resolver. What the resolver could not fix is a tier that never got files: that
took deleting it.
