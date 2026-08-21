# Worked Runs — Index

Tag table used for trait-based retrieval. One row per run; see
[../../docs/design/knowledge-system.md](../../docs/design/knowledge-system.md).

| Run | Dataset / Scene | Recon | Traits | Modules | Outcome |
| --- | --- | --- | --- | --- | --- |

*Empty. Populated as sessions are driven and distilled.*

---

## branch-comparison-2026-08 — detector/matcher branches to a sparse model

**This is the raw evidence table for the branch comparison. The lessons drawn
from it live in [`skills/scene_to_pipeline.md`](../scene_to_pipeline.md) §3b
and [`skills/judgment/swap_or_build.md`](../judgment/swap_or_build.md), stated
as scene properties rather than scene names — a plan for a new capture cannot
use a row from this table, only the reasoning built on it.** The names are here
so a claim can be traced back and re-run.

Fourteen captures, three branches, downstream held identical
(`FeatureTrackUnionFind` → `PoseEssentialToPnP` → `SparseTriangulation`), all
matchers at `pairing: exhaustive`, 12 images each, `sampling: head`.

`reg` = images registered of 12. `pts` = sparse point count. `prs` = image pairs
surviving verification, of 66 possible.

| capture | `overall_mag` | `repet` | SIFT+NN reg/pts/prs | SIFT+LightGlue | SuperPoint+LightGlue |
| --- | --- | --- | --- | --- | --- |
| relief | 0.032 | 0.665 | 12/12 · 3101 · 65 | 12/12 · 1538 · 66 | 12/12 · 1644 · 66 |
| scan33 | 0.067 | 0.660 | 12/12 · 8348 · 62 | 12/12 · 4904 · 60 | 12/12 · 1196 · 65 |
| facade | 0.075 | 0.808 | 12/12 · 6437 · 55 | 12/12 · 6869 · 62 | 12/12 · 3198 · 66 |
| scan9 | 0.096 | 0.732 | 12/12 · 2895 · 38 | 12/12 · 3873 · 49 | 12/12 · 1066 · 61 |
| delivery_area | 0.104 | 0.809 | 12/12 · 2749 · 43 | 12/12 · 2422 · 49 | 12/12 · 2798 · 62 |
| scan15 | 0.107 | 0.721 | 12/12 · 3302 · 40 | 12/12 · 3961 · 48 | 12/12 · 1264 · 54 |
| scan23 | 0.117 | 0.729 | 12/12 · 3862 · 47 | 12/12 · 4077 · 56 | 12/12 · 1593 · 64 |
| scan1 | 0.122 | 0.710 | 12/12 · 6900 · 64 | 12/12 · 4742 · 62 | 12/12 · 1807 · 65 |
| courtyard | 0.133 | 0.794 | 12/12 · 5415 · 64 | 12/12 · 6048 · 56 | 12/12 · 1323 · 66 |
| scan4 | 0.141 | 0.663 | 12/12 · 7395 · 64 | 12/12 · 4490 · 62 | 12/12 · 1822 · 66 |
| meadow | 0.166 | 0.621 | 3/12 · 109 · 26 | 3/12 · 115 · 42 | 11/12 · 1247 · 62 |
| playground | 0.222 | 0.652 | 6/12 · 916 · 33 | 8/12 · 2760 · 35 | 12/12 · 2582 · 40 |
| kicker | 0.292 | 0.712 | 9/12 · 1522 · 32 | 10/12 · 1504 · 37 | 11/12 · 1302 · 62 |
| electro | 0.309 | 0.748 | 7/12 · 763 · 27 | 10/12 · 1505 · 27 | 12/12 · 2639 · 44 |

**The four captures at the top of the `overall_mag` column are the four whose
view graph fragments under the classical branch**, with a clear gap below them.
That separation, and the fact that a learned branch restores registration on
all four, is the finding — not the individual rows.
