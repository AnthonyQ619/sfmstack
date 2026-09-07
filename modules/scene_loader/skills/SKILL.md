---
module: SceneLoader
module_version: 1.1.0
upstream: none (in-house)
curated_at: 2026-08-08
sources: 2
---

## Where to go next

This file is the router. Everything below is orientation; the detail lives in the
other four documents, and this table is how to pick one without fetching all of
them.

| If | Fetch |
| --- | --- |
| a number is out of band, or a diagnostic told you to tune | **`tuning`** — 4 parameters documented, starting with `image_dir` |
| you need to know whether this module can do the thing at all | **`limitations`** — e.g. "Mixed source resolutions" |
| you are reading what it wrote | **`artifact`** — the layout of `scene/v1` |
| you want to know where a claim came from, or what rests on nothing | **`sources`** — includes an audited list of what is asserted without a source |

**First readings on this module's output:** `n_images`, `mixed_resolution`, `downscale_factor`.

**Diagnostics it can raise:** `too_few_images`, `mixed_resolution`, `uncalibrated`, `low_working_resolution`, `heavy_downscale`.

## What this module is for


Reads a directory of images plus an optional calibration `.npz` into a
`scene/v1`. The root of every pipeline.

**Always runs first.** Everything downstream consumes `scene/v1`, and the
artifact is content-addressed by the resolved file list and resize policy — so
five parallel pipelines over the same scene decode once and share it.

**The choice that matters is `resize`.** With anything other than `none`, the
working images are written **into the artifact**, and downstream containers need
only the artifact mounted, not the dataset. With `resize: none` the artifact
references the originals and every downstream module inherits the dataset as a
runtime dependency. Prefer a resize policy unless you specifically need untouched
pixels.

**Uncalibrated is a legitimate state**, not an error. Omit `calibration_path` for
VGGT- and MapAnything-family paths, which estimate intrinsics themselves and do
better without a supplied K.

**Cheapest thing that usually works:**

```
resize: auto, max_edge: 1600, sampling: uniform
```

plus `max_images` while exploring — a spread subset of 8–20 images tells you what
the pipeline will do far faster than the full set, and `uniform` keeps it
representative of the whole trajectory.

**Reading the output:** [artifact.md](artifact.md). The per-image geometry
arrays are the part worth understanding; see
[limitations.md](limitations.md#mixed-source-resolutions) for why they are arrays
and not scalars.

## Provenance

Exercised across **20 runs at version 1.1.0** in the seventeen-capture sweep of
two benchmark families (`evidence/CORPUS.txt`); no capture outside them.
Claim-by-claim citations: the `sources` skill.
