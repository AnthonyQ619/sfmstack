# The module contract

What every module must provide, what the framework checks, and what each family
owes on top of that.

This is the reference for writing a module or reviewing one. For *why* the
contract is shaped this way see
[design/target-architecture.md](design/target-architecture.md); for the payload
types themselves see [artifact-spec.md](artifact-spec.md).

---

## 1. The five obligations

A module is a directory under `modules/`. It owes five things, and the framework
checks four of them mechanically.

| # | Obligation | Checked by | When |
| --- | --- | --- | --- |
| 1 | `module.yaml` — the declaration | `ModuleSpec.read` | registry load |
| 2 | `adapter.py` — one `@module def run(ctx)` | the module server | first job |
| 3 | `Dockerfile` — one image, self-contained | `test_docker.py` | image build |
| 4 | `skills/` — five curated documents | `test_curated_skills_are_present` | test suite |
| 5 | The **metric contract** of every type it produces | `ModuleRegistry._check_metric_contract` | registry load |

Nothing here is advisory. A module missing any of 1, 3, 4 or 5 fails before it
runs — deliberately, because the alternative is discovering it after a
forty-minute dense reconstruction.

```
modules/<module_dir>/
  module.yaml          the declaration — see §2
  adapter.py           the code — see §3
  Dockerfile           the image — see §4
  skills/
    SKILL.md           what it does, when to reach for it, the reference run
    tuning.md          which metric to read first, then which parameter to move
    limitations.md     what it cannot do, and the ESCAPE for each
    artifact.md        how to read its output, and which metrics mislead
    sources.md         upstream papers, code, licences, predecessor differences
```

---

## 2. `module.yaml`

One file feeds four consumers that used to be maintained separately and drifted:
the MCP tool schema, the agent's documentation, plan validation, and metric
interpretation. Because they are generated from one source they cannot disagree.

### Required fields

| Field | Rule |
| --- | --- |
| `name` | Bare identifier, unique in the registry. It is the key, and it appears in every artifact's provenance. |
| `version` | Semver. Part of the artifact id, so a bump must be unambiguous. |
| `produces` | At least one slot. A module that produces nothing cannot be planned around. |

### Expected of every module

| Field | Purpose |
| --- | --- |
| `kind` | Family label — `detection`, `matching`, `tracking`, `pose`, `sparse`, `dense`, `optimization`, `analysis`. |
| `summary` | One or two sentences. This is what a listing shows. |
| `description` | What it does, **when to reach for it**, and what it gives up. |
| `image` | The tag the runner starts. Must match the Dockerfile's tag. |
| `entrypoint` | `adapter:run` unless there is a reason. |
| `resources` | `gpu`, `min_ram_gb`, `expected_duration_s`, `timeout_s`. |
| `consumes` | Slot name → `{type, required}`. Slot names are what a caller wires. |
| `params` | Every knob, with `type`, `default`, bounds, `description`, `tuning`. |
| `metrics` | Every metric emitted, with `direction`, `healthy`, `meaning`. |
| `diagnostics` | Every code the adapter can raise, with `suggested_actions` and `see_also`. |

### Rules that are enforced

- **Every declared payload type must be registered.** Either a core type or one
  declared in this manifest's own `types:` block.
- **Every metric the produced types require must be declared, with the direction
  the type fixes.** §5.
- **Every diagnostic needs a `code`.**
- **`see_also` must resolve to a real heading in a real skill file.** Checked by
  `test_every_diagnostic_anchor_resolves_to_a_real_heading`.
- **Every metric named in the manifest must appear in a skill document**, and vice
  versa. Checked by `test_every_metric_named_in_a_manifest_is_documented`.

### `params` — what makes one good

Every parameter carries a `description` (what it is) and a `tuning` note (when to
move it and what happens). The `tuning` note is what the agent reads, so it should
say the direction of the effect and the cost, not restate the name.

Bounds are not decoration. `minimum`/`maximum` are validated before the container
starts, so an out-of-range value fails in milliseconds rather than at the point in
the algorithm that divides by it.

---

## 3. `adapter.py`

```python
from sfmkit import Ctx, module

@module
def run(ctx: Ctx):
    scene = ctx.inputs["scene"]            # slot names from `consumes`
    p = ctx.params                          # validated against `params`

    ctx.progress(0.3, "detecting")          # any loop over a few seconds

    out = ctx.output("features")            # slot name from `produces`
    out.save("keypoints", xy=..., image_index=...)
    out.metric("keypoints_per_image", 3570, direction="higher_better",
               healthy=(500, None))
    out.diagnostic("sparse_coverage", severity="warn", message="...",
                   suggested_actions=[...], see_also="tuning.md#coverage")
    out.note("Free text. Becomes the artifact's markdown body.")
```

