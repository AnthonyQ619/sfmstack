# Sources — FeatureDetectionSIFT

Every quantitative or mechanistic claim in the principled sections of
[tuning.md](tuning.md) and [limitations.md](limitations.md) resolves to a tag
here. Uncited numbers are not allowed in those sections.

| Tag | Source | Where | Claims it supports |
| --- | --- | --- | --- |
| S1 | Lowe, *Distinctive Image Features from Scale-Invariant Keypoints*, IJCV 60(2), 2004 | §3 (scale space, σ and prior smoothing), §4 (low-contrast rejection), §4.1 (principal-curvature / edge ratio, r=10), §3.2 (three scales per octave) | `n_octave_layers` default of 3; `contrast_threshold` as the low-contrast filter; `edge_threshold` being a curvature ratio whose sense is inverted; `sigma` assuming ~0.5 of existing blur |
| S2 | Arandjelović & Zisserman, *Three things everyone should know to improve object retrieval*, CVPR 2012 | §2 | RootSIFT: L1-normalise then square-root makes L2 distance behave as Hellinger; free and strictly better for L2 matching |
| S3 | OpenCV `SIFT_create` documentation and `sift.cpp` | `nfeatures` handling | The cap retains the strongest by contrast score rather than truncating detection, which is why `saturation` distinguishes cap-binding from filter-binding |
| S4 | Direct measurement, this repository | pilot run 2026-08-08, DTU scan1 | The single observed card in [tuning.md](tuning.md#observed) — 1024 vs 8192 on 8 images |

## Review triggers

Re-verify against these when any of the following changes:

- **The OpenCV pin moves.** S3 is behavioural, read off a specific
  implementation, not a specification. `nfeatures` selection and default
  thresholds have changed across major versions before.
- **`root_sift` default changes.** S2 assumes L2 matching downstream; a matcher
  using a different metric invalidates the recommendation.
- **A new observed card contradicts a principled claim.** The measurement wins.
  Amend the principled text and note the run that forced it.

## Deliberately absent

No claims here about SIFT's comparative accuracy against learned detectors. Those
comparisons are benchmark- and scene-dependent, and the useful form of that
knowledge is a routing decision, which belongs in
[limitations.md](limitations.md) as a capability escape rather than as a cited
number.
