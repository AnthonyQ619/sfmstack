# Campaign: dense-batch-2026-09 — raw frames to a dense cloud, every capture, planning only from context

**This is a raw evidence table. Cite it; do not plan from it.** The reasoning built on these rows lives in [`plan/dense.md`](../plan/dense.md), [`plan/optimization.md`](../plan/optimization.md), [`health/ladder.md`](../health/ladder.md) and the dense modules' own skills, stated as capture properties rather than as scene names.

## Protocol

The whole tool loop over the 22 captures of this dataset's standard evaluation set, one isolated agent per capture, every module and parameter chosen from retrievable context alone, at full frame count (49 views) and with the dense stage in scope. Ground truth entered once at the end, in a separate scoring script; no plan, parameter or branch choice saw any of it.

**Scoring.** The public protocol for this dataset: each cloud thinned to one point per 0.2 mm, accuracy as the mean distance from the cloud's points inside the observability mask to the reference scan, completeness as the mean distance from the reference points above the ground plane to the cloud, distances of 20 mm or more dropped from both means, overall their average. Same constants as the widely used Python port of the original script.

**Two bases, and they answer different questions.**

- **Published basis** — the cloud fitted to the reference geometry (trimmed 7-DoF ICP) before scoring. This is what published dense results on this dataset do for methods that estimate their own cameras (a similarity by Umeyama, in some work refined by ICP), so it is the only basis on which these numbers and published ones mean the same thing.
- **As placed** — the cloud left where the capture's own sparse model put it, with the frame fixed by a robust similarity from registered camera centres to the reference rig positions. Reference *geometry* plays no part in that fit. Every error in the placement is charged to the result.

All 22 agents delivered on the first attempt, in 74–172 minutes each, and all 22 chose the photometric MVS module.

## Per capture

