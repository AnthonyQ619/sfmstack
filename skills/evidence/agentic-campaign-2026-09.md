# Campaign: agentic-campaign-2026-09 — the loop driven over every capture, planning only from context

**This is a raw evidence table. Cite it; do not plan from it.** The reasoning built on these rows lives in [`plan/`](../plan/scene_to_pipeline.md), [`health/ladder.md`](../health/ladder.md) and [`judge/swap_or_build.md`](../judge/swap_or_build.md), stated as capture properties rather than as scene names.

## Protocol

Steps 0–6 of the tool loop over every capture in [CORPUS.txt](CORPUS.txt), at **full frame count**, with every module and parameter chosen from retrievable context alone. Ground truth was computed once at the end by a separate script; no plan, parameter or branch choice saw it.

62 pipeline legs. Two working resolutions appear: the campaign opened at `max_edge: 1024`, inherited from the reference driver, and moved to the loader's own default of 1600 once that was noticed — the `px` column says which.

## The model shipped for each capture

Selected on registration first and the accounting rungs second, which is the rule in `health/ladder.md`. Where that rule and ground truth disagree the disagreement is recorded below rather than hidden by the selection.

| capture | pipeline | px | reg | points | GT rot° | GT trn° |
| --- | --- | --- | --- | --- | --- | --- |
| DTU/scan1 | `sift_nn` | 1024 | 1.00 | 19235 | 0.108 | 0.709 |
| DTU/scan10 | `sift_nn` | 1024 | 1.00 | 15707 | 0.116 | 0.759 |
| DTU/scan15 | `sift_nn` | 1024 | 1.00 | 15837 | 0.078 | 0.745 |
| DTU/scan23 | `sift_nn` | 1024 | 1.00 | 18411 | 0.118 | 0.807 |
| DTU/scan33 | `sift_nn` | 1024 | 1.00 | 19824 | 0.090 | 0.715 |
| DTU/scan4 | `sift_nn` | 1024 | 1.00 | 22744 | 0.092 | 0.725 |
| DTU/scan9 | `sift_nn` | 1024 | 1.00 | 16391 | 0.094 | 0.736 |
| ETH/courtyard | `sift_lg` | 1024 | 1.00 | 11768 | 0.072 | 0.122 |
| ETH/delivery_area | `sup@1600` | 1600 | 1.00 | 28335 | 0.048 | 0.085 |
| ETH/electro | `roma` | 1024 | 1.00 | 69803 | 0.079 | 0.084 |
| ETH/facade | `global_sift@1600` | 1600 | 1.00 | 32609 | 0.061 | 0.080 |
| ETH/kicker | `global_sift_clahe@1600` | 1600 | 1.00 | 6405 | 0.040 | 0.078 |
| ETH/meadow | `roma` | 1024 | 1.00 | 33854 | 0.136 | 0.083 |
| ETH/office | `sup@1024` | 1024 | 1.00 | 2382 | 0.090 | 0.448 |
| ETH/playground | `global_sift_clahe@1600` | 1600 | 1.00 | 9307 | 0.088 | 0.196 |
| ETH/relief | `mine@1600` | 1600 | 1.00 | 9606 | 3.068 | 0.962 |

