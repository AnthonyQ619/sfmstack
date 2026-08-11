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
| 5 | Containerize: `sfm-runtime` base, per-module images, module server, GPU broker | **done** |
| 6 | MCP server over the orchestrator | **done** |
| 7b | `FeatureMatchNN`, `FeatureTrackUnionFind` — scene → features → pairs → tracks | **done** |
| 7c | Pose, triangulation, bundle adjustment — a complete classical pipeline | **done** |
| 7d | ORB, FLANN, SuperPoint, ALIKED, LightGlue, LoFTR | **done** |
| 8 | The remaining 9 legacy modules | in progress |
| 9 | First agent-driven session over MCP | |

18 modules, 277 tests. `.venv/bin/python -m pytest -q`

A complete classical reconstruction runs end to end on DTU scan1 — 12 contiguous
images at 1024px, every stage in its own container:

```
SceneLoader           12 images, 0.64x downscale
FeatureDetectionSIFT  3570 keypoints/image, coverage 0.81
FeatureMatchNN        64 pairs, inlier ratio 0.96, 1 graph component
FeatureTrackUnionFind 7014 tracks, 52% reaching 3+ views, conflicts 0.005
PoseEssentialToPnP    12/12 registered, seeded on images 0 and 8 at 25 degrees
SparseTriangulation   6941 points, 22743 observations, 0.376 px
BundleAdjustmentGlobal                                 0.253 px, converged
```

## Containers

Every module gets its own image, even where two would be identical. All of them
build `FROM` a shared base, so Docker stores the common layers once:

```
sfmstack/runtime          415 MB   sfmkit only — the tracker's image IS this
  + opencv                179 MB   shared by SIFT, ORB, NN, FLANN, pose, triangulation
  + pycolmap                       shared by both bundle adjusters
  + pillow                 21 MB   SceneLoader
sfmstack/runtime-torch    5.8 GB   torch cu124 + git
  runtime-lightglue       6.2 GB   + lightglue + baked weights
                                   shared by SuperPoint, ALIKED, LightGlue
```

```
sfmstack/runtime-kornia          + kornia + LoFTR weights
```

Fourteen module images cost four bases plus a few MB of unique layer each. That
sharing is what makes strict one-image-per-module affordable — and kornia is
deliberately *not* in the lightglue base, because the predecessor's two conda
environments pinned kornia 0.8.1 and 0.7.1 and could not be reconciled.

## Modules

| stage | module | backend | GPU |
| --- | --- | --- | --- |
| source | `SceneLoader` | Pillow | |
| detection | `FeatureDetectionSIFT` | OpenCV | |
| | `FeatureDetectionORB` | OpenCV + ANMS-SSC | |
| | `FeatureDetectionSuperPoint` | lightglue | ✓ |
| | `FeatureDetectionALIKED` | lightglue | ✓ |
| matching | `FeatureMatchNN` | OpenCV brute force | |
| | `FeatureMatchFLANN` | OpenCV FLANN | |
| | `FeatureMatchLightGlue` | lightglue | ✓ |
| | `FeatureMatchSuperGlue` | magicleap SuperGlue | ✓ |
| | `FeatureMatchLoFTR` | kornia, **detector-free** | ✓ |
| | `FeatureMatchRoMa` | romatch, **detector-free** | ✓ |
| tracking | `FeatureTrackUnionFind` | numpy only | |
| pose | `PoseEssentialToPnP` | OpenCV + pycolmap (in-loop local BA) | |
| sparse | `SparseTriangulation` | OpenCV | |
| | `SparseTriangulationGTSAM` | GTSAM LOST, multi-view | |
| | `SparseGlobalCOLMAP` | pycolmap global mapping (GLOMAP) | |
| optimization | `BundleAdjustmentGlobal` | pycolmap / Ceres | |
| | `BundleAdjustmentLocal` | pycolmap / Ceres | |

`SparseGlobalCOLMAP` estimates poses itself and consumes `pairwise_matches/v1`
directly, so the chain through it is scene → detect → match → reconstruct, with no
tracker and no pose estimator in it.

Still to port: VGGT (pose/sparse/dense), MapAnything, VGGSfM, Tapir,
PatchMatch MVS.

```bash
docker build -t sfmstack/runtime:1.0         -f docker/runtime/Dockerfile .
docker build -t sfmstack/runtime-torch:1.0   -f docker/runtime-torch/Dockerfile .
docker build -t sfmstack/runtime-lightglue:1.0 -f docker/runtime-lightglue/Dockerfile .
# then one per module, e.g.
docker build -t sfmstack/feature-sift:1.0.0  -f modules/feature_sift/Dockerfile .
```

### GPUs

`resources.gpu: true` modules need the NVIDIA container toolkit wired into the
Docker daemon — having GPUs on the host is not enough. Without it `DockerBackend`
falls back to CPU with a warning naming the fix; pass `cpu_fallback=False` to make
it an error.

**GPU passthrough works** (toolkit 1.19.1, 8 x RTX A6000, driver 580.159.03).
A container is given exactly the device the `GpuBroker` leased it — `--gpus
device=N`, never `all` — and a container with no lease sees no GPU at all. Measured
module time in containers, DTU at 1024px:

