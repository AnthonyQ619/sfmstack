# Campaign: alternate-legs-2026-09 — every module the reference pipeline never ran

**This is a raw evidence table. Cite it; do not plan from it.** The reasoning built on these rows lives in [`health/ladder.md`](../health/ladder.md), [`health/smells.md`](../health/smells.md), [`plan/pose.md`](../plan/pose.md) and [`judge/swap_or_build.md`](../judge/swap_or_build.md), stated as capture properties rather than as scene names.

## Protocol

Every leg is the reference pipeline of [reference-pipeline-2026-09](reference-pipeline-2026-09.md) with **one stage replaced**, run against the reference campaign's own artifact store. Every stage upstream of the swap is recipe-identical and served from the cache, so the two models differ in exactly one module and the difference is attributable to it.

That shape buys the thing the reference campaign could not have: **models of one capture that can legitimately be compared against ground truth.** True pose error is measured over the images a model registered, so it is comparable between two models only when they registered the same ones. Two conditions give that. A swap at or after the pose stage cannot add or drop a camera, so it registers exactly what the reference did. And several captures ended with three or four *different* pipelines each registering the capture in full — which is the stronger set, because unlike the first it contains comparisons the alternate wins.

Image drift was verified before the campaign started and every module image matched its source. 44 rows completed; 7 legs failed, and the failures are recorded below because a module refusing an input is a reading about the module.

## The rung validation — 17 comparisons between models of one capture, all fully registered

Two models that each registered 100% of a capture contain the same images, so ground-truth pose error is comparable between them whatever stage the swap was at. Every such pair is scored on whether the rung ranked it the way ground truth did.

| Rung | ranked correctly | ranked wrongly | unevaluable |
| --- | --- | --- | --- |
| coverage | 17 | 0 | 0 |
| yield_obs | 17 | 0 | 0 |
| yield_track | 16 | 1 | 0 |
| point_count | 16 | 1 | 0 |
| pose_agreement | 14 | 1 | 2 |
| pose_agreement_translation | 14 | 1 | 2 |
| error | 10 | 7 | 0 |
| conditioning | 9 | 8 | 0 |
| composition | 6 | 11 | 0 |
| registration | 0 | 0 | 17 |

Split by **what differs between the two models** — a bundle adjuster that deletes short tracks differs from its comparand by a point-retention rule and by nothing else, and the rungs that are selection effects behave completely differently on those pairs:

| Rung | differing by a point filter | differing by a change of branch |
| --- | --- | --- |
| coverage | 9 of 9 | 8 of 8 |
| yield_obs | 9 of 9 | 8 of 8 |
| yield_track | 9 of 9 | 7 of 8 |
| point_count | 9 of 9 | 7 of 8 |
| pose_agreement | 8 of 8 | 6 of 7 |
| pose_agreement_translation | 8 of 8 | 6 of 7 |
| error | 8 of 9 | 2 of 8 |
| conditioning | 1 of 9 | 8 of 8 |
| composition | 0 of 9 | 6 of 8 |
| registration | 0 of 0 | 0 of 0 |

**DTU/scan1** — every model below registers the whole capture.

| model | GT rot° | GT trn° | points | conditioning | composition | coverage | error | yield_obs | pose agreement |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| reference | 0.572 | 0.825 | 5273 | 13.37 | 0.364 | 0.594 | 0.395 | 0.816 | 0.175 |
| ba_local | 0.589 | 0.805 | 1922 | 23.33 | 1.000 | 0.500 | 0.591 | 0.434 | 0.234 |

**DTU/scan15** — every model below registers the whole capture.

| model | GT rot° | GT trn° | points | conditioning | composition | coverage | error | yield_obs | pose agreement |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| reference | 0.539 | 0.766 | 3984 | 12.29 | 0.293 | 0.609 | 0.446 | 0.785 | 0.209 |
| ba_local | 0.716 | 0.857 | 1169 | 22.72 | 1.000 | 0.484 | 0.689 | 0.348 | 0.339 |

**DTU/scan23** — every model below registers the whole capture.

| model | GT rot° | GT trn° | points | conditioning | composition | coverage | error | yield_obs | pose agreement |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| reference | 0.553 | 0.823 | 5283 | 12.66 | 0.334 | 0.625 | 0.387 | 0.812 | 0.415 |
| ba_local | 1.053 | 1.173 | 1765 | 21.62 | 1.000 | 0.500 | 0.528 | 0.411 | 0.499 |