### What `Ctx` gives you

| | |
| --- | --- |
| `ctx.inputs[slot]` | An `Artifact`. `.load(file, array)`, `.has(file)`, `.resolve(path)`, `.sidecar(name)`, `.metric(name)`. |
| `ctx.params.<name>` | Validated, defaults applied. |
| `ctx.output(slot)` | An `ArtifactWriter`. The only way to produce output. |
| `ctx.progress(f, s)` | Optional but expected. It is the only thing distinguishing a working module from a wedged one. |
| `ctx.device` | The leased GPU index, or `None`. Usually unnecessary — the container sees one device as `0`. |
| `ctx.module_version` | For stamping into exports. |

### Rules

- **Fill exactly what the output type declares, and no more.** A module producing
  `poses/v1` writes poses even if its model also produced depth. The exception is
  algorithmic necessity — a global reconstructor that estimates poses *as part of*
  reconstructing must write both, because it cannot be given them. Every
  triangulator writes 3D points; that is what makes it one.
- **Additive extension is legal, replacement is not.** Writing an extra optional
  file a type declares (`intrinsics` beside `poses`) is fine. Changing the meaning
  of a required one is not.
- **Errors must name the fix.** A module that raises `ValueError("no points")`
  has told the caller nothing. Name the dominant rejection filter, its current
  value, and what to change.
- **A diagnostic before the raise.** `ctx.output(...)` can be called, given
  diagnostics, and then abandoned by raising — the diagnostics survive into the
  run record even though no artifact seals.
- **`warmup()` is optional** — a module-level function the server calls once so
  the first job does not pay for model loading.
- **No network at run time.** Weights are baked into the image. A module that
  downloads on first use fails on an air-gapped host, minutes into a run.

---

## 4. `Dockerfile`

One image per module, even where two would be identical, all `FROM` a shared
base so Docker stores the common layers once.

```dockerfile
FROM sfmstack/runtime:1.0            # or runtime-torch, runtime-lightglue, ...
RUN pip install --no-cache-dir "opencv-python-headless==4.10.0.84"
COPY modules/<module_dir> /module
```

- Build context is the repository root, always.
- The tag must match `image:` in the manifest.
- **A module needing a different torch does not build FROM the shared base.** It
  installs its own and pays full price. That is the correct outcome, and it is the
  case a single shared environment could not express at all.
- Weights are baked in a `cache_weights.py` step, at a fixed path named by an
  `ENV`, never left in a cache whose location follows `HOME`.

`tools/build_images.sh` builds everything in dependency order. sfmkit is COPYed
into `sfmstack/runtime`, so **any change to sfmkit invalidates every image** —
"rebuild the one I touched" is usually wrong.

---

## 5. The metric contract

Each payload type declares metrics that **every** producer must emit, with a fixed
`direction` and a canonical `meaning`. The `healthy` band stays per-module, because
what counts as healthy is method-specific.

This is the floor that makes two implementations of a stage interchangeable.
Payload shape alone does not let an agent ask which detector covered the scene
better if each reports it under a different name.

Enforced twice: at registry load (the manifest must declare them) and at seal
(the values must be present). Nullable metrics may be `None` — and a null is
informative, not an omission: `PoseVGGT` reports `mean_reprojection_error: null`
because it has no correspondences, and inventing a number from its own point maps
would report how self-consistent the network is rather than how accurate it is.

| Type | Required metrics |
| --- | --- |
| `scene/v1` | `n_images`, `megapixels`, `mixed_resolution` |
| `features/v1` | `keypoints_per_image`, `keypoints_min`, `spatial_coverage` |
| `pairwise_matches/v1` | `pairs_matched`, `matches_per_pair`, `min_matches_per_pair`, `inlier_ratio`, `graph_components`, `largest_component_fraction`, `planarity`\* |
| `tracks/v1` | `track_count`, `avg_track_length`, `long_track_fraction`, `min_frame_observations`, `inconsistent_rate`, `split_rate`, `trifocal_transfer_px`\*, `median_track_length`, `track_survival_5` |
| `poses/v1` | `registered_fraction`, `registered_images`, `mean_reprojection_error`\*, `median_reprojection_error`\* |
| `sparse_model/v1` | `point_count`, `observation_count`, `mean_reprojection_error`\*, `registered_images` |
| `dense_model/v1` | `point_count`, `views_contributing`, `mean_depth_confidence`\* |