| capture | role | sparse pipeline | dense | reg | sparse pts | thinnest view | error px | acc | comp | overall | acc placed | comp placed | overall placed | align mm |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| <a id="cap-dtu-scan1"></a>DTU/scan1 | control | `sift-clahe+nn/incr@1600` | `mvs@1600` | 49/49 | 78,076 | — | 0.321 | 0.233 | 0.380 | **0.306** | 0.362 | 0.534 | 0.448 | 0.65 |
| <a id="cap-dtu-scan4"></a>DTU/scan4 | control | `sift+nn/incr@1600` | `mvs@1600` | 49/49 | 72,173 | — | 0.321 | 0.280 | 0.566 | **0.423** | 0.648 | 1.072 | 0.860 | 0.90 |
| <a id="cap-dtu-scan9"></a>DTU/scan9 | control | `sift+nn/incr@1600` | `mvs@1600` | 49/49 | 31,173 | — | 0.356 | 0.339 | 0.451 | **0.395** | 0.499 | 0.624 | 0.562 | 0.63 |
| <a id="cap-dtu-scan10"></a>DTU/scan10 | control | `sift+nn/incr+gtsam@1600` | `mvs@1600` | 49/49 | 27,655 | — | 0.332 | 0.286 | 0.500 | **0.393** | 0.734 | 0.922 | 0.828 | 1.09 |
| <a id="cap-dtu-scan11"></a>DTU/scan11 | holdout | `sift+nn/incr@1600` | `mvs@1600` | 48/49 | 7,444 | — | 0.466 | 0.421 | 0.670 | **0.546** | 0.632 | 0.937 | 0.785 | 0.58 |
| <a id="cap-dtu-scan12"></a>DTU/scan12 | holdout | `sift+nn/incr@1600` | `mvs@1000` | 49/49 | 15,620 | — | 0.321 | 0.511 | 0.505 | **0.508** | 1.288 | 1.401 | 1.345 | 0.92 |
| <a id="cap-dtu-scan13"></a>DTU/scan13 | holdout | `sift-clahe+nn/incr@1600` | `mvs@1600` | 49/49 | 19,086 | — | 0.420 | 0.230 | 0.652 | **0.441** | 0.384 | 0.851 | 0.617 | 0.82 |
| <a id="cap-dtu-scan15"></a>DTU/scan15 | control | `sift+nn/incr@1600` | `mvs@1600` | 49/49 | 36,702 | — | 0.356 | 0.345 | 0.426 | **0.386** | 0.532 | 0.620 | 0.576 | 0.70 |
| <a id="cap-dtu-scan23"></a>DTU/scan23 | control | `sift+nn/incr@1600` | `mvs@1600` | 49/49 | 63,154 | — | 0.305 | 0.318 | 0.483 | **0.400** | 0.786 | 1.152 | 0.969 | 0.60 |
| <a id="cap-dtu-scan24"></a>DTU/scan24 | holdout | `sift+nn/incr@1600` | `mvs@1600` | 49/49 | 29,681 | — | 0.310 | 0.256 | 0.426 | **0.341** | 0.538 | 0.731 | 0.634 | 0.70 |
| <a id="cap-dtu-scan29"></a>DTU/scan29 | holdout | `sift+nn/incr@1600` | `mvs@1600` | 49/49 | 38,531 | — | 0.334 | 0.349 | 0.650 | **0.500** | 1.612 | 2.271 | 1.941 | 0.86 |
| <a id="cap-dtu-scan32"></a>DTU/scan32 | holdout | `sift+nn/incr@1600` | `mvs@1600` | 49/49 | 23,231 | — | 0.333 | 0.414 | 0.884 | **0.649** | 1.651 | 2.071 | 1.861 | 0.76 |
| <a id="cap-dtu-scan33"></a>DTU/scan33 | control | `sift+nn/incr@1600` | `mvs@1600` | 49/49 | 71,600 | — | 0.265 | 0.452 | 0.611 | **0.531** | 0.693 | 0.902 | 0.798 | 0.70 |
| <a id="cap-dtu-scan34"></a>DTU/scan34 | holdout | `sift+nn/incr@1600` | `mvs@1600` | 49/49 | 114,361 | — | 0.263 | 0.243 | 0.391 | **0.317** | 0.771 | 0.917 | 0.844 | 0.60 |
| <a id="cap-dtu-scan48"></a>DTU/scan48 | holdout | `sift-clahe+nn/global@1600` | `mvs@1600` | 49/49 | 2,876 | — | 0.345 | 0.373 | 2.928 | **1.651** | 0.939 | 3.513 | 2.226 | 1.67 |
| <a id="cap-dtu-scan49"></a>DTU/scan49 | holdout | `sift-clahe+nn/incr@1600` | `mvs@1600` | 49/49 | 27,567 | — | 0.274 | 0.596 | 0.525 | **0.561** | 0.877 | 0.716 | 0.796 | 0.81 |
| <a id="cap-dtu-scan62"></a>DTU/scan62 | holdout | `sift+nn/incr@1600` | `mvs@1600` | 49/49 | 9,777 | — | 0.320 | 0.369 | 1.085 | **0.727** | 0.776 | 1.396 | 1.086 | 0.56 |
| <a id="cap-dtu-scan75"></a>DTU/scan75 | holdout | `sift+nn/incr@1600` | `mvs@1600` | 49/49 | 27,793 | — | 0.299 | 1.053 | 0.438 | **0.745** | 1.760 | 1.085 | 1.423 | 1.08 |
| <a id="cap-dtu-scan77"></a>DTU/scan77 | holdout | `sift+lightglue/global@1600` | `mvs@1600` | 49/49 | 4,836 | — | 0.547 | 0.803 | 0.736 | **0.770** | 1.395 | 1.326 | 1.361 | 0.77 |
| <a id="cap-dtu-scan110"></a>DTU/scan110 | holdout | `sift-clahe+nn/incr@1600` | `mvs@1600` | 49/49 | 21,209 | — | 0.345 | 0.404 | 0.460 | **0.432** | 0.896 | 0.891 | 0.893 | 0.70 |
| <a id="cap-dtu-scan114"></a>DTU/scan114 | holdout | `sift+nn/incr@1600` | `mvs@1600` | 49/49 | 16,885 | — | 0.325 | 0.234 | 0.379 | **0.307** | 0.624 | 0.741 | 0.682 | 0.45 |
| <a id="cap-dtu-scan118"></a>DTU/scan118 | holdout | `sift+nn/incr@1600` | `mvs@1600` | 49/49 | 61,205 | — | 0.323 | 0.237 | 0.456 | **0.347** | 0.638 | 0.768 | 0.703 | 0.68 |
| **mean, all 22** | | | | | | | | **0.398** | **0.664** | **0.531** | 0.865 | 1.156 | 1.011 | |
| **mean, 15 holdout** | | | | | | | | **0.433** | **0.746** | **0.589** | 0.985 | 1.308 | 1.147 | |
| **mean, 7 controls** | | | | | | | | **0.322** | **0.488** | **0.405** | 0.608 | 0.832 | 0.720 | |

## What was derived from these rows

