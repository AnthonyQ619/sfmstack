---
name: scene-analysis
description: The scene triage layer: cue extractors that characterize a dataset before any reconstruction runs, producing a scene_analysis/v1 artifact whose derived traits drive workflow retrieval and initial module selection.
status: partly built 2026-08-14 — SceneTriage and SceneMotion exist; trait derivation does not
---

> **Build note, 2026-08-14.** `SceneTriage` and `SceneMotion` are implemented and
> their images are built. Both ports landed with the three fixes named below.
> What is built, against what this document proposed:
>
> | Proposed | State |
> | --- | --- |
> | `SceneMotion` from `optical_flow.py` | **built**, six of the seven motion signals — `large_motion_risk_score` was ported, measured against ten scenes, and cut |
> | illumination block of `SceneTriage` | **built**, measurements and weights unchanged |
> | pure-rotation and planar degeneracy tests | **built**, and verified synthetically |
> | texture: density, repetitiveness, textureless fraction, sharpness | **built** |
> | metadata: ordering, capture interval, EXIF focal | **partly** — ordering is a filename heuristic; the EXIF cues need the new `source_dir` parameter, because `SceneLoader` re-encodes and drops EXIF |
> | EXIF sanity-check of supplied calibration, GPS | not built |
> | view-graph shape, dynamic content | not built |
> | **trait derivation** | **not built**, and blocked on thresholds the global skills tier deliberately does not name — see below |
> | `sfm_open_scene` auto-runs `SceneTriage` | not built; there is no `sfm_open_scene` tool, and `SceneTriage` is an ordinary `sfm_run` |
>
> The open question at the end of this document — orchestrator or module — was
> answered in favour of the orchestrator, and the modules honour it: neither
> writes the `traits` group, and a test asserts they do not.

# Scene Analysis

Feeds retrieval in [knowledge-system.md](knowledge-system.md).

The agent should know what kind of scene it is facing **before** it runs anything.
That is what turns "try a pipeline and see" into "scenes like this one have been
solved this way." Concretely: the L-0061 episode — four wasted tuning runs on a
repetitive brick facade — was avoidable, because repetitive texture is measurable
from the inputs in seconds.

## Design: cue extraction is a normal module

No special mechanism. Cue extractors are modules like any other: containerized,
manifest-declared, producing a typed artifact.

```
scene/v1  ──►  SceneTriage   (CPU, cheap, always run)   ──►  scene_analysis/v1
          └─►  SceneMotion   (GPU, opt-in)              ──►  scene_analysis/v1
          └─►  <your new extractor>                     ──►  scene_analysis/v1
```

This answers "single tool or extensible" with **both**: today it is two modules;
adding a cue is either a new extractor inside an existing module (when the
dependencies are compatible) or a new module producing the same type (when they
are not). Extensibility comes free from the framework rather than needing its own
plugin system.

`scene_analysis/v1` has **all field groups optional** (per the additive-extension
rule for payload types),
so partial producers compose without a merge step. The agent reads whichever
groups are present.

Two properties worth having:

- **Content-addressed and cached.** Analysis is deterministic per (scene, image
  list). RAFT over 40 pairs is not free; computing it once and sharing it across
  every run and session on that scene is a large saving — same treatment as
  `scene/v1`.
- **`sfm_open_scene` auto-runs `SceneTriage`.** It is cheap and CPU-only, so the
  agent always has basic traits without an extra decision.

## What exists today

Both live in
`scene_agent/breadth_agent/src/agent/core/utility/` (the predecessor repository)
and are better than their obscurity suggests. Port, don't rewrite.

### `optical_flow.py` → `SceneMotion` (GPU)

RAFT-large dense flow over consecutive pairs, normalized by image diagonal, then
summarized:

| Signal | Meaning |
| --- | --- |
| `overall_motion_magnitude_score` | median p75 flow — apparent motion overall |
| `high_motion_tail_score` | median p90 flow — severity of the fast regions |
| `motion_variability_score` | IQR of p75 — consistency pair to pair |
| `low_baseline_risk_score` | fraction of pairs below the parallax floor |
| `large_motion_risk_score` | fraction of pairs above the matching ceiling |
| `rotation_change_deg_median` | via essential matrix from flow, when calibrated |
| `large_rotation_risk_score` | fraction of pairs past 20° |

Carry over as-is. Three fixes on the way: it imports `from modules.utilities`
(stale), it loads RAFT at **module import time** (`optical_flow.py:17` — a global
side effect that must move into the module's warm-start), and it returns a
pre-formatted English string rather than structured values. In the new design it
emits numbers into the artifact; the prose lives in `artifact.md` and the module's
skills.

### `illumination_analysis.py` → part of `SceneTriage` (CPU)

Pure OpenCV. Per-image LAB luminance/chroma stats and clipping ratios, pairwise
histogram distances, then dataset-level p75 scores for
`illumination_change`, `color_shift`, `exposure_shift`, and a combined score, each
with LOW/MEDIUM/HIGH labels and a worst-pairs list.

It already contains `make_agent_interpretation()`, which emits
`expected_failure_modes` and `recommended_actions` — this is the diagnostics
pattern from [module-skills.md](module-skills.md), independently invented. Keep the
structure. **One change:** it currently names modules directly ("Consider
SuperPoint+LightGlue, DISK+LightGlue, LoFTR, or RoMa"), which is the anti-pattern
flagged in [module-skills.md](module-skills.md#limitationsmd--when-to-stop-tuning-and-switch)
— recommendations must name a capability the orchestrator can resolve against the
live registry, not a module that may be gone.

## What is missing

Your point that this should not be images alone is right, and the biggest gaps
are the cheapest ones.

### Metadata — no pixels needed

EXIF and file structure, essentially free, currently unused:

- **focal length, sensor, camera model** — sanity-check supplied calibration, or
  seed one when absent
- **timestamps → capture rate and ordering** — is this a video sequence, a
  deliberate capture, or an unordered bag? This determines whether *sequential*
  pairwise matching is even valid, which the current framework assumes everywhere
- **GPS** — coarse trajectory, outdoor/indoor prior
- **file naming and count** — `000001.jpg…000040.jpg` vs `DSC_0287.JPG` is a real
  signal about capture discipline
- **resolution and aspect consistency** — mixed resolutions break the loader's
  scale computation (the dataset overview (not written))

### Degeneracy detection — the two classic SfM killers

Both detectable from flow before anything runs, both currently undetected:

- **Pure rotation** — no parallax means no structure, and the pipeline will fail
  or silently produce garbage. The rotation machinery already exists in
  `optical_flow.py`; what is missing is the translation-vs-rotation ratio test.
- **Planar dominance** — a homography explains the flow as well as a fundamental
  matrix, so essential-matrix decomposition is ill-conditioned. The GRIC test for
  exactly this already exists in the current codebase, buried in
  `FeatureMatching.evaluate_models` (`baseclass.py:1455`). It belongs here, run on
  flow correspondences, before module selection rather than after.

### Texture and appearance

- **texture density and spatial distribution** — where features can be found at all
- **repetitiveness / self-similarity** — autocorrelation or patch self-matching.
  This is the facade case. Repetitive structure defeats descriptor matching in a
  way that no parameter recovers, and it is visible immediately.
- **textureless fraction** — sky, walls, water
- **per-frame sharpness** — Laplacian variance; identifies frames worth dropping

### Connectivity and dynamics

- **view-graph shape** — cheap global descriptors → pairwise similarity → is this
  a sequential chain, a closed loop, or an unordered set? Loop closure presence
  changes which reconstruction strategy is appropriate.
- **dynamic content** — flow residual after fitting a global motion model reveals
  moving objects, which corrupt tracks silently.

## Derived traits — the retrieval key

> **SUPERSEDED 2026-09-10. The `traits` group is not filled, retrieval is not
> keyed on it, and a test asserts neither analysis module writes it.** The design
> below is kept as the record of an approach that was tried and abandoned.
>
> **Why.** Deriving traits by thresholding needs cut points, and those were never
> written because the evidence does not support naming them. The one cut point
> that *was* published — the connectivity band in `plan/scene_to_pipeline.md`
> §3b — was refitted on sixteen full captures across seven statistics and two
> definitions of failure, separated nothing cleanly under any of them, and was
> withdrawn. Keying retrieval on thresholds would have meant keying it on the
> weakest thing in the corpus.
>
> **What replaced it.** `evidence/INDEX.md` is keyed on **observed capture kind**
> — what a reader looked at and graded through `SceneDescription` under a fixed
> rubric, from a closed vocabulary that file defines: setting, capture shape,
> subject, target surface, repetition, hazards. Those categories carry things no
> cue here measures at all, which is the deeper reason the swap was an
> improvement rather than a retreat: whether a reflection is coherent or diffuse,
> whether a flat region is wanted or backdrop, whether an empty region is clipped
> or merely dim. The cues below stay exactly as they are and remain the input to
> planning; what changed is that they are read as numbers by a planner rather
> than cut into labels by the orchestrator.

Cue values are the raw output. What retrieval needs is a small vocabulary of
**traits**, derived by thresholding, and this is the piece that closes the loop
you asked for:

```
scene_analysis/v1
  motion:      {overall_magnitude: 0.031, low_baseline_risk: 0.44, rotation_median_deg: 6.2}
  photometric: {illumination_change_p75: 0.09, exposure_shift_p75: 0.07}
  texture:     {repetitiveness: 0.71, textureless_fraction: 0.18}
  degeneracy:  {planar_dominance: 0.62, pure_rotation_risk: 0.03}
  metadata:    {ordered: true, capture: sequential, calibrated: true, n_images: 76}
  ────────────────────────────────────────────────────────────────────────
  traits: [outdoor, repetitive-texture, planar-dominant, narrow-baseline, sequential]
```

Those traits are exactly the `scene_traits` frontmatter field on a worked run in
[knowledge-system.md](knowledge-system.md#the-worked-run-corpus). So retrieval
becomes mechanical rather than intuitive:

```
sfm_open_scene(...)            → scene/v1  (+ SceneTriage auto-run)
sfm_run(SceneMotion, ...)      → scene_analysis/v1, traits derived
      │
      ├─ evidence/INDEX.md filtered by trait overlap   → "scenes like this were solved how?"
      ├─ plan/scene_to_pipeline.md                 → how those numbers read into a plan
      └─ sfm_list_modules(...) + SKILL.md          → candidate first pipeline
```

Traits are also what makes a lesson card's `Context` field checkable rather than
prose: a card recorded on `[outdoor, repetitive-texture, wide-baseline]` can be
matched against the current scene's traits automatically, so the agent knows
whether it transfers.

**Thresholds live in the global skills tier, not in the module.** What counts as "narrow
baseline" is a practitioner call, it will change as the module set grows, and it
is exactly the kind of subjective boundary that
[knowledge-system.md](knowledge-system.md#the-judgment-tier) exists to hold. The
module emits numbers; the trait vocabulary and its cut points are yours.

## Open question

> **RESOLVED 2026-09-10, by neither of the two answers below.**

The question was whether trait derivation belongs in the orchestrator (reading
thresholds from the global tier, so traits are consistent and cheap to re-derive)
or in the analysis modules (self-contained, but re-running analysis to change a
cut point). The orchestrator was the better of the two and neither was taken,
because the premise was wrong: **the thresholds it argues about placement for do
not exist and were never going to.**

What settled it was a measurement rather than a preference. The corpus's one
published cut point failed a refit on full captures, which is a result about cut
points on this evidence and not about where to evaluate them. Retrieval is keyed
on observed capture kind instead, and the cues on this page are consumed as
numbers by whoever is planning rather than cut into labels by anything.

**The plumbing the answer would have needed is live anyway** — the orchestrator
binds each run to its scene on the first step that touches one — so if a cut
point ever earns its place, the orchestrator remains where it should be
evaluated.