**DTU/scan33** — every model below registers the whole capture.

| model | GT rot° | GT trn° | points | conditioning | composition | coverage | error | yield_obs | pose agreement |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| vggsfm_chunked | 0.565 | 0.731 | 2306 | 72.37 | 0.990 | 0.500 | 0.248 | 0.767 | — |
| reference | 0.608 | 0.695 | 3031 | 20.01 | 0.410 | 0.422 | 0.180 | 0.767 | 0.213 |
| ba_local | 1.500 | 0.834 | 1244 | 28.53 | 1.000 | 0.328 | 0.235 | 0.456 | 0.253 |

**DTU/scan4** — every model below registers the whole capture.

| model | GT rot° | GT trn° | points | conditioning | composition | coverage | error | yield_obs | pose agreement |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| reference | 0.622 | 0.856 | 4826 | 12.89 | 0.327 | 0.562 | 0.395 | 0.824 | 0.206 |
| ba_local | 0.661 | 0.777 | 1579 | 22.57 | 1.000 | 0.484 | 0.592 | 0.404 | 0.330 |

**DTU/scan9** — every model below registers the whole capture.

| model | GT rot° | GT trn° | points | conditioning | composition | coverage | error | yield_obs | pose agreement |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| reference | 0.552 | 0.746 | 4247 | 13.08 | 0.256 | 0.578 | 0.445 | 0.748 | 0.169 |
| ba_local | 0.719 | 0.664 | 1086 | 23.01 | 1.000 | 0.422 | 0.741 | 0.284 | 0.416 |

**ETH/courtyard** — every model below registers the whole capture.

| model | GT rot° | GT trn° | points | conditioning | composition | coverage | error | yield_obs | pose agreement |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| reference | 0.072 | 0.122 | 11768 | 8.79 | 0.414 | 0.867 | 0.196 | 0.817 | 0.181 |
| ba_local | 0.241 | 0.265 | 4875 | 16.46 | 1.000 | 0.805 | 0.326 | 0.487 | 0.237 |

**ETH/delivery_area** — every model below registers the whole capture.

| model | GT rot° | GT trn° | points | conditioning | composition | coverage | error | yield_obs | pose agreement |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| reference | 0.107 | 0.252 | 5856 | 9.75 | 0.479 | 0.633 | 0.241 | 0.752 | 0.187 |
| ba_local | 0.162 | 0.372 | 2804 | 15.17 | 1.000 | 0.516 | 0.280 | 0.487 | 0.213 |

**ETH/meadow** — every model below registers the whole capture.

| model | GT rot° | GT trn° | points | conditioning | composition | coverage | error | yield_obs | pose agreement |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| roma | 0.136 | 0.083 | 33854 | 27.80 | 0.100 | 0.875 | 0.549 | 0.793 | 0.532 |
| loftr | 0.155 | 0.147 | 15328 | 15.29 | 0.351 | 0.781 | 0.473 | 0.722 | 3.893 |
| superglue | 0.546 | 0.553 | 1946 | 10.89 | 0.222 | 0.672 | 0.620 | 0.573 | 2.365 |
| pose_vggt | 0.878 | 3.275 | 1079 | 5.34 | 0.029 | 0.297 | 0.388 | 0.489 | 7.987 |

**ETH/office** — every model below registers the whole capture.

| model | GT rot° | GT trn° | points | conditioning | composition | coverage | error | yield_obs | pose agreement |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| superglue | 0.103 | 0.501 | 2391 | 9.04 | 0.381 | 0.680 | 0.666 | 0.790 | 0.716 |
| pose_vggt | 2.166 | 6.661 | 745 | 8.65 | 0.219 | 0.281 | 0.527 | 0.573 | 1.872 |

## Every leg, against its reference row

`reg`, `pts`, `comp`, `cov`, `err`, `y_obs`, `pose` are the profile components; the arrow is reference → leg. `GT rot°` and `GT trn°` are median relative pose error against the dataset's own poses, over the images each model registered — **not comparable across differing registration**, which is most of this table.

