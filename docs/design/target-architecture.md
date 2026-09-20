---
name: target-architecture
description: HISTORICAL — the original proposal this system grew from. Kept for reference only; it does not describe what is built, and nothing links to it.
status: historical reference — superseded by the implementation
---

# Target Architecture — Proposal

> **Historical reference.** This is the original proposal, kept as a record of the
> design's starting point. The system that was built differs from it in places — tool
> names, scene loading, the job model among them. For what exists now, read
> `docs/mcp-tools.md`, `docs/module-contract.md` and `docs/artifact-spec.md`.

Current state was documented in the predecessor's `overview/` notes (that
repository, not this one). Read
the refactor targets (not written) first for what
is in the way.

## The three pieces

```
        ┌─────────────────────────────────────────────────────┐
        │  Claude (the driver)                                │
        │    plans, tunes params, compares metrics,           │
        │    swaps modules, scaffolds new ones                │
        └───────────────────────┬─────────────────────────────┘
                                │  MCP
        ┌───────────────────────▼─────────────────────────────┐
        │  sfm-orchestrator (MCP server)                      │
        │    module registry · run DAG · GPU broker ·         │
        │    container lifecycle · artifact store             │
        └───────────────────────┬─────────────────────────────┘
                   ┌────────────┼────────────┬────────────┐
                   ▼            ▼            ▼            ▼
              ┌────────┐  ┌────────┐  ┌────────┐  ┌────────┐
              │ SIFT   │  │ VGGT   │  │ COLMAP │  │  ...   │   module servers
              │ :8080  │  │ :8080  │  │ :8080  │  │        │   (one container each)
              └───┬────┘  └───┬────┘  └───┬────┘  └───┬────┘
                  └───────────┴───────────┴───────────┘
                                │  shared volume (read/write)
                     ┌──────────▼───────────┐
                     │  artifact store      │
                     │  runs/<run_id>/...   │
                     └──────────────────────┘
```

Three contracts hold it together, and **only three**:

1. **The module manifest** — what a module is, consumes, produces, and can be tuned by.
2. **The artifact** — what flows between modules.
3. **The module server API** — how the orchestrator invokes a module.

Everything else is implementation detail inside a container.

### A fourth piece, outside the contracts: the harness

`harness/` drives the experiments that produce the evidence the context is written
from. It is not part of the pipeline: no module depends on it, it declares no
artifacts, and it holds none of the three contracts. It launches one isolated
`claude -p` per capture, hands each the procedure as its prompt, gates the GPUs, and
writes run directories into the experiment record outside this repository.

It is versioned here, rather than beside the run data where it began, for two reasons.
A change to the procedure an agent is given is as much a change to the experiment as a
change to a skill file, and it should be reviewed with one. And it is the one place
outside `skills/` that can name a capture — in a usage example, a smoke test, an error
message — so it is the one place that can quietly write a holdout into the repository
and cost that capture its ability to measure whether the context generalises. Every
capture it names is a corpus member. See [`harness/README.md`](../../harness/README.md).

The predecessor at `~/sfm_experiments/harness` is frozen with its data so earlier
batches stay reproducible.

---

## 1. Artifacts

### Shape

An artifact is a **directory**, not a class. Write-once, immutable, addressed by id.

```
runs/<run_id>/
  run.md                          # frontmatter: run manifest · body: narrative log
  artifacts/
    <artifact_id>/
      artifact.md                 # frontmatter = manifest · body = agent-readable narrative
      data/
        observations.npz
        sparse/                   # optional native sidecars (COLMAP bins, .ply, ...)
```

**One file, two audiences.** `artifact.md` carries a YAML frontmatter block (the
machine-readable manifest the orchestrator validates and routes on) and a
markdown body (what the driving agent reads: what happened, how it went, what to
look at). This is what you were reaching for with "artifact.md + npz". Keeping
them in one file means they cannot drift, which two files guarantee they will.