| module | CPU container | GPU container |
| --- | ---: | ---: |
| `FeatureDetectionSuperPoint` (10 images) | 10.1 s | 0.9 s |
| `FeatureMatchLightGlue` (9 pairs) | 6.1 s | 0.7 s |
| `FeatureMatchLoFTR` (17 pairs) | 80.0 s | 4.0 s |

If a host lacks the toolkit, see `docs/design/gpu-container-handoff.md`.

```python
runner = ContainerRunner(
    DockerBackend(mounts=["/home/anthonyq/datasets"]),
    gpus=GpuBroker(),
)
orch = Orchestrator(store=store, registry=registry, runner=runner)
```

`SceneLoader` has Pillow and no OpenCV; `FeatureDetectionSIFT` has OpenCV and no
Pillow; `FeatureTrackUnionFind` has neither. None could run in another's image,
and they compose through the artifact store.

### Long jobs

Modules range from a two-second union-find to a forty-minute dense
reconstruction, so nothing in the call path assumes a job is quick.

`module.yaml` declares `resources.expected_duration_s` — a hint, not a limit —
and the service refines it from observed runs. That decides whether a call blocks
inline or hands back a job id:

```
SceneLoader (declared 30s):  returned in 1.0s  status=running  poll_after_s=14.5
      13%  reading 5/30
      53%  reading 17/30
      97%  reading 30/30
   -> ok in 16.0s        learned estimate: 16.0s
```

A single global wait cannot serve both ends: it either blocks pointlessly on the
slow modules or round-trips pointlessly on the fast ones. Cache hits are the
exception and are always waited for — they return instantly whatever the module
normally costs.

Every unfinished response carries `poll_after_s`, so the caller never has to
guess a cadence. Modules call `ctx.progress(fraction, stage)` from any loop that
runs more than a few seconds; it is the only thing that distinguishes a working
module from a wedged one on a twenty-minute job.

Servers stay **warm** between jobs — a second SIFT run against the same container
skips startup entirely, which is the case a parameter sweep hits constantly. Idle
servers are reaped on a TTL, and under GPU pressure the least recently used one
is evicted rather than the request failing. One module holds one GPU exclusively.

`SubprocessBackend` runs the same server as a local process for development and
for testing the container path without Docker. The orchestrator cannot tell any
of the three runners apart.

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

**3. The module server API** — `/healthz`, `/manifest`, `POST /run`,
`GET /jobs/<id>`, `POST /jobs/<id>/cancel`. Implemented once in `sfmkit.server`,
on `http.server`: it ships in every container, so a web framework here would
become a dependency of modules pinning conflicting torch and numpy majors. The
control plane carries ids and parameters only — every byte of payload moves
through the mounted artifact store, so throughput is not a consideration.

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

scene  = orch.run("SceneLoader",           run_id="r1", params={"image_dir": ...}).primary
feats  = orch.run("FeatureDetectionSIFT",  run_id="r1", inputs={"scene": scene.id}).primary
pairs  = orch.run("FeatureMatchNN",        run_id="r1", inputs={"scene": scene.id, "features": feats.id}).primary
tracks = orch.run("FeatureTrackUnionFind", run_id="r1", inputs={"scene": scene.id, "matches": pairs.id}).primary
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

## Driving it over MCP

```bash
.venv/bin/python -m sfmorch.mcp_server \
    --modules ./modules --store ./store --skills ./skills \
    --docker --mount /home/anthonyq/datasets
```

Seventeen tools in five categories — discovery, execution, inspection,
knowledge, authoring. **The count does not grow with the module count.** Modules
are discovered through `sfm_list_modules` / `sfm_describe_module`, never
enumerated as tools, so the surface is the same at two modules and at two
hundred.

What that looks like in practice:

```
sfm_run(SceneLoader, {image_dir: .../DTU/scan1, max_edge: 1024})
  → {n_images: 6, downscale_factor: 0.64, ...}

sfm_run(FeatureDetectionSIFT, {max_keypoints: 512})
  → {keypoints_per_image: 512.3, saturation: 1.0, spatial_coverage: 0.602}
    [info] cap_binding → tuning.md#saturation-near-10

sfm_module_skill(FeatureDetectionSIFT, "tuning")
  → "## saturation near 1.0 — the cap is what limits detection, not the image
     content. Gradient: max_keypoints ×2 ..."

sfm_run(FeatureDetectionSIFT, {max_keypoints: 8192})
  → {keypoints_per_image: 3564.2, saturation: 0.0, spatial_coverage: 0.799}

sfm_compare([low, high])
  → FeatureDetectionSIFT (features/v1): max_keypoints 512 -> 8192
```

Metrics arrive with `direction` and a `healthy` band, so whether a number is good
is in the response rather than in the caller's head. A diagnostic's `see_also`
names the exact curated section that addresses it. When tuning bottoms out,
`sfm_module_skill(name, "limitations")` gives a failure signature and a
capability query, and `sfm_find_alternatives` runs that query against the live
registry — which is why escapes are written as queries and never as module names.

New modules come from `sfm_scaffold_module` → implement the adapter →
`sfm_build_module` → `sfm_smoke_test`. The scaffolded adapter raises until
implemented: a stub that silently produces an empty artifact looks like a
successful reconstruction, which is worse than a refusal.
