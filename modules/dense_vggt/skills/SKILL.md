---
module: DenseVGGT
module_version: 1.0.0
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

**The scale is the thing it cannot measure alone.** It has no correspondences.
Pass the optional `tracks/v1` input and the scale is estimated and reported;
without one it is the `depth_scale` parameter, whose default of 1.0 is correct
only when the poses came from VGGT too.

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

**Run zero times in any pipeline.** Every claim in these skills is from isolated
testing or carried from the predecessor codebase; nothing here has been exercised
end to end — and by the standing plan, dense modules run after the sparse
holdout. Claim-by-claim citations: the `sources` skill.