```yaml
---
id: art_7f3a91
type: tracks/v1
run: run_20260807_dtu_scan1
scene: art_2b1c04                     # the scene/v1 artifact this run is bound to
inputs: [art_9d4e77]                  # provenance DAG, by artifact id
produced_by:
  module: FeatureTrackFromPairsUnionFind
  module_version: 1.2.0
  image: ghcr.io/lab/sfm-classical@sha256:9c1f...
  params: {min_track_len: 3, allow_pair_local_merge: true}
  started_at: 2026-08-07T14:22:11Z
  duration_s: 41.2
  device: cpu
files:
  observations:
    path: data/observations.npz
    arrays:
      obs:         {shape: [1482301, 4], dtype: float32,
                    columns: [track_id, frame_idx, x, y]}
      track_count: {shape: [], dtype: int64}
metrics:
  avg_track_length:  {value: 4.21, direction: higher_better, healthy: [3.0, null]}
  survival_ge_3:     {value: 0.62, direction: higher_better, healthy: [0.40, null]}
  fragmentation:     {value: 0.24, direction: lower_better,  healthy: [null, 0.35]}
status: ok
diagnostics: []
---

Built 351,204 tracks from 39 image pairs. Track survival past 3 views is 0.62,
comfortably above the 0.40 floor that sparse reconstruction needs. Median track
length 4; the tail past 10 views is thin (3%), typical for a turntable sequence.
```

`direction` + `healthy` on every metric is what replaces today's hand-written
`optimize_context/metric_context.txt`: the metric explains its own interpretation,
so the driving agent needs no external corpus to know whether 4.21 is good.

### Payload types: open registry, versioned names

The **envelope** is free-form and uniform. The **payload** is typed, because
interop needs it — if one module writes tracks as `N×4 [track_id, frame, x, y]`
and another expects `dict[track_id → list]`, nothing composes.

A type is a name + a schema file. Adding one is adding a file, not changing the
framework:

| Type | Payload | Replaces |
| --- | --- | --- |
| `scene/v1` | image paths (not pixels), intrinsics, distortions, resize metadata, image hashes | `CameraData` |
| `scene_analysis/v1` | motion, photometric, texture, degeneracy, metadata cues + derived traits — see [scene-analysis.md](scene-analysis.md) | `agent/core/utility/*` |
| `features/v1` | per-image keypoints, descriptors, scores, scale, orientation | `list[Points2D]` |
| `pairwise_matches/v1` | pair index, `[x1,y1,x2,y2]`, confidences, obs ids | `PointsMatched` (pairwise half) |
| `tracks/v1` | `N×4 [track_id, frame, x, y]` observation table | `PointsMatched` (track half) |
| `poses/v1` | `N×3×4` cam-from-world, per-frame validity | `CameraPose` |
| `sparse_model/v1` | points3D, colors, observations, poses (+ optional COLMAP `sparse/*.bin` sidecar) | `Scene(sparse=True)`, `IncrementalSfMState` |
| `dense_model/v1` | point cloud / depth maps (+ optional `.ply`) | `Scene(sparse=False)` |

Notice `PointsMatched` splits into two types. It is three things today
(pairwise container, track container, observation registry) and every consumer
branches on which half is populated — see
the datatype overview (not written; `packages/sfmkit/src/sfmkit/types/` is authoritative).

**Openness rule:** a module may declare `type: custom/<name>/v1` with an inline
schema in its manifest. It flows through the system, is stored, and is routable
to any module that declares it consumes it. The core set above is curated
convention, not a closed world. This is how gaussians, segmentation masks,
semantic labels, or uncertainty maps arrive later without a framework change.

### Openness without fragmentation — four guards

The risk in an open type system is a module producing something nothing else can
read. Two distinct failure modes, and only one of them is a crash:

| Failure | Consequence | Guard |
| --- | --- | --- |
| Module declares `tracks/v1` but writes a non-conforming payload | **downstream crash** | write-time schema validation (2) |
| Module produces `custom/foo/v1` that nothing consumes | dead end, no crash | orphan warning at registration (4) |

**(1) Type check before spawn.** `sfm_run` rejects a call whose input artifact
type is not in the module's `consumes`, before any container starts. A pipeline
therefore *cannot* crash from mismatched wiring — the orchestrator refuses to
build it. This is the guard that makes the concern mostly a usability question
rather than a stability one.

