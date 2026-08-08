# sfmstack

A Structure-from-Motion framework built so that **every module is an independent
container**, artifacts flow between them as typed directories on disk, and an
agent drives the pipeline over MCP — reading metrics, tuning parameters,
switching modules, and authoring new ones.

Successor to [`scene_agent`](../scene_agent). No backwards compatibility; see
[`scene_agent/skills/overview/`](../scene_agent/skills/overview/) for what the
previous system did and why this one exists.

## Status

Early. Build order and progress:

| # | Step | State |
| --- | --- | --- |
| 1 | `sfmkit` — artifact I/O, schemas, validation, module contract | **done** |
| 2 | Artifact spec + core type registry | **done** |
| 3 | Module contract proven in-process | **done** |
| 4 | `sfmorch` — module registry, type checking, run DAG, replay, lineage | **done** |
| 7a | First real modules: `SceneLoader`, `FeatureDetectionSIFT`, with curated skills | **done** |
| 5 | Containerize: `sfm-runtime` base, per-module images, GPU broker | next |
| 6 | MCP server over the orchestrator | |
| 7 | Four pilot modules + curated skills + first driven session | |
| 8 | Port the remaining 19 modules | |

128 tests, including integration against real DTU and ETH3D data.
`.venv/bin/python -m pytest -q`

## Layout

```
packages/sfmkit/        the contract layer, installed into every module container
packages/sfmorch/       registry, type checking, run DAG, scheduling, MCP server
modules/                one directory per module: module.yaml, Dockerfile, adapter.py, skills/
skills/                 the knowledge base the driving agent reasons over
docs/design/            the architecture, and why it is shaped this way
```

## The three contracts

Everything else is implementation detail inside a container.

**1. The artifact** — an immutable, typed directory.

```
artifacts/<artifact_id>/
    artifact.md        YAML frontmatter (manifest) + markdown body (narrative)
    data/*.npz         payload, one npz per declared file
    data/<sidecar>/    optional native rendering, e.g. a COLMAP model
```

One file, two audiences: the frontmatter is what the orchestrator validates and
routes on, the body is what the agent reads. Artifacts are write-once and their
ids derive from the *recipe* (module, version, params, inputs), so identical work
deduplicates and re-running with new parameters keeps both attempts.

**2. The module manifest** — `module.yaml` declares identity, `consumes` and
`produces` types, a parameter schema, metric meanings, and diagnostics. One file
feeds the MCP tool schema, the agent's documentation, type-based plan validation,
and metric interpretation.

**3. The module server API** — `/healthz`, `/manifest`, `POST /run`, `GET /jobs/<id>`.

## Payload types

Modules declare I/O in terms of named, versioned types, which is what lets the
orchestrator check a pipeline before spawning anything and what makes
"find me something that produces `tracks/v1`" a query.

`scene/v1` · `scene_analysis/v1` · `features/v1` · `pairwise_matches/v1` ·
`tracks/v1` · `poses/v1` · `sparse_model/v1` · `dense_model/v1`

The set is open — a module may declare `custom/<name>/v1` — but **extension is
additive**: a module adding per-point uncertainty emits `sparse_model/v1` with an
extra optional array rather than forking a new type. Consumers ignore arrays they
do not know. This is the rule that keeps an open type system from fragmenting.

## Writing a module

```python
from sfmkit import module, Ctx

@module
def run(ctx: Ctx):
    obs = ctx.inputs["pairs"].load("matches", "xy")
    tracks, n = union_find(obs, min_len=ctx.params.min_track_len)

    out = ctx.output("tracks")
    out.save("observations", obs=tracks, track_count=np.int64(n))
    out.metric("avg_track_length", 4.21, direction="higher_better", healthy=(3.0, None))
    out.note(f"Built {n} tracks from {len(obs)} correspondences.")
```

Provenance, timing, schema validation, and manifest rendering are handled for
you. Validation runs when the artifact is sealed, in the **producing** process —
a module that declares `tracks/v1` and writes something else fails there, not in
a consumer three stages later.

`module.yaml` alongside it declares identity, I/O types, parameters, metric
meanings, and diagnostics. That one file feeds the MCP tool schema, the agent's
documentation, plan validation, and metric interpretation, so those four cannot
drift apart.

## Running a pipeline

```python
orch = Orchestrator(store=ArtifactStore("store"), registry=registry)

scene  = orch.run("MakeScene",   run_id="r1", params={"n_images": 6}).primary
feats  = orch.run("SIFT",        run_id="r1", inputs={"scene": scene.id}).primary
pairs  = orch.run("LightGlue",   run_id="r1", inputs={"scene": scene.id, "features": feats.id}).primary
tracks = orch.run("UnionFind",   run_id="r1", inputs={"scene": scene.id, "pairs": pairs.id}).primary
```

The orchestrator refuses a step whose input types do not match **before** running
anything, skips work whose recipe is already on disk, and records every attempt
in `runs/<run_id>/run.md`.

When the metrics say the problem is upstream, one call re-runs that step and
everything downstream of it:

```python
results = orch.replay(run_id="r1", from_artifact=pairs.id, overrides={"keep_ratio": 1.0})
```

The original branch is untouched. Nothing is ever marked "stale" — a newer branch
does not supersede an older one, it may well be worse. `orch.compare([a, b])`
puts the metrics side by side **and** reports where the two lineages parted
company, so a difference inherited from three stages up is not credited to the
knob under test.

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -e "packages/sfmkit[dev]" -e "packages/sfmorch[dev]"
.venv/bin/python -m pytest -q                    # everything
.venv/bin/python -m pytest packages -q           # hermetic units only
```

Real modules bring their own dependencies (`pillow`, `opencv-contrib-python-headless`
so far). Installing them into this one venv is a development convenience and is
exactly the monolith the container step exists to dissolve — the integration
tests skip cleanly when a module's dependencies or its dataset are absent.

`sfmkit` depends on the standard library, numpy, and pyyaml — and must never
depend on anything else. It is installed into every module container, so each
dependency it takes is forced on modules pinning torch 2.6+cu124 *and* modules
pinning torch 2.11. See the note in `packages/sfmkit/pyproject.toml`.