\* nullable.

Three metrics were required and were removed after review, and the reasoning is
the rule for anything proposed next: `track_survival_10` is necessarily 0 on any
set under ten images, `max_track_length` is one order statistic of a distribution
already described four ways, `frames_covered` fires only when a frame is
completely empty while `min_frame_observations` catches that case *and* the frame
that is merely too thin to register, and `mean_track_length` is EXACTLY
`observation_count / point_count`. **A required metric has to add a degree of
freedom, not a name.** Each survives as a module-specific metric where a module
actually routes on it.

The `healthy` bands are the softest part of this contract: each is one author's
reference run, mostly DTU scan1 at eight images. They are an orientation, not a
validated threshold, and a `warning` means "look at this", never "this failed".
**They are due a revision pass from the agent-driven runs**, which will be the
first evidence spanning more than one scene per module.

Modules add whatever else they measure. The contract is a floor, not a ceiling.

---

## 6. What each family owes

Everything above applies to every module. This section is what is *additionally*
true of each family — the payload it fills, the shape of its inputs, and the
obligations that are specific to the stage.

### Feature detection

`scene/v1` → `features/v1`

**Needs** `scene.images` — `paths`, `size_current`. **No calibration.** A
detector reads pixels and reports where things are; intrinsics play no part.

**Fills** `keypoints` (`xy`, `image_index`, optional `scores`/`scale`/`orientation`)
and optionally `descriptors`.

- `image_index` must be **sorted ascending**. Consumers slice on it.
- Coordinates are in the scene's **working** resolution, never the original.
- `descriptors` is optional and its absence is meaningful: a detector-free method
  has no descriptor stage, and forcing an empty array would be a lie about what
  was computed.
- `spatial_coverage` is the metric that separates "found 4000 keypoints" from
  "found 4000 keypoints on one textured corner".

*Members:* `FeatureDetectionSIFT`, `FeatureDetectionORB`,
`FeatureDetectionSuperPoint`, `FeatureDetectionALIKED`.

### Feature matching

`scene/v1` (+ `features/v1`) → `pairwise_matches/v1`

**Needs** `scene.images` — `paths`, `size_current`. **No calibration**, including
for geometric verification: the fundamental matrix is estimated in pixels and needs
no K. Detector-free matchers (`FeatureMatchLoFTR`, `FeatureMatchRoMa`) take no
`features/v1` at all and read the images directly.

**Fills** `pairs` (`image_pair`) and `matches` (`xy`, `pair_index`, optionally
`feature_index`).

- `features` is **required for detector-based matchers and absent for
  detector-free ones**. That difference is the whole distinction, and it
  propagates: `feature_index` is present only when there is a keypoint table to
  index, and its absence is what forces the tracker into proximity merging.
- **Geometric verification is the matcher's job**, not the tracker's. `inlier_ratio`
  is reported over the verified set.
- `graph_components` and `largest_component_fraction` describe the **view graph**,
  and they are the numbers that predict whether registration will stall. A matcher
  reporting a high `matches_per_pair` and three components has not produced a
  reconstructable scene.

*Members:* `FeatureMatchNN`, `FeatureMatchFLANN`, `FeatureMatchLightGlue`,
`FeatureMatchSuperGlue`, `FeatureMatchLoFTR`, `FeatureMatchRoMa`.

### Feature tracking

`scene/v1` + (`pairwise_matches/v1` | `features/v1`) → `tracks/v1`

**Needs** `scene.images` — `size_current`, and `paths` for the predictive
trackers, which re-read the pixels. **`scene.calibration` is OPTIONAL for all
three**, and used for exactly one thing: `trifocal_transfer_px`, which reports null
without it. Which second input is required is the family's real fork —
`FeatureTrackUnionFind` needs `pairwise_matches/v1`, the two learned trackers need
`features/v1` and no matcher runs at all.

**Fills** `observations` (`obs` as `[track_id, frame_idx, x, y]`, `track_count`,
optional `visibility`).

- `track_id` must be **dense in `[0, track_count)`**. Checked by an invariant.
- **Two input shapes exist and they are not interchangeable.** A chaining tracker
  consumes `pairwise_matches/v1`; a predictive one consumes `features/v1` and no
  matcher runs at all. Both land on `tracks/v1`, which is what lets them be
  swapped without touching anything downstream.