| leg | capture | reg | pts | comp | cov | err | y_obs | pose_agr | GT rot° | GT trn° | imgs w/ GT | s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ba_local | DTU/scan1 | 1.00→1.00 | 5273→1922 | 0.364→1.000 | 0.594→0.500 | 0.395→0.591 | 0.816→0.434 | 0.175→0.234 | 0.572→0.589 | 0.825→0.805 | 49→49 | 6.9 |
| ba_local | DTU/scan10 | 0.90→0.90 | 1902→611 | 0.321→1.000 | 0.383→0.234 | 0.340→0.856 | 0.496→0.238 | 0.394→0.936 | 0.530→1.840 | 0.867→1.543 | 44→44 | 7.0 |
| ba_local | DTU/scan15 | 1.00→1.00 | 3984→1169 | 0.293→1.000 | 0.609→0.484 | 0.446→0.689 | 0.785→0.348 | 0.209→0.339 | 0.539→0.716 | 0.766→0.857 | 49→49 | 7.6 |
| ba_local | DTU/scan23 | 1.00→1.00 | 5283→1765 | 0.334→1.000 | 0.625→0.500 | 0.387→0.528 | 0.812→0.411 | 0.415→0.499 | 0.553→1.053 | 0.823→1.173 | 49→49 | 7.3 |
| ba_local | DTU/scan33 | 1.00→1.00 | 3031→1244 | 0.410→1.000 | 0.422→0.328 | 0.180→0.235 | 0.767→0.456 | 0.213→0.253 | 0.608→1.500 | 0.695→0.834 | 49→49 | 9.4 |
| ba_local | DTU/scan4 | 1.00→1.00 | 4826→1579 | 0.327→1.000 | 0.562→0.484 | 0.395→0.592 | 0.824→0.404 | 0.206→0.330 | 0.622→0.661 | 0.856→0.777 | 49→49 | 6.9 |
| ba_local | DTU/scan9 | 1.00→1.00 | 4247→1086 | 0.256→1.000 | 0.578→0.422 | 0.445→0.741 | 0.748→0.284 | 0.169→0.416 | 0.552→0.719 | 0.746→0.664 | 49→49 | 6.9 |
| ba_local | ETH/courtyard | 1.00→1.00 | 11768→4875 | 0.414→1.000 | 0.867→0.805 | 0.196→0.326 | 0.817→0.487 | 0.181→0.237 | 0.072→0.241 | 0.122→0.265 | 38→38 | 7.1 |
| ba_local | ETH/delivery_area | 1.00→1.00 | 5856→2804 | 0.479→1.000 | 0.633→0.516 | 0.241→0.280 | 0.752→0.487 | 0.187→0.213 | 0.107→0.162 | 0.252→0.372 | 44→44 | 3.6 |
| ba_local | ETH/facade | 0.88→0.88 | 7103→2774 | 0.391→1.000 | 0.734→0.625 | 0.202→0.248 | 0.475→0.258 | 0.069→0.078 | 0.261→2.094 | 0.213→2.732 | 44→44 | 6.6 |
| ba_local | ETH/kicker | 0.77→0.77 | 1852→701 | 0.379→1.000 | 0.500→0.383 | 0.274→0.309 | 0.495→0.256 | 0.408→0.531 | 0.105→1.050 | 0.237→1.227 | 24→24 | 2.8 |
| ba_local | ETH/playground | 0.50→0.50 | 3677→985 | 0.268→1.000 | 0.766→0.609 | 0.510→0.756 | 0.267→0.103 | 0.150→0.301 | 0.137→0.420 | 0.327→0.738 | 19→19 | 3.9 |
| ba_local | ETH/relief | 0.71→0.71 | 1746→760 | 0.435→1.000 | 0.586→0.531 | 0.217→0.222 | 0.520→0.327 | 0.373→0.304 | 0.135→0.132 | 0.133→0.137 | 22→22 | 3.4 |
| loftr | ETH/electro | 0.04→0.91 | 79→43254 | 0.000→0.527 | 0.211→0.938 | —→0.413 | 0.009→0.539 | 0.148→0.103 | 0.203→0.096 | 0.249→0.228 | 2→41 | 315.3 |
| loftr | ETH/meadow | 0.13→1.00 | 72→15328 | 0.000→0.351 | 0.117→0.781 | —→0.473 | 0.032→0.722 | 43.495→3.893 | 43.435→0.155 | 77.806→0.147 | 2→15 | 61.9 |
| loftr | ETH/office | 0.08→0.88 | 168→16769 | 0.000→0.354 | 0.453→0.797 | —→0.763 | 0.109→0.685 | 0.058→1.196 | 0.071→0.141 | 0.344→0.540 | 2→23 | 90.2 |
| loftr | ETH/playground | 0.50→0.16 | 3677→9348 | 0.268→0.266 | 0.766→0.969 | 0.510→0.460 | 0.267→0.099 | 0.150→0.519 | 0.137→0.069 | 0.327→0.062 | 19→6 | 132.7 |
| pose_vggt | DTU/scan10 | 0.90→1.00 | 1902→2493 | 0.321→0.330 | 0.383→0.438 | 0.340→0.343 | 0.496→0.641 | 0.394→0.341 | 0.530→0.838 | 0.867→1.071 | 44→49 | 20.5 |
| pose_vggt | ETH/electro | 0.04→1.00 | 79→2155 | 0.000→0.217 | 0.211→0.406 | —→0.305 | 0.009→0.293 | 0.148→0.322 | 0.203→0.276 | 0.249→0.720 | 2→45 | 39.0 |
| pose_vggt | ETH/kicker | 0.77→1.00 | 1852→1351 | 0.379→0.152 | 0.500→0.359 | 0.274→0.359 | 0.495→0.304 | 0.408→0.897 | 0.105→1.035 | 0.237→1.122 | 24→31 | 10.5 |
| pose_vggt | ETH/meadow | 0.13→1.00 | 72→1079 | 0.000→0.029 | 0.117→0.297 | —→0.388 | 0.032→0.489 | 43.495→7.987 | 43.435→0.878 | 77.806→3.275 | 2→15 | 4.8 |
| pose_vggt | ETH/office | 0.08→1.00 | 168→745 | 0.000→0.219 | 0.453→0.281 | —→0.527 | 0.109→0.573 | 0.058→1.872 | 0.071→2.166 | 0.344→6.661 | 2→26 | 9.0 |
| pose_vggt | ETH/playground | 0.50→1.00 | 3677→3409 | 0.268→0.070 | 0.766→0.461 | 0.510→0.704 | 0.267→0.217 | 0.150→0.646 | 0.137→2.097 | 0.327→6.339 | 19→38 | 15.5 |
| pose_vggt | ETH/relief | 0.71→1.00 | 1746→1286 | 0.435→0.143 | 0.586→0.344 | 0.217→0.176 | 0.520→0.275 | 0.373→0.972 | 0.135→10.584 | 0.133→11.280 | 22→31 | 12.0 |
| roma | ETH/meadow | 0.13→1.00 | 72→33854 | 0.000→0.100 | 0.117→0.875 | —→0.549 | 0.032→0.793 | 43.495→0.532 | 43.435→0.136 | 77.806→0.083 | 2→15 | 188.4 |
| roma | ETH/office | 0.08→0.35 | 168→14936 | 0.000→0.135 | 0.453→0.781 | —→0.514 | 0.109→0.273 | 0.058→0.654 | 0.071→0.161 | 0.344→1.244 | 2→9 | 330.4 |
| sparse_mapanything | DTU/scan10 | 0.90→0.90 | 1902→631 | 0.321→0.249 | 0.383→0.195 | 0.340→0.271 | 0.496→0.150 | 0.394→0.508 | 0.530→2.997 | 0.867→2.269 | 44→44 | 21.4 |
| sparse_mapanything | ETH/kicker | 0.77→0.77 | 1852→813 | 0.379→0.321 | 0.500→0.312 | 0.274→0.246 | 0.495→0.211 | 0.408→0.513 | 0.105→0.309 | 0.237→0.724 | 24→24 | 10.7 |
| sparse_mapanything | ETH/playground | 0.50→0.50 | 3677→1954 | 0.268→0.217 | 0.766→0.594 | 0.510→0.370 | 0.267→0.137 | 0.150→0.209 | 0.137→0.170 | 0.327→0.607 | 19→19 | 41.2 |
| sparse_mapanything | ETH/relief | 0.71→0.71 | 1746→943 | 0.435→0.408 | 0.586→0.461 | 0.217→0.177 | 0.520→0.275 | 0.373→0.365 | 0.135→0.146 | 0.133→0.148 | 22→22 | 11.1 |
| sparse_vggt | DTU/scan10 | 0.90→0.90 | 1902→716 | 0.321→0.306 | 0.383→0.195 | 0.340→0.295 | 0.496→0.181 | 0.394→0.561 | 0.530→2.194 | 0.867→1.724 | 44→44 | 18.9 |
| sparse_vggt | ETH/kicker | 0.77→0.77 | 1852→1162 | 0.379→0.356 | 0.500→0.398 | 0.274→0.204 | 0.495→0.307 | 0.408→0.520 | 0.105→0.434 | 0.237→0.858 | 24→24 | 11.3 |
| sparse_vggt | ETH/playground | 0.50→0.50 | 3677→2302 | 0.268→0.181 | 0.766→0.594 | 0.510→0.402 | 0.267→0.157 | 0.150→0.225 | 0.137→0.285 | 0.327→0.527 | 19→19 | 35.2 |
| sparse_vggt | ETH/relief | 0.71→0.71 | 1746→1057 | 0.435→0.384 | 0.586→0.484 | 0.217→0.179 | 0.520→0.290 | 0.373→0.374 | 0.135→0.096 | 0.133→0.115 | 22→22 | 11.5 |
| superglue | ETH/electro | 0.04→0.91 | 79→2367 | 0.000→0.492 | 0.211→0.703 | —→0.559 | 0.009→0.365 | 0.148→0.176 | 0.203→0.142 | 0.249→0.353 | 2→41 | 84.5 |
| superglue | ETH/meadow | 0.13→1.00 | 72→1946 | 0.000→0.222 | 0.117→0.672 | —→0.620 | 0.032→0.573 | 43.495→2.365 | 43.435→0.546 | 77.806→0.553 | 2→15 | 19.4 |
| superglue | ETH/office | 0.08→1.00 | 168→2391 | 0.000→0.381 | 0.453→0.680 | —→0.666 | 0.109→0.790 | 0.058→0.716 | 0.071→0.103 | 0.344→0.501 | 2→26 | 33.1 |
| tapir | ETH/playground | 0.50→0.16 | 3677→264 | 0.268→0.489 | 0.766→0.266 | 0.510→0.981 | 0.267→0.111 | 0.150→— | 0.137→1.183 | 0.327→2.821 | 19→6 | 21.7 |
| vggsfm | ETH/playground | 0.50→0.95 | 3677→1465 | 0.268→0.961 | 0.766→0.219 | 0.510→0.807 | 0.267→0.229 | 0.150→— | 0.137→1.838 | 0.327→7.509 | 19→36 | 55.4 |
| vggsfm_chunked | DTU/scan33 | 1.00→1.00 | 3031→2306 | 0.410→0.990 | 0.422→0.500 | 0.180→0.248 | 0.767→0.767 | 0.213→— | 0.608→0.565 | 0.695→0.731 | 49→49 | 132.1 |