| Claim | Where it went | The rows behind it |
| --- | --- | --- |
| Coverage, not purity, is what the dense stage consumes | `plan/dense.md` §Planning the sparse stage | sparse points vs completeness **−0.64**; thinnest view **−0.59**; median points per view −0.50; at equal density, models keeping two-view structure −0.45 and models pruned to long tracks +0.47 |
| The error rung cannot see metric placement | `health/ladder.md`; `plan/optimization.md` §3 | reprojection error flat at 0.26–0.55 px across the batch and **+0.29** against metric error over 74 models; two captures at 0.33 px differing five-fold in metric error |
| Do not refine intrinsics on a calibrated capture | `plan/optimization.md`, `ba_global/tuning.md` | focal free: 0.44 → 0.33 px while the cloud moved 1.46 → 3.47 mm; focal + principal point → 13.36 mm at 0.28–0.33 px; recovered focal 0.877–1.055 of the shipped value |
| A hole is a photometric refusal, not an absence | `plan/dense.md`; `dense_mvs/limitations.md` | 94–99.5% of missed reference surface visible and unoccluded in ≥5 of the capture's own cameras, depth-buffer occlusion test |
| Blown highlights predict dense coverage | `scene_triage/module.yaml`, its `tuning.md`, `plan/dense.md` | `highlight_clipped_fraction` vs `depth_map_completeness` **−0.92**; texture density +0.59; textureless fraction −0.56; coverage spread 0.12–0.79 |
| `fusion_min_num_pixels` is the one filter that buys coverage | `dense_mvs/tuning.md` | five captures, five improvements: completeness 0.741→0.717, 1.396→1.238, 3.513→3.305, 2.071→1.928, 0.768→0.734; points ×1.61–1.85; mean aligned overall −0.032 mm |
| A predicted cloud is not a repair kit | `plan/dense.md`; `dense_vggt/limitations.md` | on one capture, aligned overall: MVS 0.307, predicted alone 1.164, union 1.217, hole-fill 1.585; 1.9 of 2.46 M predicted points >2 mm from any verified point |
| Selection is not where the dense result is won | `health/ladder.md` | delivered model metrically best in 6 of 22; best computable rule −2.4%; oracle −15.5% |
| MVS runtime under contention | `dense_mvs/SKILL.md` | under-predicted 1.5×–6×; 10 of 22 agents recorded it independently |

## The placement floor, and the six explanations that failed

Each capture's cloud sits 0.8–4.5 mm from where the reference expects it, and independently built models of one capture are displaced **identically** — median cosine +0.99 between displacement vectors, differing by 0.20 mm. That is the gap between the two bases above, and it is why pipelines should be compared on the published basis.

| tested | result |
| --- | --- |
| focal refinement | worse (1.46 → 3.47 mm) |
| focal + principal point | much worse (→ 13.36 mm) |
| BA convergence (18 of 22 hit the iteration cap) | converges by 414 iterations; geometry identical to 5 decimals |
| per-position camera-centre correction | halves the camera residual, moves the object 0.012 mm |
| the frozen per-position rotation correction | much worse for 20 of 22 (shift 1.43 → 4.56 mm) |
| distortion model | no radial trend in reprojection error (outer/inner 1.04) |

## Beside published results on this dataset

Millimetres, published basis, same evaluation set. Rows marked *given* were handed the dataset's calibration and reconstruct in the reference frame; rows marked *estimated* recovered their own cameras and were aligned before scoring, as this batch was. Published feed-forward rows sample a handful of frames per capture; every capture here used all 49 views.

| method | cameras | accuracy | completeness | overall |
| --- | --- | --- | --- | --- |
| Gipuma | given | 0.283 | 0.873 | 0.578 |
| COLMAP | given | 0.400 | 0.664 | 0.532 |
| MVSNet | given | 0.396 | 0.527 | 0.462 |
| GeoMVSNet | given | 0.331 | 0.259 | 0.295 |
| DUSt3R | estimated | 2.677 | 0.805 | 1.741 |
| MASt3R | estimated | 0.403 | 0.344 | 0.374 |
| VGGT | estimated | 0.389 | 0.374 | 0.382 |
| **this batch, all 22** | estimated | **0.398** | **0.664** | **0.531** |
| **this batch, 15 holdout** | estimated | **0.433** | **0.746** | **0.589** |

Accuracy sits with the published field; completeness is where the whole distance is. Five captures already beat the best published overall on this basis, and the batch mean is dragged by a tail of captures whose photometry denied the dense stage evidence.

## What this campaign could not measure

- **Which part of a hole is clipped and which is textureless.** The batch established that holes are photometric and that clipping predicts them; it never projected missed surface back into the images to attribute each hole. That is the first thing a follow-up needs.
- **Whether a surface reconstruction step would close the completeness gap.** Published dense numbers are often measured on a sampled surface rather than a fused point cloud; no module here produces one.
- **The fusion knob as a curve.** Five captures at one value, not a sweep — fusion is not separable from the stereo pass in the current module, so each arm costs a full MVS run.
- **Anything about captures that are not studio orbits of compact subjects.** Every row here is one rig.

## Harness note

One capture met a CUDA out-of-memory failure caused by three captures sharing a device, before the harness gated dense steps; its agent retried at lower resolution and delivered. The capture is flagged in the results and on both report pages, and the intervention is recorded in the experiment's `INTERVENTIONS.md`. Reports: `~/sfm_experiments/DTU_dense_exp/DTU_dense_results.html`.
