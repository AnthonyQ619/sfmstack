---
module: DenseVGGT
module_version: 1.1.0
upstream: facebookresearch/vggt @ a288dd0, depth head
curated_at: 2026-08-11
sources: 2
---

## Where to go next

This file is the router. Everything below is orientation; the detail lives in the
other four documents, and this table is how to pick one without fetching all of
them.

| If | Fetch |
| --- | --- |
| a number is out of band, or a diagnostic told you to tune | **`tuning`** — 5 parameters documented, starting with `stride` |
| you need to know whether this module can do the thing at all | **`limitations`** — e.g. "The scale it cannot measure alone" |
| you are reading what it wrote | **`artifact`** — the layout of `dense_model/v1` |
| you want to know where a claim came from, or what rests on nothing | **`sources`** — includes an audited list of what is asserted without a source |

**First readings on this module's output:** `point_count`, `views_contributing`, `mean_depth_confidence`.

**Diagnostics it can raise:** `no_points`, `scale_unverified`, `depth_scale_inconsistent`.

## What this module is for


Dense point cloud from VGGT's per-pixel depth, unprojected with the **supplied**
poses. GPU required.

**Use when** you want coverage fast. 8 DTU views at `stride: 2` give ~402k points
in 22 s, most of it model load — a second run against a warm server is 2 s.

**Prefer MVS when** you want precision. This is not MVS: no photometric
consistency check, no cross-view fusion. Every view contributes independently, so
a surface seen from four views appears four times.

**Hand it the refined model, as `sparse`.** It takes either a `poses/v1` or a
`sparse_model/v1` and wants exactly one. The sparse model is the better input and
usually the only possible one: every stage after the pose one — triangulation,
the global reconstructor, both bundle adjusters — produces `sparse_model/v1`, so
a refined model has no `poses/v1` to offer, and a pipeline built through the global
reconstructor never had one at all.

Until version 1.1.0 this module took `poses/v1` alone, which made it unreachable
from any refined model. An agent hit exactly that in a dense batch: its subject was
specular, the plan sent it here, and by then it held a bundle-adjusted model and
nothing this module would accept. That is fixed, and the fix is why `sparse` exists.

**The scale is the thing it cannot measure alone.** It has no correspondences of
its own. A `sparse` model settles it outright: its points are already triangulated
in the poses' frame, so each observation compares a known depth against the
predicted depth at the pixel that saw it, with nothing re-triangulated. A
`tracks/v1` input is the fallback. With neither, the scale is the `depth_scale`
parameter, whose default of 1.0 is correct only when the poses came from VGGT too.
`depth_scale_source` on the output says which of the three the run used.

Measured, 8 DTU views, classical poses:

| | `depth_scale` | `depth_scale_spread` | points |
|---|---:|---:|---:|
| without tracks | 1.0000 *(assumed)* | null | 401 968 |
| with tracks | **4.4460** *(measured)* | 0.0039 | 401 968 |

Same points, placed 4.4× further out. Getting this wrong **does not fail** — the
cloud is correctly shaped and wrongly sized, in front of cameras at the wrong
distance. The `scale_unverified` warning is the only signal, so read it.

**`min_confidence` is not a probability.** VGGT's confidence is unbounded above;
the mean on this run was **46.6**. A threshold set as if it were 0–1 rejects
nothing at 0.9 and everything at, say, 0.99 of the wrong scale. Read
`mean_depth_confidence` from a run first.

**Reading the output:** [artifact.md](artifact.md).

## Provenance

**Run as a comparison arm in one dense batch, and measured against reference
geometry for the first time** — see `limitations` and
`skills/evidence/dense-batch-2026-09.md`. No capture in that batch shipped this
module's cloud as its deliverable, so everything about its behaviour as a delivered
dense stage is still isolated testing or carried from the predecessor codebase.
Claim-by-claim citations: the `sources` skill.