- `visibility` is written when the module predicts one, and its absence is
  meaningful: chaining verified matches produces no such number.
- **`inconsistent_rate` and `split_rate` are duals and both are required.** The
  first detects over-merging (one track holding two scene points), the second
  splitting (one scene point across several tracks). A chaining tracker can do
  both; a predictive one structurally cannot over-merge, so its `inconsistent_rate`
  is zero and carries no information — which its skills must say rather than
  presenting as a clean bill of health. Both are computed by sfmkit at tolerances
  the TYPE fixes, not the module, because their purpose is cross-tracker comparison.
- **`trifocal_transfer_px` is the only positional metric.** Everything else in the
  type is length, coverage or self-consistency, and a track table can be excellent
  on all of them while being several pixels off. It is a held-out three-view
  prediction — two views are not enough, because a matcher verifies pairs
  independently and a chaining tracker's observations satisfy every epipolar
  constraint by construction. One measurement is one observation in one image — the
  distance between where the tracker put the point and where geometry fitted from
  *other* tracks says it belongs, in that image's pixels at working resolution —
  and the metric is their median. Nullable: an uncalibrated scene cannot support it.

*Members:* `FeatureTrackUnionFind`, `FeatureTrackVGGSfM`, `FeatureTrackTapir`.

### Pose estimation

`scene/v1` + (`tracks/v1` | nothing else) → `poses/v1`

**Needs** `scene.images` — `size_current`, and `paths` for a module that looks at
pixels. **Calibration splits the family in two:** `PoseEssentialToPnP` REQUIRES
`scene.calibration` and raises a named diagnostic without it; `PoseVGGT` treats it
as optional, estimates its own intrinsics, and measurably does better without a
supplied K. That split is the reason an uncalibrated scene is a first-class state
rather than an error.

**Fills** `poses` (`cam_from_world` as (N, 3, 4), `valid`, `image_index`), and
optionally `intrinsics`.

- **`cam_from_world`**: `X_camera = R @ X_world + t`. There is one convention and
  this is it.
- `valid` is not decoration. An unregistered image must be marked, never written
  as identity, and every consumer filters on it.
- **`intrinsics` is written only by a module that ESTIMATED them.** A module that
  read them from the scene omits the file. A consumer finding the file prefers it,
  because a pose estimated with its own K is not consistent with anyone else's.
- `mean_reprojection_error` is nullable, and null is the honest answer for a
  feed-forward estimator with no correspondences.

*Members:* `PoseEssentialToPnP`, `PoseVGGT`.

### Sparse reconstruction

`scene/v1` + … → `sparse_model/v1`

**Needs** `scene.images.size_current`, plus `paths` for a module that looks at
pixels. **Calibration is required by every geometric member and optional for every
feed-forward one**: `SparseTriangulationGTSAM`, `SparseGlobalCOLMAP` and
`DenseMVS`'s upstream raise without it, `SparseTriangulation` accepts it *or*
`poses.intrinsics` — the one module with a genuine fallback — and `SparseVGGT` /
`SparseMapAnything` prefer their own estimate.

**Fills** `points` (`xyz`, optional `rgb`/`error`/`track_id`), `observations`
(`obs` as `[frame_idx, point_index, x, y]`), `poses`, and optionally `intrinsics`.

- **The npz is always authoritative.** A COLMAP-backed producer additionally writes
  a `colmap` sidecar so a pycolmap consumer can open the reconstruction natively;
  a consumer without pycolmap reads the npz and loses nothing.
- **Observations are in UNDISTORTED pixels.** There is no distortion array here by
  construction — a producer working in distorted pixels would be changing the
  meaning of `observations`, not adding to it.
- `poses` is required even for a pure triangulator, which passes its input through
  unchanged. That is what makes the artifact self-contained.
- **Every triangulator fills 3D points; that is what makes it one.** A global
  reconstructor that also estimates poses is the documented exception, because the
  algorithm cannot be given them.

*Members:* `SparseTriangulation`, `SparseTriangulationGTSAM`, `SparseVGGT`,
`SparseMapAnything`, `SparseGlobalCOLMAP`.

### Optimization

`sparse_model/v1` → `sparse_model/v1`

**Needs** the `sparse_model/v1` it refines, plus `scene.images.size_current`.
`scene.calibration` is OPTIONAL — the model's own intrinsics take precedence when
present, and the scene is the fallback. Note that `points.track_id` is optional in
the type and most producers omit it; a consumer must handle its absence.