**(2) Write-time schema validation, enforced by `sfmkit`.** When a module seals an
artifact, `sfmkit` validates the payload against the registered schema for the
declared type: array names present, rank and declared dimensions, dtypes, column
counts, and cheap invariants (`obs[:,0].max()+1 == track_count`). A mismatch fails
**the producing job**, not a consumer three stages later. Non-optional, no opt-out.
This is the guard that actually prevents the crash.

**(3) Extension is additive within a type, not a new type.** Every schema declares
**required** and **optional** arrays. A module that produces a point cloud *plus*
per-point uncertainty emits `sparse_model/v1` with an extra optional array — it
does **not** invent `custom/sparse_with_uncertainty/v1`. Consumers ignore arrays
they do not know. This is the discipline that keeps the type set small while
leaving it genuinely open; without it, every new capability forks a type and the
graph fragments. A new `v2` is warranted only when a **required** field changes,
and the registry then carries a `v2 → v1` adapter.

**(4) Orphan types are flagged at registration, not discovered at runtime.**
`sfm_build_module` warns when a module produces a type no registered module
consumes, marks it terminal in `sfm_list_modules`, and `sfm_smoke_test` records
it. Producing a terminal artifact is legitimate — final outputs are terminal by
definition — but the agent learns it *before* spending a GPU hour, not after.

Promoting a `custom/` type into the core set is a deliberate act: write a schema
file, get it reviewed. `custom/` types work fine but are visibly second-class,
which is the right pressure.

### Two decisions worth calling out

**Data never crosses the wire.** Artifacts are hundreds of MB (dense depth maps,
point clouds). Containers mount the run directory and receive *paths*. The
HTTP/JSON layer carries only ids, params, metrics, and diagnostics.

**`Scene.recon` (the live `pycolmap.Reconstruction`) becomes a sidecar.** The
canonical form of `sparse_model/v1` is npz. When a COLMAP-backed module produces
one, it *also* writes `data/sparse/{cameras,images,points3D}.bin` and flags it in
the manifest. pycolmap consumers open the sidecar natively; everyone else reads
the npz. This kills the framework's only unserializable handoff without losing
COLMAP interop.

### Immutability buys the thing you actually want

Today `output_key` is a class constant and a second sparse reconstructor silently
overwrites the first. With write-once artifacts, re-running a module with new
params produces a *new* artifact and both are retained. `run.md` becomes a DAG of
attempts rather than a linear history — which is exactly the substrate the
driving agent needs to compare "SIFT@8000 vs SuperPoint@4096" without re-running
anything.

---

## 2. Modules

### The contract: manifest + adapter + base image

Turning a GitHub repo into a working module should be three files.

```
modules/feature-tracking-unionfind/
  module.yaml       # declarative: identity, I/O types, params, metrics, diagnostics
  Dockerfile        # FROM a base image; install the upstream repo
  adapter.py        # the only imperative code you write
```

**`module.yaml`** is the single source of truth. It feeds the MCP tool schema,
the agent's tool documentation, type-based plan validation, and metric
interpretation — all four things that are hand-maintained and drifting today
(see the agent-layer overview (not written)).

```yaml
name: FeatureTrackFromPairsUnionFind
version: 1.2.0
kind: tracking
summary: Builds multi-view tracks from pairwise correspondences via union-find.
description: |
  Use when a pairwise matcher has already run. Cheap, CPU-only, no learned
  components. Prefer a direct tracker (VGGSfM, TAPIR) when pairwise matching
  is producing short tracks on low-texture scenes.

image: ghcr.io/lab/sfm-classical:1.4.0
resources: {gpu: false, min_ram_gb: 8}

consumes:
  scene: {type: scene/v1,            required: true}
  pairs: {type: pairwise_matches/v1, required: true}
produces:
  tracks: {type: tracks/v1}

params:
  min_track_len:
    type: integer, default: 2, minimum: 2, maximum: 10
    description: Minimum observations for a track to be kept.
    tuning: Raise to 3 when downstream triangulation reports high reprojection error.
  allow_pair_local_merge:
    type: boolean, default: true
    description: Merge coordinate-adjacent observations from detector-free matchers.

metrics:
  avg_track_length: {direction: higher_better, healthy: [3.0, null],
                     meaning: Mean observations per track.}
  survival_ge_3:    {direction: higher_better, healthy: [0.40, null],
                     meaning: Fraction of tracks seen in >=3 views. Sparse recon needs this.}

diagnostics:
  - code: too_few_tracks
    message: Fewer than 100 tracks survived; sparse reconstruction will fail.
    suggested_actions:
      - Increase the detector's max_keypoints.
      - Loosen the matcher's RANSAC_threshold (cap at 3.0).
      - Switch to a detector-free matcher (LoFTR, RoMa) on low-texture scenes.
```

