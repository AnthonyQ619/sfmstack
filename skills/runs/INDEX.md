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

---

## detection-phase-2026-08 — the detection stage driven cold, five captures

**Raw evidence for the detection-stage findings.** The lessons live in
[`skills/families/detection.md`](../families/detection.md) §3 and §5, in the two
sparse detectors' `tuning.md`, and in `SceneTriage`'s `textureless` diagnostic —
stated as capture properties, not as rows from this table. The names are here so a
claim can be traced back and re-run.

Five captures, each driven from a standing start through step 4's first stage only:
brief → plan → choose the detector → run and tune it → stop before matching. 12
images each, `sampling: head`. 37 detector runs plus 2 `SceneMotion` re-reads.

| capture | `overall_mag` | detector chosen | settled at run | final params |
| --- | --- | --- | --- | --- |
| scan33 | 0.067 | SIFT | 2 | `max_keypoints: 8192` |
| facade | 0.075 | SIFT | 2 | `max_keypoints: 8192` |
| scan15 | 0.107 | SIFT | 4 | `max_keypoints: 16384`, `grayscale_clahe: true` |
| scan10 | 0.110 | SIFT | 2 | `max_keypoints: 8192` |
| terrace | 0.183 | SuperPoint | 2 | `max_keypoints: 4096` |

`terrace` is the only one outside the fourteen-capture corpus above and the only
one the connectivity question sent to the learned branch — the first out-of-sample
application of that rule.

**Saturation at the module default**, which is the reason "a cap is not a result"
became a rule: scan33 1.00, terrace 1.00 (SuperPoint), scan15 0.833, facade 0.583,
scan10 0.167. `cap_binding` fired on three of five; the two partial cases raised
nothing.

**The coverage denominator**, on the studio-rig capture that settled it. Dead-pixel
mask = grey ≥245 **and** local σ<3, which covers 0.60 of the median frame and
reproduces its `textureless_fraction` 0.5954. Of 768 grid cells (8×8 × 12 images),
333 are >80% burnt.

| detector | cells occupied | of the 333 burnt | keypoints on pure-255 σ<3 | reported `spatial_coverage` |
| --- | --- | --- | --- | --- |
| SIFT | 470 (435 of 435 recoverable) | 35 | 1.8% | 0.612 |
| SuperPoint | 762 | 327 | 11.0% | 0.992 |

Confirmed from the other side on scan15: raising SuperPoint's `detection_threshold`
10× dropped coverage 0.993 → 0.875 and removed 40% of the keypoints. And on facade,
where the dead region is *unwanted* rather than destroyed, banding raw `xy` against
the described regions: SIFT spends 73.1% of its budget on the facade, SuperPoint
61.3%, while SuperPoint reports the higher coverage (0.986 vs 0.957).

**`resize_long_edge`, after the downscale-only bug was fixed** (terrace 1024→1600
up, →640 down; facade the same). The loss orders monotonically by suppression
radius, which is the mechanism.

| module | `nms_radius` | baseline | upscale ~1.5× | downscale 0.63× |
| --- | --- | --- | --- | --- |
| SuperPoint · terrace | 4 | 2979.2 kp | 2575.0 · **−13.6%** | 1529.9 · −48.6% |
| ALIKED · terrace | 2 | 1994.4 kp | 1950.8 · **−2.2%** | 1567.2 · −21.4% |
| ALIKED · facade | 2 | 3187.3 kp | 3154.4 · **−1.0%** | 2277.9 · −28.5% |
| LoFTR · terrace | none | 5185.4 m/pair | 7948.4 · **+53.3%** | 2052.4 · −60.4% |

LoFTR's upscale also raised `min_matches_per_pair` 3976 → 7872, `inlier_ratio`
0.986 → 0.994 and `mean_match_score` 0.684 → 0.771 — every metric the right way.