## The detection leg, driven cold

`FeatureDetectionORB` had no readings anywhere in this corpus. Run on the captures [detection-phase-2026-08](detection-phase-2026-08.md) drove cold, at the module default, beside the reference campaign's SIFT row for the same capture and the same frames.

| capture | ORB kp/img | ORB kp_min | ORB sat | ORB coverage | suppression | SIFT kp/img | SIFT kp_min | SIFT sat | SIFT coverage |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| DTU/scan33 | 4096 | 4096 | 1.00 | 0.589 | 0.263 | 4096 | 4096 | 1.00 | 0.618 |
| ETH/facade | 4096 | 4096 | 1.00 | 0.809 | 0.293 | 3917 | 3205 | 0.54 | 0.928 |
| DTU/scan15 | 4079 | 3789 | 0.92 | 0.802 | 0.281 | 3931 | 1724 | 0.86 | 0.809 |
| DTU/scan10 | 4068 | 3724 | 0.80 | 0.669 | 0.353 | 3278 | 1151 | 0.29 | 0.660 |

## What refused to run, and what the refusal says

| leg | capture | failed at | the refusal |
| --- | --- | --- | --- |
| ba_local | ETH/electro | — | RuntimeError: BundleAdjustmentLocal: ExecutionError: module 'BundleAdjustmentLocal' failed: RuntimeError: ValueError: no point survived min_track_length=3. This module defaults to 3 rather than 2, because a two-view point inside a window contributes nothing… |
| ba_local | ETH/meadow | — | RuntimeError: BundleAdjustmentLocal: ExecutionError: module 'BundleAdjustmentLocal' failed: RuntimeError: ValueError: no point survived min_track_length=3. This module defaults to 3 rather than 2, because a two-view point inside a window contributes nothing… |
| ba_local | ETH/office | — | RuntimeError: BundleAdjustmentLocal: ExecutionError: module 'BundleAdjustmentLocal' failed: RuntimeError: ValueError: no point survived min_track_length=3. This module defaults to 3 rather than 2, because a two-view point inside a window contributes nothing… |
| tapir | DTU/scan33 | SparseTriangulation | RuntimeError: SparseTriangulation: ExecutionError: module 'SparseTriangulation' failed: RuntimeError: ValueError: no track survived triangulation: 465 had at least 2 registered observations, 0 landed behind a camera, and the rest failed the 2.0 degree angle… |
| tapir | ETH/courtyard | — | RuntimeError: FeatureTrackTapir: ExecutionError: module 'FeatureTrackTapir' failed: RuntimeError: ValueError: FeatureTrackTapir needs every image at the same resolution -- it stacks them into one video tensor. Re-run SceneLoader with a fixed resize. |
| vggsfm | DTU/scan33 | FeatureTrackVGGSfM | RuntimeError: FeatureTrackVGGSfM: ExecutionError: module 'FeatureTrackVGGSfM' failed: RuntimeError: OutOfMemoryError: CUDA out of memory. Tried to allocate 11.50 GiB. GPU 0 has a total capacity of 44.42 GiB of which 9.21 GiB is free. Including non-PyTorch m… |
| vggsfm | ETH/courtyard | — | RuntimeError: FeatureTrackVGGSfM: ExecutionError: module 'FeatureTrackVGGSfM' failed: RuntimeError: ValueError: FeatureTrackVGGSfM needs every image at the same resolution -- it stacks them into one tensor and tracks across the stack. This scene has mixed r… |