`description`, `tuning`, and `diagnostics.suggested_actions` are where today's
long English error strings in `run_from_state` go. Those strings are the
framework's most underrated asset — they are the corrective feedback loop — and
they should be relocated, not deleted.

**`adapter.py`** is the only code a module author writes:

```python
from sfmkit import module, Ctx

@module
def run(ctx: Ctx):
    obs   = ctx.inputs["pairs"].load("matches")       # -> np.ndarray
    scene = ctx.inputs["scene"]

    tracks = union_find_tracks(obs, min_len=ctx.params.min_track_len)

    out = ctx.output("tracks")
    out.save("obs", tracks, columns=["track_id", "frame_idx", "x", "y"])
    out.metric("avg_track_length", float(...))
    out.metric("survival_ge_3", float(...))
    if len(tracks) < 100:
        out.diagnostic("too_few_tracks")
    out.note("Built %d tracks from %d pairs." % (...))
```

### The shared library must stay tiny — this is load-bearing

If `sfmkit` needs torch or pycolmap, the dependency conflict is back inside every
container. So:

- **`sfmkit`** — artifact I/O, manifest read/write, metrics, the server harness.
  **stdlib + numpy only.** Nothing else, ever.
- **`sfmgeom`** *(optional second lib)* — shared geometric helpers currently
  duplicated across modules (`Normalization`, `TriangulationCheck`, RANSAC
  outlier rejection, reprojection error). **numpy + opencv only** — neither is a
  conflict source.

Everything else in today's `sfmcore` dissolves into per-module adapters. There is
no shared `sfmcore` in the target state; that shared import is precisely what
forces one environment today.

### One image per module — strictly

**Decided:** every module gets its own image and its own Dockerfile, even when two
modules would be byte-identical in their dependencies. No shared "classical" image
covering SIFT/ORB/BF/FLANN. The discipline is worth more than the efficiency.

The cost is smaller than it looks, provided every Dockerfile starts from a common
runtime base:

```dockerfile
FROM ghcr.io/lab/sfm-runtime:1.0        # python + sfmkit + sfmgeom, ~400 MB
RUN pip install --no-cache-dir opencv-python==4.12.0.88
COPY adapter.py module.yaml skills/ /module/
```

Docker stores the shared base layers **once**, so 23 module images built on one
base cost `base + 23 × (delta)`, not `23 × full`. The images that genuinely
diverge — torch/CUDA variants for VGGT, VGGSfM, RoMa — are the ones that would
have needed separate images anyway.

Rules that keep this maintainable:

- Every Dockerfile follows the same skeleton and pins the base by tag.
- Upstream repos are installed at a **pinned commit**, never a floating branch.
- A bump to `sfm-runtime` is a version bump across all module manifests —
  so the base contract (`sfmkit`) must be small and semver-stable. This is the
  main reason `sfmkit` is capped at stdlib + numpy.

Which backends each module needs today:
the module inventory (not written).

### Server lifecycle

Modules run as **servers, spawned on demand, with an idle TTL** — not always-on,
not per-call cold starts.

The reason is your use case #3: the driving agent re-runs the same module with
different parameters. A warm VGGT server keeps ~2–5 GB of weights resident and
turns a 90-second parameter sweep step into a 15-second one. Always-on across 23
modules would pin GPU memory nothing is using; cold-start-per-call would make
sweeps unusable.

Model weights live in a **mounted cache volume**, never baked into images
(HF cache, torch hub, VGGT `model.pt`). Today `sfmcore/models/` is 4.8 GB of
untracked weights and vendored source; that becomes a volume.

