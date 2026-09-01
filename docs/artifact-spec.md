# Artifact Specification v1

The contract every module reads and writes. Implemented in
[`packages/sfmkit`](../packages/sfmkit); rationale in
[design/target-architecture.md](design/target-architecture.md).

## Store layout

```
<store_root>/
  artifacts/<artifact_id>/
      artifact.md              manifest (YAML frontmatter) + narrative (markdown body)
      data/<file>.npz          payload — one npz per file declared by the type
      data/<sidecar>/          optional native rendering (e.g. a COLMAP model)
  runs/<run_id>/
      run.md                   the attempt DAG and the session narrative
```

Artifacts live in **one flat global namespace**, not under a run. Ids derive from
the recipe, so five parallel pipelines on the same scene resolve to the same
`scene/v1` id and share one decode. Runs reference artifacts by id.

## Identity

```
artifact_id = "art_" + sha256(canonical_json({
    type, module, module_version, params, sorted(input_ids), salt
}))[:12]
```

Derived from the **recipe**, not the output bytes — so an id is known before the
work runs, which is what makes cache lookup possible. Consequences worth knowing:

- Identical recipes deduplicate. Re-running the same module with the same
  parameters on the same inputs is a no-op.
- Different parameters produce a *different* artifact and **keep the old one**.
  Nothing is ever overwritten; comparing attempts is the point.
- A `module_version` bump invalidates the cache, which is correct.
- Genuinely non-deterministic modules pass a `salt` to opt out of dedup.
- **A rebuilt image invalidates the cache too, and this is enforced rather than
  asked for.** The recipe covers module, version, slot, params and inputs — and
  none of those changes when a module's *code* does. The rule used to be that a
  human bumps `module_version` whenever a metric set or a published band changes;
  a rule is not a mechanism, and an uncommitted version that has already produced
  artifacts will hand them back after the code behind it is fixed. So before
  serving a cache entry the orchestrator compares the artifact's
  `produced_by.image_digest` against the digest of the image that would run now,
  and treats a mismatch as a miss.

  The failure mode this closes is nastier than a stale number: both times it
  happened here, the served value was a metric the new code *always* populates
  coming back null. That is indistinguishable from a code defect, and it costs a
  debugging session to rule out. It is conservative in both directions — a missing
  digest on either side is not evidence of staleness, so in-process runs and
  artifacts older than the field are served as before.

## `artifact.md`

One file, two audiences. YAML frontmatter is the machine-readable manifest;
the markdown body is the narrative the driving agent reads. They cannot drift
because they are the same file.

```yaml
---
id: art_7f3a91c04e2b
type: tracks/v1
run: run_20260807_dtu_scan1
scene: art_2b1c04                     # the scene/v1 artifact this is bound to
inputs: [art_2b1c04, art_9d4e77]      # provenance DAG, by id
produced_by:
  module: FeatureTrackFromPairsUnionFind
  module_version: 1.2.0
  image: sfmstack/track-union-find:1.0.0        # the tag that was asked for
  image_digest: sha256:9c1f...                 # the image that answered
  params: {min_track_len: 3, allow_pair_local_merge: true}
  started_at: '2026-08-07T14:22:11+00:00'
  duration_s: 41.2
  device: cpu
**`image` is a tag; `image_digest` is the answer.** A tag is mutable — two builds
of `sfmstack/track-union-find:1.0.0` are the same string and different software —
and artifact ids are recipe-derived, so they do not cover the image either. Without
the digest nothing in the record separates a result produced before a rebuild from
one produced after. It is read from the running CONTAINER rather than from the tag,
because a tag can move between the run and the read. Absent when the module ran
in-process: there was no image, and saying nothing is honest.

files:
  observations:
    path: data/observations.npz
    arrays:
      obs: {shape: [1482301, 4], dtype: float32, columns: [track_id, frame_idx, x, y]}
      track_count: {shape: [], dtype: int64}
metrics:
  avg_track_length: {value: 4.21, direction: higher_better, healthy: [3.0, null]}
  survival_ge_3:    {value: 0.62, direction: higher_better, healthy: [0.40, null]}
status: ok
diagnostics:
- code: short_tracks
  severity: warn
  message: Track survival past 3 views is 0.31.
  suggested_actions: [Increase the detector's max_keypoints.]
  see_also: tuning.md#survival_ge_3-below-040
extras:
  observations: [uncertainty]          # arrays present but not in the schema
---

Built 351,204 tracks from 39 image pairs. Survival past three views is 0.62,
above the 0.40 floor sparse reconstruction needs.
```

### Metrics carry their own interpretation

