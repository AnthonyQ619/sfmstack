# Campaign: band-calibration-2026-10 — are the healthy bands carrying information?

**This is a raw evidence table. Cite it; do not plan from it.** The rules it supports live
in [`health/bands.md`](../health/bands.md).

## Method

Every `healthy` band declared in any `module.yaml`, scored over **every reading** in every
batch on disk — up to 1080 readings for one band. Fire rate is per reading, not per
capture: an earlier pass took the last reading per module per capture and reported two
bands as dead that in fact fire on 1–2% of readings, which is a rare-event alarm behaving
correctly. Per-reading is the only rate that separates those.

Precision is measured on the twenty captures with reference poses: of the readings where
the band fired, the share belonging to a capture whose delivered model scored below
AUC@30 0.5. **The base rate of a poor delivery is 40%**, so 40% precision is what guessing
achieves.

## The ten bands that fire on most readings

| module · metric | kind | n | rate | precision |
|---|---|---|---|---|
| `SceneMotion.variability` | input | 102 | 96% | 40% |
| `SceneDescription.material_hazards` | input | 102 | 95% | 41% |
| `SceneDescription.subject_complete` | explains | 34 | 94% | **0%** |
| `SparseTriangulation.mean_track_length` | quality | 208 | 93% | 37% |
| `FeatureTrackUnionFind.avg_track_length` | quality | 304 | 91% | 43% |
| `SparseTriangulation.two_view_fraction` | quality | 208 | 84% | 39% |
| `FeatureTrackUnionFind.track_survival_5` | quality | 304 | 83% | 41% |
| `SceneTriage.illumination_change` | input | 103 | 79% | **31%** |
| `SceneTriage.textureless_fraction` | input | 103 | 78% | 38% |
| `SparseGlobalCOLMAP.min_frame_points` | structural | 125 | 71% | 50% |

**Every one is at or below the base rate except the last.** `illumination_change` at 31%
and `subject_complete` at 0% fire *more* often on good deliveries than on poor ones.

`subject_complete` is the clearest case in the set: 32 firings, **none** on a poor
delivery. The metric reports that a subject is cropped by the frame, which is a fact about
the capture and not a defect.

## Where the thresholds came from

They describe the ideal rather than the observed population:

| band | set at | p10 | median | p90 |
|---|---|---|---|---|
| `SparseTriangulation.mean_track_length` | ≥ 3.0 | 2.00 | 2.31 | **2.92** |
| `FeatureTrackUnionFind.avg_track_length` | ≥ 3.0 | 2.08 | 2.30 | **2.97** |
| `SparseTriangulation.two_view_fraction` | ≤ 0.6 | 0.56 | **0.75** | 1.00 |
| `FeatureTrackUnionFind.track_survival_5` | ≥ 0.1 | 0.00 | **0.01** | 0.14 |
| `SceneMotion.variability` | ≤ 0.035 | **0.052** | 0.10 | 0.19 |
| `SceneTriage.illumination_change` | ≤ 0.12 | 0.10 | **0.16** | 0.28 |
| `SceneTriage.textureless_fraction` | ≤ 0.35 | 0.28 | **0.50** | 0.75 |

Three sit outside the range the quantity reaches at all: no cloud in any batch reaches a
mean track length of 3.0 (p90 2.92) or an `avg_track_length` of 3.0 (p90 2.97), and no
capture is as evenly paced as `variability` ≤ 0.035 (p10 0.052).

## Recalibrated against the outcome

For each, the threshold that best separates poor from good deliveries on the twenty
reference captures, with its precision and the share of poor deliveries it catches:

| band | current → precision | best threshold | precision | recall |
|---|---|---|---|---|
| `mean_track_length` | 3.0 → 41% | **2.22** | **83%** | 71% |
| `two_view_fraction` | 0.6 → 44% | **0.843** | **83%** | 71% |
| `min_frame_points` | 50 → 47% | **10** | **75%** | 38% |
| `avg_track_length` | 3.0 → 42% | 2.08 | 100% | **25%** (2 firings) |
| `track_survival_5` | 0.1 → 39% | 0.001 | **50%** | 25% |

**`mean_track_length` and `two_view_fraction` are one signal.** At those thresholds they
fire on the same six captures — six of six — with correlation −0.90 between them. Keeping
both double-counts.

**`track_survival_5` cannot be rescued**: its best achievable precision is 50% against a
40% base rate, on four firings.

**`avg_track_length` reaches 100% on two firings**, which is too thin to act on — and this
module's own `tuning.md` carries a section headed *"avg_track_length is not a quality
metric"*, recording that track length rises as the pipeline degrades. A healthy band on it
contradicts its own documentation.

**These thresholds are fitted on the captures they are scored against.** They are
proposals, not results. The error they risk is the one that produced
`camera_spread_ratio`: fitted on thirteen models known to be wrong, deployed on models
that had passed every check, and reading rho **+0.051** against rotation error where the
incumbent `heldout_residual_mrad` reads **+0.680**.

## The bands that never fire

**Twenty-nine bands, over samples up to 281 readings, have never been violated.** Four
cannot be:

| band | why |
|---|---|
| `BundleAdjustmentGlobal.error_reduction` ≥ 0 | the quantity is a reduction and cannot be negative |
| `FeatureMatchRoMa.pairs_matched` ≥ 1 | observed minimum 6 |
| `PoseVGGT.registered_fraction` ≥ 1.0 | the module poses every image by design; 1.0 on all 87 readings |
| `PoseMapAnything.registered_fraction` ≥ 1.0 | the same, on all 86 |

The remaining twenty-five sit outside the observed range by a wide margin —
`FeatureDetectionSuperPoint.keypoints_min` ≥ 150 against an observed minimum of 346,
`FeatureMatchRoMa.matches_per_pair` ≥ 500 against 794,
`FeatureDetectionSuperPoint.spatial_coverage` ≥ 0.35 against 0.787.

## What a working band looks like

Twenty-two bands fire on **0.3% to 5.2% of readings**, which is the shape to aim at:

| band | n | rate |
|---|---|---|
| `FeatureTrackUnionFind.split_rate` | 304 | 0.3% |
| `PoseEssentialToPnP.local_ba_gain_px` | 211 | 0.9% |
| `FeatureDetectionSIFT.keypoints_per_image` | 161 | 1.9% |
| `SparseVerification.supported_second_size` | 1080 | 4.5% |
| `BundleAdjustmentGlobal.escaped_points` | 268 | 4.9% |

The last two are the ones this corpus has repeatedly acted on.

## What this campaign does not settle

**Forty-one bands are observed on fewer than eight readings** and no rate is stated for
them. Most sit on modules that barely run — `FeatureMatchLoFTR`,
`SparseTriangulationGTSAM`, `DenseFusion`.

Precision is measured against a *sparse* delivery metric on twenty captures. A band that
predicts dense failure, or a band whose job is to inform a parameter rather than to judge a
model, scores badly here and may still be doing work — `SceneMotion.large_rotation_risk`
fires at 17% precision and is read by a tuning section and two plan files.
