---
module: DenseVGGT
module_version: 1.0.0
upstream: facebookresearch/vggt @ a288dd0, depth head
curated_at: 2026-08-11
sources: 2
---

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