### Server API

Small on purpose:

```
GET  /healthz                        → {ok, gpu_visible, model_loaded}
GET  /manifest                       → module.yaml, as validated JSON
POST /run   {run_dir, inputs: {name: artifact_id}, params, job_id}
                                     → 202 {job_id}
GET  /jobs/<job_id>                  → {status, progress, log_tail, artifact_id?, metrics?, diagnostics?}
POST /jobs/<job_id>/cancel
```

The orchestrator owns the run directory and mounts it; the module reads and
writes paths under it. GPU index arrives via `--gpus` at container spawn, not
as a parameter — so a module never has to know about GPU brokering.

---

## 3. The MCP surface

The existing agent layer (`AutoSFM`, `Generator`, `Compiler`, `Executor`, and the
whole `agent_details/` prompt corpus) is **deleted**. Its job — plan, execute,
read metrics, replan — becomes Claude driving MCP tools directly.

### Tools

**Discovery and planning**
- `sfm_list_modules(kind?, consumes?, produces?)` — filterable by type, so
  "what can consume `tracks/v1`?" is a query, not tribal knowledge
- `sfm_describe_module(name)` — full manifest: params schema, metric meanings, diagnostics
- `sfm_list_datasets()` / `sfm_scenes(dataset)`
- `sfm_open_scene(dataset, scene, {max_images?, target_resolution?})` → `scene/v1` artifact

**Execution**
- `sfm_run(module, params, inputs, run_id)` → `{job_id}`
- `sfm_replay(from_artifact, overrides)` → re-executes the recorded downstream
  chain from that point, reusing each step's prior params except where
  overridden. Makes going back upstream a one-call operation instead of five.
- `sfm_job(job_id)` → status, progress, log tail; on completion the artifact id, metrics, diagnostics
- `sfm_cancel(job_id)`

**Inspection**
- `sfm_artifact(artifact_id)` → the rendered `artifact.md`
- `sfm_run_summary(run_id)` → the attempt DAG with every module, params, and metric
- `sfm_compare(artifact_ids)` → metrics side by side, **plus where their lineage
  diverges**. Nothing is ever marked "stale"; a newer branch does not supersede
  an older one, it just differs — and the agent needs to see *where*.

**Knowledge** — see [module-skills.md](module-skills.md)
- `sfm_module_skill(name, topic)` → `tuning` | `limitations` | `sources`
- `sfm_find_alternatives(capability, excluding?)` → modules matching a
  consumes/produces signature, for when tuning has bottomed out

**Authoring** — this is what closes your extensibility loop
- `sfm_scaffold_module(repo_url|name, kind, consumes, produces)` → writes
  `module.yaml` + `Dockerfile` + `adapter.py` stub
- `sfm_build_module(name)` → builds the image, validates the manifest
- `sfm_smoke_test(name, scene)` → runs it on a tiny scene, checks the artifact validates

So "download some git code and turn it into a functioning container" is:
`sfm_scaffold_module` → I fill in `adapter.py` → `sfm_build_module` →
`sfm_smoke_test` → it appears in `sfm_list_modules` and is immediately routable
by type.

### Tool granularity

**Decided: a few stable tool categories; modules are discovered, not enumerated
as tools.** The MCP surface stays at ~12 tools regardless of whether there are 23
modules or 200. Everything module-specific is reached through
`sfm_list_modules` → `sfm_describe_module` → `sfm_run`, with parameters validated
against the schema `describe_module` returns.

The categories are the five headings above: **discovery · execution · inspection ·
knowledge · authoring**. New capability gets added inside a category, not as a new
top-level tool.

`sfm_describe_module` returns the manifest *plus* the module's `SKILL.md`, so one
call gives the agent both the machine contract and the curated guidance on when to
use it. Deeper knowledge is fetched on demand via `sfm_module_skill` — see
[module-skills.md](module-skills.md).

---

## 4. Sessions, runs, and parallelism

Four nested things, deliberately kept distinct:

```
Session      an agent's MCP connection. Cheap. May own many runs.        session_id
  └─ Run     one pipeline exploration on one scene. The unit of work.    run_id
       └─ Job    one module execution. The unit of scheduling.           job_id
            └─ Artifact   the immutable output.                          artifact_id
```