## The images that produced these rows

A version tag does not pin behaviour. These digests do.

| module | image | digest |
| --- | --- | --- |
| BundleAdjustmentGlobal | `sfmstack/ba-global:1.1.0` | `sha256:3f258903cd71` |
| BundleAdjustmentLocal | `sfmstack/ba-local:1.1.0` | `sha256:55b26011c36f` |
| FeatureDetectionORB | `sfmstack/feature-orb:1.0.0` | `sha256:58bb2278585f` |
| FeatureDetectionSIFT | `sfmstack/feature-sift:1.1.0` | `sha256:df4026a5a31d` |
| FeatureDetectionSuperPoint | `sfmstack/feature-superpoint:1.1.0` | `sha256:9829b3905801` |
| FeatureMatchLightGlue | `sfmstack/match-lightglue:1.6.0` | `sha256:98b783e16686` |
| FeatureMatchLoFTR | `sfmstack/match-loftr:1.7.0` | `sha256:262f0ef24015` |
| FeatureMatchRoMa | `sfmstack/match-roma:1.6.0` | `sha256:1406e088ab0b` |
| FeatureMatchSuperGlue | `sfmstack/match-superglue:1.6.0` | `sha256:829fd55bc3a8` |
| FeatureTrackTapir | `sfmstack/track-tapir:1.5.0` | `sha256:1647f41bac1a` |
| FeatureTrackUnionFind | `sfmstack/track-union-find:1.4.0` | `sha256:db9cc0e8fb2e` |
| FeatureTrackVGGSfM | `sfmstack/track-vggsfm:1.5.0` | `sha256:734ba9fa662b` |
| PoseEssentialToPnP | `sfmstack/pose-incremental:1.2.0` | `sha256:b71414a82268` |
| PoseVGGT | `sfmstack/pose-vggt:1.0.0` | `sha256:58e4b6f24119` |
| SceneLoader | `sfmstack/scene-loader:1.1.0` | `sha256:a7bf9fffc583` |
| SparseMapAnything | `sfmstack/sparse-mapanything:1.1.0` | `sha256:3e4ec57a5037` |
| SparseTriangulation | `sfmstack/sparse-triangulation:1.1.0` | `sha256:921fc13bb2fe` |
| SparseVGGT | `sfmstack/sparse-vggt:1.1.0` | `sha256:3de5a8800dc8` |

---

*Generated by `tools/phase_b_report.py` from `/home/anthonyq/sfm-phase-a-store`. The driver is `tools/phase_b.py`, which carries the leg definitions and the reason each capture was chosen for each leg.*