Same type in and out, which is what makes it composable and what makes its
metrics tricky.

- **The type's required metrics describe the ARTIFACT, not the process.** A bundle
  adjuster's interesting numbers are before/after; those go in *additional*
  metrics. `mean_reprojection_error` still means "the error of this model".
- **Error is never comparable across differing camera or point counts.** A
  reconstruction that improves its error by dropping cameras got worse.
  `registered_images` beside it is what catches that.

*Members:* `BundleAdjustmentGlobal`, `BundleAdjustmentLocal`.

### Dense reconstruction

`scene/v1` + (`sparse_model/v1` | `poses/v1`) → `dense_model/v1`

**Needs** `scene.images.paths` — dense methods re-read the pixels, always.
`DenseMVS` REQUIRES `scene.calibration` (an uncalibrated scene supplies neither
intrinsics nor a model that carries them); `DenseVGGT` treats it as optional and
prefers its own.

**Fills** `points` (`xyz`, optional `rgb`/`normals`), optionally `depth`, and by
convention a `ply` sidecar.

- **Depth maps are only expressible when every view shares a resolution.** A
  producer with ragged depth omits the array rather than padding, which would
  silently corrupt downstream metrics.
- **A `cloud.ply` sidecar is written through `sfmkit.write_ply`**, so the format is
  identical whichever module produced it. It is what MeshLab, CloudCompare, Open3D
  and evaluation scripts read; the npz stays authoritative.
- `mean_depth_confidence` is nullable, and null is correct for a method that
  expresses uncertainty by deleting pixels rather than scoring them.
- **A dense module that unprojects a learned depth must resolve the scale
  explicitly** and report it with its spread. Assuming it is 1.0 produces a cloud
  that is correctly shaped and wrongly placed, with no metric moving.

*Members:* `DenseMVS`, `DenseVGGT`.

### Scene analysis

`scene/v1` → `scene_analysis/v1`

**Needs** `scene.images.paths` for anything reading pixels; the `metadata` group
needs only the paths themselves. **No calibration** — the point is to characterise
a scene before anything is known about it.

*Members:* `SceneTriage` (CPU), `SceneMotion` (GPU).

- Every file is optional: an analyser fills the facets it measures and omits the
  rest, so a triage module and a motion module both produce the type honestly.
  `SceneTriage` fills `metadata`, `photometric` and `texture`; `SceneMotion`
  fills `motion` and `degeneracy`. They are two artifacts of one type with
  disjoint groups, and nothing merges them — the agent reads whichever are
  present.
- **Absent is not zero.** A cue that could not be measured is omitted, and its
  metric is reported as null. `pure_rotation_risk` needs intrinsics; on an
  uncalibrated scene a zero would read as "no rotation detected" when the truth
  is "the test could not run".
- **Thresholds do not live here.** The analyser emits numbers; what counts as
  "narrow baseline" belongs in `skills/judgment/`.
- **`traits` has no producer, and that is deliberate.** It is the one declared
  group neither module fills. Deriving it is the orchestrator's job, from
  thresholds in `skills/judgment/`, so that revising a cut point does not
  invalidate every analysis already computed. Until `judgment/` is written,
  trait-based retrieval does not run — see
  [mcp-tools.md](mcp-tools.md#4-the-empty-tiers--which-tools-read-them-and-what-does-not-work).
- This is the only family whose output no module consumes. The orphan warning
  at registry load is expected: `scene_analysis/v1` is read by the agent, not by
  a pipeline stage.

---

## 7. Adding a module — the order that works

1. **Pick the payload types first.** What it consumes and produces decides
   everything else, and it is the only decision that is expensive to change.
2. **Write `module.yaml`** including the metrics. Load the registry — the metric
   contract will tell you what you missed before you write any code.
3. **Write `adapter.py`** against a fixture or a small real scene, in-process,
   with `SubprocessBackend` or no runner at all.
4. **Write the Dockerfile**, build, and run the same thing in a container. Bake
   weights at this point, not later.
5. **Run it on a real scene and record the numbers.** The reference run in
   `SKILL.md` and `tuning.md` comes from here, and the module is not finished
   without it — a tuning note with no measurement behind it is a guess with
   formatting.
6. **Write the five skills.** `sources.md` last, including what differs from any
   predecessor implementation.
7. **Run the suite.** The structural tests cover the contract; what they cannot
   cover is whether the numbers are right.
