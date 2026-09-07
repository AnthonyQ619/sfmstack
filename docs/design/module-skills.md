---
name: module-skills
description: PROPOSAL (under discussion) — every containerized module ships curated knowledge alongside its metrics: how to read them, the gradient for improving them, and the limitations that mean the agent should switch modules rather than keep tuning. Curated from papers, source, and issue trackers.
status: proposal / under discussion — not implemented
---

# Module Skills

Part of [target-architecture.md](target-architecture.md) (decision 7).

A module that emits `avg_track_length: 4.21` has told the driving agent almost
nothing. Is 4.21 good? If not, which knob moves it, in which direction, and by how
much? And at what point is the honest answer "this method cannot do better on this
scene — use a different one"?

That knowledge exists — in papers, ablation tables, source comments, and issue
threads — and today it lives nowhere. Each module carries it as curated skill
files.

## What this replaces

Today the equivalent knowledge is a single hand-written corpus shared by all
modules: `agent_details/optimize_context/metric_context.txt` plus the long English
strings in `run_from_state`. It is global, unversioned, uncited, and — as
documented in the agent-layer overview (not written)
— substantially wrong. Moving it into per-module files makes it versionable with
the module, auditable against sources, and impossible to leave behind when a
module is added.

## Where this sits

Per-module skills are the **lower tier** of a two-tier knowledge system. Above
them sit cross-cutting workflow guides, a corpus of worked runs, and the
distillation loop that feeds both — all in
[knowledge-system.md](knowledge-system.md). Read that first for the whole shape;
this document covers only what ships with a module.

