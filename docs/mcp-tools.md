---
name: mcp-tools
description: The 17 MCP tools and the exact files each one reads or writes. Where the agent's context comes from, and which tools are currently blocked on the empty knowledge tiers.
status: current as of 2026-08-14
---

# The tools and their context

Seventeen tools in five groups. The count does not grow with the module count —
modules are *discovered* through `sfm_list_modules` / `sfm_describe_module`, never
enumerated as tools, so this surface is the same at 2 modules and at 200.

Every tool's context comes from one of four stores. Knowing which one answers
"why does the agent know this" and, more usefully, "why does it not".

---

## 1. The four stores

### A. Module manifests — `modules/*/module.yaml`

27 files. Loaded once at server start by `ModuleRegistry.load_dir`, and again on
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
skills/families/*.md               <- sfm_workflow_skill("families/tracking.md")
skills/judgment/*.md               <- sfm_workflow_skill("triage")      [EMPTY]
skills/workflow/*.md               <- sfm_workflow_skill("<topic>")     [EMPTY]
skills/runs/INDEX.md               <- sfm_workflow_skill("runs/INDEX.md") [EMPTY]
```

`sfm_workflow_skill` resolves a topic against four candidates in order —
`skills/<topic>`, `skills/<topic>.md`, `skills/workflow/<topic>.md`,
`skills/judgment/<topic>.md` — so a bare topic reaches the judgment and workflow
tiers by name, and anything else in the tree is reachable by relative path. A
miss returns the full list of every `.md` under `skills/`, which makes wrong
guesses self-correcting.

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
| `sfm_run_summary` | **D** — `run.md`: every step attempted with params and metrics, plus the leaf artifacts nothing consumed | — |
| `sfm_compare` | **D** — the manifests of the named artifacts, plus their ancestry walked back through `inputs` | — |

`sfm_compare`'s lineage-divergence report is the part that earns its place:
without it, two results differing because of a change three stages upstream look
like evidence about the parameter just turned.

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

3. choose the family                 <- no tool decides this
   sfm_workflow_skill("families/detection.md")
   sfm_workflow_skill("families/matching.md")
   sfm_list_modules(consumes=scene/v1)   the menu, not the answer

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

**Step 3 is still a judgement, and no tool makes it.** The type system constrains
what *can* follow; the family files say what *should*. That asymmetry is
deliberate and it is where the empty tiers bite.

---

## 4. The empty tiers — which tools read them, and what does not work

`skills/judgment/`, `skills/workflow/` and `skills/runs/INDEX.md` are empty by
decision; they are to be filled from the agent-driven runs. This section records
what is wired and waiting, so the gap is a known state rather than a surprise.

### `skills/judgment/` — thresholds and practitioner calls

| Reached by | How |
| --- | --- |
| `sfm_workflow_skill(topic)` | resolves `skills/judgment/<topic>.md` on a bare topic name — `triage`, `stopping`, `tradeoffs`, `smells`, `priors` |

Indexed in `skills/SKILLS.md` and unwritten. Five files are named there.

**What does not work without it:**

- **Trait derivation.** `scene_analysis/v1` declares a `traits` group and
  **neither analysis module fills it**, deliberately: traits are derived by the
  orchestrator from thresholds held here, so that revising what counts as
  "narrow baseline" does not cost a re-run. With `judgment/` empty there are no
  thresholds, so there is no trait vector — and traits are the retrieval key.
- **Stopping.** The agent will decide when a reconstruction is good enough with
  no authored answer. `healthy` bands in manifests are advisory and
  module-local; they are not a stopping criterion.
- **Reading the analysis numbers.** Both new modules emit cues whose *cut points*
  are explicitly not theirs to set. Until `judgment/` says what counts as
  repetitive, the agent has a number and a provisional band.

### `skills/workflow/` — cross-cutting stage guides

| Reached by | How |
| --- | --- |
| `sfm_workflow_skill(topic)` | resolves `skills/workflow/<topic>.md` on a bare topic name |

Empty, with no filenames committed to yet. This is the tier that would answer
"which stage is my problem in" — the question that sits above any single module's
`tuning.md` and below `judgment/`.

**What does not work without it:** nothing refuses, but a failure whose cause is
two stages upstream has no authored path back. `sfm_compare`'s divergence report
is the mechanical half of that answer; the interpretive half is here.

### `skills/runs/INDEX.md` — the worked-run corpus

| Reached by | How |
| --- | --- |
| `sfm_workflow_skill("runs/INDEX.md")` | by relative path — it is not under `workflow/` or `judgment/`, so the bare-topic form does not find it |

The file exists with its table header and no rows.

**What does not work without it:** *"has a scene like this been solved before?"*
returns nothing. The retrieval it is meant to support is a set intersection
between a scene's derived traits and a run's `scene_traits` frontmatter — which
is doubly blocked, since trait derivation needs `judgment/` too.

**The machinery underneath it is live**, which is the part worth knowing: the
orchestrator already binds each run to its scene on the first step that touches
one (`_scene_of`, `orchestrator.py`), precisely so `INDEX.md` has a stable key to
be built from later. Nothing needs re-plumbing when the rows arrive.

### Summary

| Tier | Files | Tool that reads it | Blocked capability |
| --- | --- | --- | --- |
| `judgment/` | 0 of 5 named | `sfm_workflow_skill` | trait derivation; stopping criteria; cut points for the analysis cues |
| `workflow/` | 0 | `sfm_workflow_skill` | stage-level diagnosis above a single module |
| `runs/INDEX.md` | header only | `sfm_workflow_skill` | "scenes like this were solved how" |
| `families/` | 8 | `sfm_workflow_skill` | — populated |
| `modules/*/skills/` | 135 across 27 modules | `sfm_describe_module`, `sfm_module_skill` | — populated |

Only one tool reads all three empty tiers, and it is the same tool that reads the
populated ones. **No new tool is needed when they are filled** — which is the
point of routing every knowledge tier through one resolver.