**Parallelism happens at the run level.** A session can have many runs in flight —
five different pipelines on one scene, or one pipeline across thirty scenes, or
both. `sfm_run` enqueues a job and returns immediately with a `job_id`; the agent
launches the next one rather than blocking. `sfm_run_summary` and `sfm_compare`
then read across runs.

**Concurrency is bounded by GPUs.** One module holds one GPU exclusively
(decided), so with 8× A6000 at most **8 GPU jobs run at once**. CPU-only jobs
(COLMAP BA, union-find, classical matchers) run on a separate, larger pool. The
scheduler holds two queues and hands out GPU leases; a module never sees or
chooses an index.

**Multiple sessions share one GPU pool.** Two agents working simultaneously must
not let one starve the other, so the scheduler is fair-share across sessions with
a per-session in-flight cap. Runs are isolated by directory; the module registry
and GPU pool are shared.

**Scene artifacts are content-addressed and shared.** Five parallel pipelines on
`DTU/scan1` decode and resize the images **once** — the `scene/v1` artifact is
keyed by (dataset, scene, image-list hash, resize policy) and reused across runs
and across sessions. This is a large saving; image loading is currently repeated
per run and holds every decoded frame in RAM.

**Warm servers interact with GPU exclusivity.** A module server holding a GPU
lease stays alive on an idle TTL so parameter sweeps hit a warm model. When a job
needs a GPU and none is free, the scheduler evicts the least-recently-used idle
server. The consequence to expect: during a wide sweep the module *being swept*
stays hot (which is what matters) while others cold-start.

### What I meant by "headless batch" — and what I think you actually want

My earlier question was poorly framed. The distinction is **who decides the next
step**, not how many run at once:

- **Agent-driven** — Claude calls `sfm_run`, reads metrics, decides what to do
  next. Adaptive. This is the primary mode and covers parallel runs fine, since
  the agent can have many in flight.
- **Config-driven** — a fixed matrix (30 scenes × 5 pipelines, no adaptation)
  submitted from a file, running to completion unattended over hours. No LLM in
  the loop, no session to keep alive.

Config-driven is the mode used for producing evaluation tables for a paper. It is
*not* required for parallelism. If you want it, the constraint it imposes is that
the orchestrator core must not assume an MCP session exists — the MCP server and
a `sfm submit sweep.yaml` CLI become two thin front ends over one scheduler.
That is cheap to design in now and awkward to retrofit. **Open question 3.**

## 5. Orchestrator responsibilities

Not the agent's job, not the module's job:

| Concern | Behaviour |
| --- | --- |
| **Module registry** | scan `modules/*/module.yaml`, validate, index by consumes/produces type |
| **Knowledge index** | serve each module's `skills/` without spawning its container |
| **Run DAG** | assign artifact ids, record provenance, maintain `run.md` |
| **Type checking** | reject `sfm_run` when an input artifact's type isn't in the module's `consumes` — before spawning anything |
| **Scheduler** | two queues (GPU / CPU), fair-share across sessions, per-session in-flight cap |
| **GPU broker** | exclusive leases, one module per GPU; the module never sees an index |
| **Container lifecycle** | spawn on demand, health-check, idle TTL, LRU evict under GPU pressure |
| **Artifact store** | own the run directory, mount read/write into containers, dedupe `scene/v1` by content hash |
| **Image builds** | `docker build` per module from its own Dockerfile; local now, hub later |

---

## Decisions taken