The split matters because a lot of real SfM knowledge is **not** module-local
("low inlier yield at the matcher means don't bother tuning the tracker"). That
kind of reasoning lives above the module — in `skills/plan/scene_to_pipeline.md` §3 and
the `skills/plan/` stage files — not in any one module's files. (A `skills/workflow/`
tier was designed to hold it, never written, and retired; see
[knowledge-system.md](knowledge-system.md#status--what-is-built-measured-2026-09-02-paths-pre-reorganisation).)

## Layout

```
modules/<module-name>/
  module.yaml
  Dockerfile
  adapter.py
  skills/
    SKILL.md          # identity · when to use · when not to      (always served)
    tuning.md         # principled gradient + observed episodes   (on demand)
    limitations.md    # failure signatures + observed switches    (on demand)
    artifact.md       # what this module's output means, how to inspect it
    sources.md        # citation backing every claim above
```

Skills live in the repo **and** are copied into the image. The orchestrator reads
them from disk, so `sfm_describe_module` never has to spawn a container.

Every file has two kinds of content, kept visually separate:

- **Principled** — distilled from the paper, its ablations, the source, and the
  issue tracker. Written once at curation time, revisited on version bumps.
- **Observed** — atomic lesson cards accreted from actual runs. Each carries the
  run it came from, the scene context, real numbers, and a confidence level.

Neither is sufficient alone. The paper tells you `contrast_threshold` trades
count against stability; only a run tells you that on DTU turntable sequences
doubling past 8192 keypoints buys 0.02 survival for +140% runtime.

## The three documents

### `SKILL.md` — identity and fit

Short. Returned with every `sfm_describe_module` call, so it must stay compact
enough to read alongside the manifest.

```markdown
---
module: FeatureTrackFromPairsUnionFind
module_version: 1.2.0
upstream: none (in-house)
curated_at: 2026-08-07
sources: 4
---

Builds multi-view tracks by union-find over pairwise correspondences. CPU-only,
no learned components, seconds not minutes.

**Use when** a pairwise matcher has already run and produced dense, well-distributed
correspondences — typically LightGlue or SuperGlue on a textured scene.

**Do not use when** the scene is low-texture or repetitive. This module cannot
create tracks the matcher never produced; it only merges what it is given.
See a module's `limitations.md`.

**Cheapest thing that usually works:** `min_track_len: 3` on turntable sequences,
`2` on wide-baseline sets.
```

### `tuning.md` — the gradient

The important one. **Keyed by observed metric state, not by parameter.** The agent
arrives holding metrics, not a hypothesis, so the index must match what it has.

```markdown
## `survival_ge_3` below 0.40

**Read it as:** most tracks are two-view only. Triangulation will be
under-constrained and sparse reconstruction will likely fail outright.

**Related upstream signal (advisory):** matcher `inlier_yield`. If it is also
below ~0.15 the deficit may originate in matching rather than here — see
[`skills/plan/scene_to_pipeline.md`](../../skills/plan/scene_to_pipeline.md) §3. This is a
pointer, not a gate: tune locally first if you prefer, and come back to it.

**Gradient, in order of expected effect:**

1. Upstream detector `max_keypoints` ×2 (e.g. 4096 → 8192).
   More candidates per frame is the largest single lever.
   *Expect:* `survival_ge_3` +0.10–0.15, runtime +60%.
2. Upstream matcher `RANSAC_threshold` 1.0 → 2.0 (hard cap 3.0).
   *Expect:* +0.05, and a rise in `fragmentation` — watch it.
3. `allow_pair_local_merge: true`, if the matcher is detector-free.
   No effect with a global-index detector; the observation registry already merges.

**Diminishing returns:** past `max_keypoints=16384` SIFT keypoint repeatability
falls and the added tracks are mostly noise [S2, §4.2 Table 3].

**Do not** raise `min_track_len` to fix this — it improves the *mean* by deleting
short tracks while making the underlying problem worse.

### Observed episodes

> **L-0042 · max_keypoints stops paying past 8192 on turntable sets**
> **Run:** `runs/2026-08-07-dtu-scan1` (illustrative) · **Seen in:** 3 runs · **Confidence:** medium
> **Context:** DTU scan1/9/10, 49 images, calibrated, SIFT → FLANN → this module.
> **Observed:** 4096→8192 moved `survival_ge_3` 0.31→0.44. 8192→16384 moved it
> 0.44→0.46 for +140% runtime.
> **Takeaway:** one doubling, then stop and look elsewhere. Untested on
> wide-baseline outdoor sets.

> **L-0057 · min_track_len=3 flattered the metric and broke reconstruction**
> **Run:** `runs/2026-08-11-eth-courtyard` (illustrative) · **Seen in:** 1 run · **Confidence:** low
> **Observed:** raising to 3 lifted `avg_track_length` 3.8→5.1 but dropped
> `track_count` 210k→48k, and sparse reconstruction then failed on too few points.
> **Takeaway:** on sparse-coverage scenes, judge by `track_count` alongside the mean.

## `fragmentation` above 0.35

...
```

Four properties that make this work:

- **Indexed by metric + threshold**, so a diagnostic can link straight to the
  right section (`see_also: tuning.md#survival_ge_3-below-040`).
- **Cross-module signals are advisory pointers**, never mandatory ordering. The
  agent decides when to go upstream; the skill only tells it where to look. The
  reasoning behind those pointers lives in `skills/plan/scene_to_pipeline.md` §3.
- **States expected magnitude and cost**, so the agent can decide whether a
  change is worth a run at all.
- **Principled guidance and observed episodes are visually separate.** The first
  is what the literature claims; the second is what actually happened here, with
  the scene context attached so the agent can judge whether it transfers.

### `limitations.md` — when to stop tuning and switch

```markdown
## Low-texture or repetitive structure

**Signature:** `survival_ge_3 < 0.25` after the upstream detector has already been
doubled once, and matcher `inlier_yield < 0.10`.

**Why no parameter helps:** union-find is a pure merge over correspondences the
matcher produced. On textureless surfaces the matcher produces few and they are
spatially clustered; merging them cannot manufacture multi-view support.

**Escape:** switch to a module that produces `tracks/v1` **without** consuming
`pairwise_matches/v1` — i.e. a direct tracker that reads `scene/v1` and finds its
own correspondences.
`sfm_find_alternatives(produces="tracks/v1", not_consuming="pairwise_matches/v1")`

**Expected trade:** direct trackers are 10–50× slower and need a GPU, but hold
tracks through texture-poor regions [S3, §5.1].

### Observed switches

> **L-0061 · Gave up on this module for ETH/facade after 4 tuning runs**
> **Run:** `runs/2026-08-11-eth-facade` (illustrative) · **Confidence:** medium
> **Trigger:** `survival_ge_3` plateaued at 0.22 across max_keypoints
> 4096/8192/16384 and RANSAC 1.0/2.0/3.0. Matcher `inlier_yield` never exceeded 0.09.
> **Switched to:** `FeatureTrackingVGGSfM` (direct tracker).
> **Result:** `survival_ge_3` 0.71, runtime 40s → 11min.
> **In hindsight:** the flat repetitive brick facade was visible in the input
> mosaic from the start. Four runs of tuning were avoidable — check
> `skills/plan/scene_to_pipeline.md` §3 for repetitive texture before sweeping.
```

**Escapes name a capability, never a module.** "Switch to LoFTR" goes stale the
moment the module set changes; "switch to something producing `tracks/v1` that
doesn't consume `pairwise_matches/v1`" is a query the orchestrator answers against
the live registry. This is what keeps a module's knowledge valid as the framework
grows — and it is the reason the payload types in
[target-architecture.md](target-architecture.md#payload-types-open-registry-versioned-names)
are worth having.

### `artifact.md` — reading this module's output

What the produced artifact actually contains, and how to look at it without
guessing. Short, but it is the difference between an agent that reads metrics and
one that can inspect a result.

```markdown
Produces `tracks/v1`.

`data/observations.npz`
  obs : [N, 4] float32, columns [track_id, frame_idx, x, y]
        one row per observation; a track with 5 views has 5 rows.
        Coordinates are in RESIZED image pixels — multiply by
        `scene.image_scale` to get original-resolution coordinates.
  track_count : scalar int64

**Sanity checks**
- `obs[:,0].max() + 1 == track_count` — off-by-one here means a producer bug.
- `obs[:,1]` should cover every frame index. Missing frames mean the matcher
  dropped a pair entirely; check its `pairwise_meta`.
- Median track length below 3 is not survivable downstream regardless of what
  the mean says.

**Inspect it**
`sfm_artifact(<id>)` for the summary; the npz is plain numpy, no custom loader.
```

### `sources.md` — auditability

Every non-obvious claim above carries a tag resolved here.

```markdown
| Tag | Source | Where | Claim it supports |
| --- | --- | --- | --- |
| S1 | Lowe 2004, *Distinctive Image Features* | §7.1 | contrast_threshold vs keypoint count |
| S2 | Ablation, upstream repo `benchmarks/repeatability.md` | Table 3 | repeatability falls past 16k keypoints |
| S3 | VGGSfM (Wang et al. 2024) | §5.1 | direct trackers on low-texture scenes |
| S4 | github.com/<org>/<repo>/issues/142 | thread | fine_tracking OOMs above 1024² on 24 GB |
```

This is what makes the corpus maintainable. When a module bumps its upstream
version, the sources table is the checklist for what to re-verify — as opposed to
today's situation, where nobody can tell which prompt claims were ever true.

## How the agent consumes this

```
sfm_run(...)  ─────────────►  job completes
                              metrics: {survival_ge_3: 0.31, ...}
                              diagnostics: [{code: short_tracks,
                                             severity: warn,
                                             see_also: "tuning.md#survival_ge_3-below-040"}]
        │
        ├─ sfm_module_skill(name, "tuning")     → the specific gradient
        ├─ re-run with adjusted params           → new artifact, both retained
        │
        └─ if tuning has bottomed out:
             sfm_module_skill(name, "limitations")
             sfm_find_alternatives(produces=..., not_consuming=...)
             → run a different module of the same capability
```

Progressive disclosure: `SKILL.md` always, the rest only when the agent has a
reason. Keeps context cost proportional to how stuck it is.

The `diagnostics[].see_also` link is what closes the loop tightly — the module
tells the agent not just that something is wrong but exactly which curated section
addresses it.

## Curation workflow

Writing these is an agent task, and a good one — reading a paper, its ablations,
the source, and the issue tracker to distill a page of actionable guidance is
squarely in scope for me.

```
sfm_scaffold_module(repo_url, ...)
    └─ writes module.yaml, Dockerfile, adapter.py, and skills/ STUBS
       with the source URLs pre-filled

curation pass (agent, per module)
    ├─ read the paper: ablation tables → the gradient, §limitations → escapes
    ├─ read the source: actual parameter ranges, hardcoded caps, guards
    ├─ read issues/discussions: real-world failure modes, OOM thresholds,
    │    version incompatibilities — often better than the paper for limitations
    └─ write tuning.md / limitations.md / sources.md, every claim tagged

sfm_smoke_test(name, scene)
    └─ validates the manifest, artifact schema, and that every metric named in
       tuning.md is actually emitted by the module
```

That last validation matters: a `tuning.md` section keyed on a metric the module
does not emit is dead text, and it is exactly the kind of drift that killed the
current corpus. Make it a build-time check.

Curation depth is **decided: both tiers, in this order** —

1. a shallow generic pass so every module has a usable `SKILL.md` and
   `artifact.md` and is discoverable from day one;
2. deep `tuning.md` / `limitations.md` / `sources.md` for the pilot modules;
3. the `Observed` sections in every module fill in continuously from real runs
   via the distillation loop in [knowledge-system.md](knowledge-system.md).

Only step 1 and 2 are authored up front. Step 3 is where most of the eventual
value accumulates, and it costs nothing extra because it is a by-product of
running the system.

### Quality bar

- Every quantitative claim in a **principled** section carries a source tag.
  No uncited numbers.
- Every **observed** card carries a run backlink, the scene context, and a
  confidence level. A number without the scene it came from is not transferable.
- Every `tuning.md` heading names a metric the module actually emits (enforced).
- Every `limitations.md` escape is a capability query, not a module name (enforced).
- Cross-module claims are **advisory pointers into the cross-cutting files**
  (`plan/scene_to_pipeline.md`, the `plan/` stage files, `judge/`, `health/`), never ordering rules. A module's skills never dictate what the agent must do first.
- Skills are versioned with `module_version`; bumping the upstream pin flags the
  principled sections for review. Observed cards survive version bumps but their
  confidence is downgraded.
