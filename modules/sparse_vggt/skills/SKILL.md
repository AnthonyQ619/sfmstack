---
module: SparseVGGT
module_version: 1.1.0
upstream: facebookresearch/vggt @ a288dd0, depth head
curated_at: 2026-08-11
sources: 3
---

## Where to go next

This file is the router. Everything below is orientation; the detail lives in the
other four documents, and this table is how to pick one without fetching all of
them.

| If | Fetch |
| --- | --- |
| a number is out of band, or a diagnostic told you to tune | **`tuning`** — 5 parameters documented, starting with `min_track_len` |
| you need to know whether this module can do the thing at all | **`limitations`** — e.g. "It cannot fix poses" |
| you are reading what it wrote | **`artifact`** — the layout of `sparse_model/v1` |
| you want to know where a claim came from, or what rests on nothing | **`sources`** — includes an audited list of what is asserted without a source |

**First readings on this module's output:** `min_frame_points`, `two_view_fraction`, `p95_reprojection_error`.

**Diagnostics it can raise:** `no_points`, `depth_scale_inconsistent`, `mostly_single_view`.

## What this module is for


Sparse structure from VGGT's learned depth, unprojected with the **supplied**
poses. Same three inputs as `SparseTriangulation`, same output, so it drops into
the classical chain. GPU required.

**Use when** tracks are short or the scene is weakly textured. Depth is predicted,
not intersected, so a track seen in one view still gets a point — the capability
no geometric triangulator has.

**Prefer SparseTriangulation when** tracks are long and the scene is well
textured. Measured on twelve frames of a small, well-textured object on a plain
backdrop, with identical classical tracks and classical poses: this module 5358 points at 0.967 px, `SparseTriangulation` 6900 at
0.365 px. Ray intersection wins where rays are available.

**It uses the DEPTH head, not the point maps.** VGGT's point maps live in VGGT's
own world frame and scale — reading them is correct only when the poses also came
from VGGT, and silently wrong otherwise. Depth is per-view and frame-agnostic, so
unprojecting it with the supplied K and pose lands in the supplied frame by
construction. That is what makes "SIFT tracks + PnP poses + VGGT depth" work.

**`depth_scale_spread` is the metric to read first.** One scalar relates VGGT's
depth unit to the poses' unit only if the ratio is constant across the scene; the
spread says whether it is.

Measured, same tracks, two pose sources:

| poses from | `depth_scale` | `depth_scale_spread` | points | error |
|---|---:|---:|---:|---:|
| `PoseEssentialToPnP` | 2.1164 | 0.004 | 5358 | 0.967 px |
| `PoseVGGT` | **1.0044** | 0.004 | 4005 | 1.285 px |

The 1.0044 is the sanity check: fed its own model's poses, the scale estimator
recovers unity, because the two units already agree.

**Reading the output:** [artifact.md](artifact.md).