| # | Decision |
| --- | --- |
| 1 | **MCP surface = ~12 tools in 5 stable categories.** Modules are discovered, never enumerated as tools. |
| 2 | **One module per GPU, exclusive lease.** 8 concurrent GPU jobs max; separate CPU pool. |
| 3 | **One image per module, strictly** — own Dockerfile, own tag, even when identical to a sibling. A shared `sfm-runtime` base layer keeps the disk cost down. |
| 4 | **`sfmcore` dissolves entirely.** Only `sfmkit` (stdlib+numpy) and `sfmgeom` (numpy+opencv) survive as shared code. |
| 5 | **Local builds now**, push to a hub later. Dockerfiles held to one consistent skeleton. |
| 6 | **Artifact = directory + `artifact.md`** (YAML frontmatter manifest + narrative body). Envelope free-form, payload typed via an open type registry. |
| 7 | **Every module ships curated skills** — metric interpretation, an improvement gradient, and limitations. See [module-skills.md](module-skills.md). |
| 8 | **No backwards compatibility** with the current `sfmcore` / `AutoSFM` stack. |
| 9 | **A layered knowledge system** — moment tiers (`plan/`, `judge/`, `health/`, `evidence/`), per-module skills, and a corpus of worked runs. Originally designed as knowledge-kind tiers with cross-cutting `workflow/` guides; `workflow/` was never written and was retired, the rest were reorganised by the moment a reader stands in, and a distillation loop was designed to feed them and has never run. See [knowledge-system.md](knowledge-system.md) — read its STATUS section first. |
| 10 | **Local filesystem** for artifact store and image builds. Re-run from the last completed artifact rather than resuming in-flight jobs. |
| 11 | **`sfm_replay` adopted.** Going back upstream branches the DAG; nothing is marked stale; `sfm_compare` surfaces lineage divergence instead. |
| 12 | **Type safety via four guards** — pre-spawn type check, write-time schema validation in `sfmkit`, additive extension (required + optional arrays) instead of new type names, orphan-type warnings at registration. |
| 13 | **Scene analysis is a normal module family** producing `scene_analysis/v1`; derived traits key workflow retrieval. See [scene-analysis.md](scene-analysis.md). |
| 14 | **Claude drives all runs.** No config-driven CLI front end; the MCP surface is the only entry point. |

## Open questions

**Design is locked** as of 2026-08-07 except the two items below, neither of
which blocks starting work.

1. **Migration order.** Recommendation: build `sfmkit` + the artifact spec first,
   then prove all three contracts end to end on four modules
   (SIFT → LightGlue → union-find → COLMAP BA) before porting the other 19.
   Proceeding on this unless overridden.
2. **Trait-derivation location** — orchestrator or analysis module. See
   [scene-analysis.md](scene-analysis.md#open-question). Low-stakes; affects only
   what it costs to revise a threshold.

### Parked idea: a weights cache keyed on (module, weights, scene)

**Not implemented. Recorded so it can be reached for if it becomes a bottleneck.**

Artifact ids are derived from the RECIPE — module, version, slot, params, inputs —
which is what makes caching correct: the same recipe is the same artifact. It also
means two different modules share nothing, even when they run the same network
over the same images.

That is the price of one-role-per-module, and it is paid most visibly by the
feed-forward models. `PoseVGGT`, `SparseVGGT` and `DenseVGGT` each run a full VGGT
forward pass over the scene; the second and third recompute what the first already
had. The same applies to any pair of modules sharing a backbone.

**The fix, if needed:** a second cache layer INSIDE the module, keyed on
`(module_family, weights_hash, scene_id)` and holding the raw network output
rather than an artifact. The three VGGT modules would declare the same family and
the second run would find the tensors already computed. Storage is at a different
level from the artifact store, which stays recipe-addressed and unchanged.

**Why not now:** it adds a second notion of identity to a system whose single
notion of identity is its main simplification, and the cost it removes has not
been measured. Merging the modules to avoid the recompute would be the wrong
trade -- it is exactly the fixed-pipeline coupling this architecture exists to
remove, and `SparseVGGT` in particular must be able to accept tracks and poses
from other modules, which a merged module cannot.

## Build order

1. `sfmkit` — artifact I/O, manifest, schema validation, metrics, server harness.
   Everything depends on this and nothing depends on anything else.
2. The artifact spec and the core type registry (`scene/v1` … `dense_model/v1`).
3. The module contract proven on one trivial module, run in-process.
4. The orchestrator: registry, run DAG, type checking, artifact store — still
   in-process, no containers.
5. Containerize: `sfm-runtime` base, per-module images, server harness, GPU broker.
6. The MCP server over the orchestrator.
7. Port the four pilot modules; curate their skills; run the first human-led
   session; exercise the distillation loop.
8. Port the remaining 19.