**DTU rotations are corrected**; translations are not. See [the ground-truth section](#the-ground-truth-these-were-scored-against).

**Two captures where that selection rule and ground truth disagree, and the rule loses.** On a shallow-relief subject two models both registered the whole capture and the rule preferred the one truth ranks roughly sixty times worse. On a dim built interior the rule preferred a model with more points and better coverage that is worse against truth on both axes. In both cases the branch the rule declined was the one whose poses came from a global reconstructor, on which the yield rungs cannot be computed at all — so the tiebreak fell to coverage and point count alone. This is the hazard `health/ladder.md` now records.

## Every leg

| capture | leg | px | reg | points | coverage | yield_obs | error | GT rot° | GT trn° |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| DTU/scan1 | `sift_lg` | 1024 | 1.00 | 5273 | 0.594 | 0.816 | 0.395 | 0.094 | 0.775 |
| DTU/scan1 | `sift_nn` | 1024 | 1.00 | 19235 | 0.750 | 0.867 | 0.266 | 0.108 | 0.709 |
| DTU/scan10 | `sift_nn` | 1024 | 1.00 | 15707 | 0.609 | 0.873 | 0.266 | 0.116 | 0.759 |
| DTU/scan10 | `sift_lg` | 1024 | 0.90 | 1902 | 0.383 | 0.496 | 0.340 | 0.173 | 0.778 |
| DTU/scan15 | `sift_lg` | 1024 | 1.00 | 3984 | 0.609 | 0.785 | 0.446 | 0.092 | 0.750 |
| DTU/scan15 | `sift_nn` | 1024 | 1.00 | 15837 | 0.812 | 0.820 | 0.270 | 0.078 | 0.745 |
| DTU/scan23 | `sift_lg` | 1024 | 1.00 | 5283 | 0.625 | 0.812 | 0.387 | 0.131 | 0.787 |
| DTU/scan23 | `sift_nn` | 1024 | 1.00 | 18411 | 0.859 | 0.854 | 0.261 | 0.118 | 0.807 |
| DTU/scan33 | `sift_lg` | 1024 | 1.00 | 3031 | 0.422 | 0.767 | 0.180 | 0.202 | 0.606 |
| DTU/scan33 | `sift_nn` | 1024 | 1.00 | 19824 | 0.547 | 0.902 | 0.175 | 0.090 | 0.715 |
| DTU/scan4 | `sift_lg` | 1024 | 1.00 | 4826 | 0.562 | 0.824 | 0.395 | 0.101 | 0.788 |
| DTU/scan4 | `sift_nn` | 1024 | 1.00 | 22744 | 0.703 | 0.954 | 0.261 | 0.092 | 0.725 |
| DTU/scan9 | `sift_lg` | 1024 | 1.00 | 4247 | 0.578 | 0.748 | 0.445 | 0.112 | 0.708 |
| DTU/scan9 | `sift_nn` | 1024 | 1.00 | 16391 | 0.797 | 0.853 | 0.275 | 0.094 | 0.736 |
| ETH/courtyard | `sift_lg` | 1024 | 1.00 | 11768 | 0.867 | 0.817 | 0.196 | 0.072 | 0.122 |
| ETH/courtyard | `sift_nn` | 1024 | 1.00 | 11049 | 0.805 | 0.642 | 0.112 | 0.482 | 2.263 |
| ETH/delivery_area | `sift_lg` | 1024 | 1.00 | 5856 | 0.633 | 0.752 | 0.241 | 0.107 | 0.252 |
| ETH/delivery_area | `sift_nn` | 1024 | 1.00 | 7245 | 0.641 | 0.796 | 0.163 | 0.185 | 0.268 |
| ETH/delivery_area | `sup@1600` | 1600 | 1.00 | 28335 | 0.906 | 0.914 | 0.207 | 0.048 | 0.085 |
| ETH/delivery_area | `sup@1024` | 1024 | 1.00 | 15372 | 0.867 | 0.914 | 0.201 | 0.043 | 0.074 |
| ETH/delivery_area | `mine@1600` | 1600 | 1.00 | 11294 | 0.648 | 0.762 | 0.165 | 0.054 | 0.217 |
| ETH/electro | `roma` | 1024 | 1.00 | 69803 | 0.953 | 0.620 | 0.507 | 0.079 | 0.084 |
| ETH/electro | `sp_sg` | 1024 | 0.91 | 2367 | 0.703 | 0.365 | 0.559 | 0.142 | 0.353 |
| ETH/electro | `loftr` | 1024 | 0.91 | 43254 | 0.938 | 0.539 | 0.413 | 0.096 | 0.228 |
| ETH/electro | `sift_nn` | 1024 | 0.38 | 1684 | 0.562 | 0.216 | 0.218 | 0.139 | 0.172 |
| ETH/electro | `sift_lg` | 1024 | 0.04 | 79 | 0.211 | 0.009 | — | 0.203 | 0.249 |
| ETH/facade | `global_sift@1600` | 1600 | 1.00 | 32609 | 0.867 | unevaluable | 0.165 | 0.061 | 0.080 |
| ETH/facade | `sift_nn` | 1024 | 0.90 | 11985 | 0.891 | 0.462 | 0.123 | 0.159 | 0.170 |
| ETH/facade | `sift_lg` | 1024 | 0.88 | 7103 | 0.734 | 0.475 | 0.202 | 0.261 | 0.213 |
| ETH/facade | `mine@1600` | 1600 | 0.88 | 13061 | 0.719 | 0.535 | 0.105 | 0.085 | 0.093 |
| ETH/kicker | `global_sift_clahe@1600` | 1600 | 1.00 | 6405 | 0.531 | unevaluable | 0.274 | 0.040 | 0.078 |
| ETH/kicker | `mine@1600` | 1600 | 0.97 | 7652 | 0.547 | 0.591 | 0.175 | 0.065 | 0.091 |
| ETH/kicker | `sift_nn` | 1024 | 0.94 | 4184 | 0.500 | 0.599 | 0.164 | 0.815 | 1.199 |
| ETH/kicker | `sift_clahe_nn` | 1024 | 0.94 | 5215 | 0.547 | 0.649 | 0.187 | 0.452 | 0.554 |
| ETH/kicker | `sift_lg` | 1024 | 0.77 | 1852 | 0.500 | 0.495 | 0.274 | 0.105 | 0.237 |
| ETH/kicker | `sp_sg` | 1024 | 0.16 | 699 | 0.703 | 0.175 | 0.654 | 0.183 | 0.415 |
| ETH/meadow | `sp_sg` | 1024 | 1.00 | 1946 | 0.672 | 0.573 | 0.620 | 0.546 | 0.553 |
| ETH/meadow | `loftr` | 1024 | 1.00 | 15328 | 0.781 | 0.722 | 0.473 | 0.155 | 0.147 |
| ETH/meadow | `roma` | 1024 | 1.00 | 33854 | 0.875 | 0.793 | 0.549 | 0.136 | 0.083 |
| ETH/meadow | `sift_nn` | 1024 | 0.20 | 149 | 0.156 | 0.111 | 0.703 | 26.480 | 65.714 |
| ETH/meadow | `sift_lg` | 1024 | 0.13 | 72 | 0.117 | 0.032 | — | 43.435 | 77.806 |
| ETH/office | `sup@1600` | 1600 | 1.00 | 2324 | 0.594 | unevaluable | 0.974 | 0.098 | 0.455 |
| ETH/office | `sup@1024` | 1024 | 1.00 | 2382 | 0.625 | unevaluable | 0.757 | 0.090 | 0.448 |
| ETH/office | `global_sift_clahe@1600` | 1600 | 1.00 | 1715 | 0.375 | unevaluable | 0.268 | 0.073 | 0.265 |
| ETH/office | `sift_clahe_nn` | 1024 | 0.31 | 166 | 0.219 | 0.078 | 0.520 | 3.560 | 61.809 |
| ETH/office | `mine@1600` | 1600 | 0.31 | 1859 | 0.414 | 0.374 | 0.113 | 0.102 | 0.523 |
| ETH/office | `loftr` | 1024 | 0.15 | 1173 | 0.398 | 0.084 | 1.426 | 3.008 | 14.288 |
| ETH/office | `sift_clahe_lg` | 1024 | 0.12 | 316 | 0.547 | 0.117 | 0.424 | 0.188 | 0.389 |
| ETH/office | `sift_lg` | 1024 | 0.08 | 168 | 0.453 | 0.109 | — | 0.071 | 0.344 |
| ETH/office | `sp_sg` | 1024 | 0.08 | 267 | 0.547 | 0.091 | — | 0.169 | 0.399 |
| ETH/office | `sift_nn` | 1024 | 0.08 | 22 | 0.062 | 0.011 | — | 123.669 | 61.792 |
| ETH/office | `roma` | 1024 | 0.08 | 392 | 0.547 | 0.003 | — | 178.589 | 80.419 |
| ETH/playground | `global_sift_clahe@1600` | 1600 | 1.00 | 9307 | 0.680 | unevaluable | 0.249 | 0.088 | 0.196 |
| ETH/playground | `sift_lg` | 1024 | 0.50 | 3677 | 0.766 | 0.267 | 0.510 | 0.137 | 0.327 |
| ETH/playground | `sift_clahe_nn` | 1024 | 0.50 | 3781 | 0.797 | 0.337 | 0.203 | 0.112 | 0.161 |
| ETH/playground | `mine@1600` | 1600 | 0.47 | 3192 | 0.781 | 0.329 | 0.213 | 0.113 | 0.135 |
| ETH/playground | `sift_nn` | 1024 | 0.45 | 2211 | 0.750 | 0.224 | 0.242 | 0.079 | 0.232 |
| ETH/playground | `sp_sg` | 1024 | 0.16 | 1245 | 0.938 | 0.164 | 0.715 | 0.065 | 0.137 |
| ETH/relief | `global_sift@1600` | 1600 | 1.00 | 6016 | 0.609 | unevaluable | 0.185 | 0.052 | 0.067 |
| ETH/relief | `mine@1600` | 1600 | 1.00 | 9606 | 0.672 | 0.840 | 0.143 | 3.068 | 0.962 |
| ETH/relief | `sift_nn` | 1024 | 0.84 | 4262 | 0.641 | 0.814 | 0.150 | 0.059 | 0.091 |
| ETH/relief | `sift_lg` | 1024 | 0.71 | 1746 | 0.586 | 0.520 | 0.217 | 0.135 | 0.133 |

## The connectivity rule, refitted on full captures

The rule in `plan/scene_to_pipeline.md` §3b was fitted on fourteen captures at twelve frames with `sampling: head`, and states a clean gap in `overall_magnitude` between the captures that fragment and those that do not. These are the readings and the outcomes at full frame count, scored against the branch the rule is about — a classical detector and a ratio-test matcher.

| capture | imgs | reg on the cheap branch | `overall_magnitude` full | `high_motion_tail` full | `overall_magnitude` at the 12-frame head |
| --- | --- | --- | --- | --- | --- |
| ETH/office | — | 0.077 | 0.2290 | 0.2740 | 0.2690 |
| ETH/meadow | — | 0.200 | 0.2064 | 0.2652 | 0.2049 |
| ETH/electro | — | 0.378 | 0.1957 | 0.2229 | 0.3092 |
| ETH/playground | — | 0.447 | 0.2217 | 0.2568 | 0.2217 |
| ETH/relief | — | 0.839 | 0.1269 | 0.1531 | 0.0319 |
| ETH/facade | — | 0.900 | 0.1110 | 0.1535 | 0.0749 |
| ETH/kicker | — | 0.935 | 0.2864 | 0.3378 | 0.2916 |
| ETH/courtyard | — | 1.000 | 0.2451 | 0.2629 | 0.1327 |
| ETH/delivery_area | — | 1.000 | 0.1606 | 0.1787 | 0.1037 |
| DTU/scan1 | — | 1.000 | 0.0896 | 0.1153 | 0.1217 |
| DTU/scan10 | — | 1.000 | 0.1061 | 0.1276 | 0.1096 |
| DTU/scan15 | — | 1.000 | 0.0794 | 0.0975 | 0.1073 |
| DTU/scan23 | — | 1.000 | 0.0789 | 0.0967 | 0.1168 |
| DTU/scan33 | — | 1.000 | 0.0466 | 0.0615 | 0.0674 |
| DTU/scan4 | — | 1.000 | 0.1177 | 0.1352 | 0.1406 |
| DTU/scan9 | — | 1.000 | 0.0649 | 0.0828 | 0.0961 |

**Separation, as the probability that a fragmenting capture reads higher than a complete one.** No statistic tested produces a clean gap under either definition of fragmentation.

| statistic | any frame lost (7 vs 9) | reg < 0.8 (4 vs 12) |
| --- | --- | --- |
| `high_motion_tail` / √n | 0.921 | 0.896 |
| `overall_magnitude` / √n | 0.889 | 0.896 |
| `overall_magnitude` × 12/n | 0.905 | 0.896 |
| `high_motion_tail`, full capture | 0.905 | 0.875 |
| `overall_magnitude`, full capture | 0.857 | 0.833 |
| `pair_p90_across`, full capture | 0.873 | 0.771 |
| `overall_magnitude` at the 12-frame head | 0.730 | 0.938 |

## The twelve-frame head sample against the full capture

Every capture rebuilt at the exact fitting protocol — `max_images: 12, sampling: head` — and read on the same modules.

| capture | `texture_density` head / full | `overall_magnitude` head / full |
| --- | --- | --- |
| DTU/scan1 | 4952 / 3159 | 0.1217 / 0.0896 |
| DTU/scan10 | 2304 / 2421 | 0.1096 / 0.1061 |
| DTU/scan15 | 3576 / 3799 | 0.1073 / 0.0794 |
| DTU/scan23 | 3754 / 4379 | 0.1168 / 0.0789 |
| DTU/scan33 | 2724 / 3087 | 0.0674 / 0.0466 |
| DTU/scan4 | 5618 / 3927 | 0.1406 / 0.1177 |
| DTU/scan9 | 3204 / 3499 | 0.0961 / 0.0649 |
| ETH/courtyard | 4413 / 4284 | 0.1327 / 0.2451 |
| ETH/delivery_area | 1687 / 1641 | 0.1037 / 0.1606 |
| ETH/electro | 1624 / 1518 | 0.3092 / 0.1957 |
| ETH/facade | 4900 / 4737 | 0.0749 / 0.1110 |
| ETH/kicker | 2059 / 2159 | 0.2916 / 0.2864 |
| ETH/meadow | 3798 / 3804 | 0.2049 / 0.2064 |
| ETH/office | 475 / 1020 | 0.2690 / 0.2290 |
| ETH/playground | 4680 / 4178 | 0.2217 / 0.2217 |
| ETH/relief | 3372 / 2404 | 0.0319 / 0.1269 |

## Experiment E — is `registered_fraction` gated on surviving structure?

The pose stage's triangulation filters swept on healthy tracks (tighten) and on tracks that had produced full registration with no structure (relax).

| capture | min angle° | max reproj px | `registered_fraction` | `points_triangulated` |
| --- | --- | --- | --- | --- |
| ETH/courtyard (E1) | 2.0 | 4.0 | 1.000 | 10970 |
| ETH/courtyard (E1) | 8.0 | 4.0 | 0.947 | 5435 |
| ETH/courtyard (E1) | 15.0 | 4.0 | 0.947 | 2551 |
| ETH/courtyard (E1) | 25.0 | 4.0 | 0.921 | 1123 |
| ETH/courtyard (E1) | 30.0 | 4.0 | 0.632 | 744 |
| ETH/courtyard (E1) | 30.0 | 1.0 | 0.632 | 285 |
| ETH/courtyard (E1) | 30.0 | 0.5 | 0.579 | 147 |
| ETH/courtyard (E1) | 2.0 | 0.5 | 0.974 | 4938 |
| DTU/scan1 (E1) | 2.0 | 4.0 | 1.000 | 4885 |
| DTU/scan1 (E1) | 8.0 | 4.0 | 1.000 | 4772 |
| DTU/scan1 (E1) | 15.0 | 4.0 | 0.041 | 0 |
| DTU/scan1 (E1) | 25.0 | 4.0 | 0.041 | 0 |
| DTU/scan1 (E1) | 30.0 | 4.0 | 0.041 | 0 |
| DTU/scan1 (E1) | 30.0 | 1.0 | 0.041 | 0 |
| DTU/scan1 (E1) | 30.0 | 0.5 | 0.041 | 0 |
| DTU/scan1 (E1) | 2.0 | 0.5 | 1.000 | 1840 |
| ETH/playground (E2) | 2.0 | 4.0 | 0.158 | 266 |
| ETH/playground (E2) | 1.0 | 8.0 | 0.158 | 428 |
| ETH/playground (E2) | 0.5 | 12.0 | 0.158 | 493 |
| ETH/playground (E2) | 0.1 | 20.0 | 0.237 | 1178 |
| DTU/scan33 (E2) | 2.0 | 4.0 | 1.000 | 0 |
| DTU/scan33 (E2) | 1.0 | 8.0 | 1.000 | 65 |
| DTU/scan33 (E2) | 0.5 | 12.0 | 1.000 | 143 |
| DTU/scan33 (E2) | 0.1 | 20.0 | 1.000 | 302 |

## The n-view triangulator, against the pairwise one

Identical poses and tracks, matched track-length floor, only the triangulator swapped.

| triangulator | points | coverage | yield_obs | two-view share | GT rot° | GT trn° |
| --- | --- | --- | --- | --- | --- | --- |
| gtsam | 28335 | 0.906 | 0.914 | 0.510 | 0.048 | 0.085 |
| pairwise | 27854 | 0.906 | 0.892 | 0.518 | 0.047 | 0.082 |

## A learned detector on three captures a classical one solved

Every leg below ran at `saturation: 0.0`, so the cap is not what is being measured.

| capture | leg | reg | points | coverage | GT rot° | GT trn° |
| --- | --- | --- | --- | --- | --- | --- |
| ETH/kicker | `sp_global@1600` | 1.00 | 5037 | 0.672 | 0.092 | 0.123 |
| ETH/kicker | `sp_incr@1600` | 0.97 | 5619 | 0.766 | 0.076 | 0.120 |
| ETH/relief | `sp_global@1600` | 0.58 | 3761 | 0.883 | 0.101 | 0.142 |
| ETH/relief | `sp_incr@1600` | 0.58 | 6466 | 0.953 | 0.061 | 0.088 |
| ETH/office | `sp_global@1600` | 1.00 | 2326 | 0.609 | 0.095 | 0.415 |
| ETH/office | `sp_incr@1600` | 0.88 | 2558 | 0.719 | 0.092 | 0.380 |

<a id="the-ground-truth-these-were-scored-against"></a>

## The ground truth these were scored against

**DTU carries a fixed per-position rotation offset.** Seven reconstructions of seven different scenes, sharing only the arm's physical stops, agree with each other roughly three times more closely than any agrees with the shipped extrinsics; after the world-gauge alignment their per-position residuals agree across scans to a third of their own size. Fitting that correction on six scans and applying it to the held-out seventh takes the rotation error from 0.53–0.62° to 0.11–0.24°. The mechanism is named in `tools/gt_poses.py`: the shipped matrices are the rectified camera's and the working images are the cleaned/distorted set. **The correction is rotation-only**; the translation column is uncorrected.

**The other family needs no correction.** The same test over eighteen model pairs finds model-to-model disagreement comparable to or larger than the best model's disagreement with truth. A method that finds a large offset on one family and nothing on the other is not manufacturing the offset.

---

*Generated by `tools/phase_c_report.py`.*