`direction` (`higher_better` | `lower_better` | `neutral` | `unknown`) and
`healthy` (a `[min, max]` band, either end nullable) travel with the value. This
is what replaces a separate, hand-maintained corpus explaining what each metric
means — the previous system had exactly that, and it went stale.

### Diagnostics point into the module's skills

`see_also` links to the section of the module's `tuning.md` or `limitations.md`
that addresses this condition, so the agent goes from "something is wrong" to the
specific curated guidance in one step.

## Payload types

A type declares which files an artifact holds, which arrays live in each, their
shapes and dtypes, and invariants. Core types ship in
`packages/sfmkit/src/sfmkit/types/*.yaml`.

```yaml
type: tracks/v1
files:
  observations:
    required: true
    arrays:
      obs:
        required: true
        shape: [null, 4]                # null = any length
        dtype: [float32, float64]
        columns: [track_id, frame_idx, x, y]
      track_count: {required: true, shape: [], dtype: [int32, int64]}
invariants:
  - check: max_plus_one_equals
    args: {file: observations, array: obs, column: 0, scalar: track_count}
```

Invariants are referenced **by name** from a registry
(`sfmkit/invariants.py`), never embedded as expressions — no schema file is ever
evaluated as code. Adding a check is adding a function and one registry entry.

### The two rules

**1. Extension is additive.** Arrays are `required` or optional, and a payload
may carry arrays the schema never mentions; they are recorded under `extras` so a
consumer can discover them. A module producing per-point uncertainty emits
`sparse_model/v1` with an extra array — it does **not** invent
`custom/sparse_with_uncertainty/v1`. Without this rule every new capability forks
a type and the graph fragments.

**2. A new version means a required field changed.** Everything else is additive.
A `v2` obliges the registry to carry a `v2 → v1` adapter.

## Validation — four guards

| Guard | Where | Catches |
| --- | --- | --- |
| Type check before spawn | orchestrator, on `run` | incompatible wiring — a pipeline cannot be built wrong |
| **Schema validation at seal** | `sfmkit`, in the producer | a module declaring `tracks/v1` and writing something else |
| Additive extension | schema design | type-set fragmentation |
| Orphan-type warning | build/registration | a module producing something nothing consumes |

The second is the one that prevents crashes. Structural problems (missing files,
wrong rank, wrong dtype, wrong column count) are reported **all at once**;
invariants run only once structure is sound, so a shape error never hides behind
a confusing semantic one.

A failed seal writes nothing. There is no half-finished artifact to confuse a
later run.

## Sidecars

The npz payload is always authoritative. A sidecar is an **additional** native
rendering of the same data:

```python
d = out.sidecar_dir("colmap")
reconstruction.write_binary(str(d))       # cameras.bin, images.bin, points3D.bin
```

```python
if (p := art.sidecar("colmap")):
    rec = pycolmap.Reconstruction(str(p))  # native, no rebuild
else:
    rec = build_from(art.load("points"), art.load("poses"))
```

This is what replaces the live `pycolmap.Reconstruction` object the old `Scene`
carried — previously the only unserializable handoff in the pipeline, and the
reason the whole thing had to run in a single process. A consumer without
pycolmap reads the npz and loses nothing but convenience.

## Lineage, not staleness

Re-running an upstream module **branches** the DAG. Nothing is marked stale: a
newer branch does not supersede an older one — it may well be worse, and that is
a judgment the orchestrator cannot make.

`ArtifactStore.ancestry(id)` returns the transitive input map. `sfm_compare`
uses it to report *where two artifacts' lineage diverges*, which is strictly more
useful than a staleness flag and stops the agent attributing a difference to the
parameter it just changed when it actually came from three stages up.

## Artifacts across a container boundary

The store is mounted into every container **at its own absolute path**, so an
artifact written by one module resolves identically in the next and no path
translation layer exists to get wrong.

Two consequences worth knowing:

- **Paths recorded inside an artifact must be resolved through
  `Artifact.resolve()`.** Relative paths resolve against the artifact root;
  absolute ones pass through. A producer that copies files in (SceneLoader with
  any resize policy) records them relatively and the artifact is self-contained.
  A producer that merely references external files records absolute paths, and
  those files must then be mounted into every downstream container too.

- **Containers run as the host user.** Docker defaults to root, and without
  `--user` everything a module writes into the shared store is root-owned: the
  operator cannot delete their own artifacts, and a later in-process run cannot
  write beside them. `DockerBackend` passes `--user $(id -u):$(id -g)` and sets
  `HOME=/tmp`, because a bare uid has no passwd entry and several libraries fall
  over resolving it.

Payload never crosses the wire. The HTTP control plane carries artifact ids,
parameters, metrics and diagnostics; the arrays move through the mounted
filesystem.
