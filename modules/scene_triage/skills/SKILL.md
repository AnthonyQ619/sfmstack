---
module: SceneTriage
module_version: 1.4.0
upstream: ported from scene_agent/breadth_agent/src/agent/core/utility/illumination_analysis.py
curated_at: 2026-08-14
sources: 4
---

## Where to go next

This file is the router. Everything below is orientation; the detail lives in the
other four documents, and this table is how to pick one without fetching all of
them.

| If | Fetch |
| --- | --- |
| a number is out of band, or a diagnostic told you to tune | **`tuning`** — 6 parameters documented, starting with `pairing` |
| you need to know whether this module can do the thing at all | **`limitations`** — e.g. "EXIF does not survive the scene artifact" |
| you are reading what it wrote | **`artifact`** — the layout of `scene_analysis/v1` |
| you want to know where a claim came from, or what rests on nothing | **`sources`** — includes an audited list of what is asserted without a source |

**First readings on this module's output:** `illumination_change`, `color_shift`, `exposure_shift`.

**Diagnostics it can raise:** `illumination_unstable`, `repetitive_texture`, `textureless`, `blurred_frames`, `unordered_capture`, `exif_unavailable`.

## What this module is for


CPU scene characterisation. Run it immediately after `SceneLoader`, before
choosing a detector.

**It is cheap enough not to think about.** No GPU, no model, a few seconds on a
40-image set. The artifact is content-addressed on the scene, so every pipeline
branching off that scene shares one analysis.

**It answers a different question from `SceneLoader`.** The loader reports
bookkeeping — how many images, what resolution, how far they were scaled. This
reports what the images are *like*: whether the same surface looks the same
twice, whether there is anything to detect, and whether the capture has an order.
Read the two together; neither is a scene description on its own.

**The metric that changes a decision is `repetitiveness`.** Everything else here
is a matter of degree that a parameter can chase. Self-similarity is not: a
facade whose windows are interchangeable makes a descriptor matcher produce
*confident wrong* correspondences, and no ratio-test threshold separates a right
one from a wrong one when the two look identical. High values mean choose a
different capability, not a different number. See
[limitations.md](limitations.md#repetitive-structure).

**The three photometric numbers are separate on purpose.** `illumination_change`,
`color_shift` and `exposure_shift` have different causes and different fixes —
the sun moved, the white balance drifted, the exposure clipped — and
`combined_change` is a convenience, not a diagnosis. Read the components before
acting on the total.

**Cheapest thing that usually works:**

```
defaults, plus source_dir when you have the original files
```

`source_dir` costs nothing and is the only way to get capture timing: `SceneLoader`
re-encodes images into the scene artifact and EXIF does not survive that. See
[limitations.md](limitations.md#exif-does-not-survive-the-scene-artifact).

**What it does not do:** derive traits. The `traits` group of `scene_analysis/v1`
is the orchestrator's job, from thresholds held in the global skills tier
(deliberately unwritten so far -- see `evidence/INDEX`), so that
revising what counts as "repetitive" does not mean re-running analysis. The
`healthy` bands here are this module's own advisory reading and are explicitly
provisional — see [limitations.md](limitations.md#the-bands-here-are-provisional).

**The other half of the scene** is `SceneMotion`, which fills the `motion` and
`degeneracy` groups from optical flow. Both produce `scene_analysis/v1` and both
fill different groups, so they compose without a merge step.

**Reading the output:** [artifact.md](artifact.md).

## Provenance

Exercised across **19 runs at version 1.4.0** in the seventeen-capture sweep of
two benchmark families (`evidence/CORPUS.txt`); no capture outside them.
Claim-by-claim citations: the `sources` skill — including the experiment
`repetitiveness` is still waiting on.
