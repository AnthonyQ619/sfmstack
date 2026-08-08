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
| 3 | Module contract proven in-process on one module | **done** (test suite) |
| 4 | Orchestrator: registry, run DAG, type checking, store | next |
| 5 | Containerize: `sfm-runtime` base, per-module images, GPU broker | |
| 6 | MCP server over the orchestrator | |
| 7 | Four pilot modules + curated skills + first driven session | |
| 8 | Port the remaining 19 modules | |

## Layout

```
packages/sfmkit/        the contract layer, installed into every module container
modules/                one directory per module: module.yaml, Dockerfile, adapter.py, skills/
orchestrator/           registry, scheduler, GPU broker, MCP server
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

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -e "packages/sfmkit[dev]"
.venv/bin/python -m pytest packages/sfmkit/tests -q
```

`sfmkit` depends on the standard library, numpy, and pyyaml — and must never
depend on anything else. It is installed into every module container, so each
dependency it takes is forced on modules pinning torch 2.6+cu124 *and* modules
pinning torch 2.11. See the note in `packages/sfmkit/pyproject.toml`.
