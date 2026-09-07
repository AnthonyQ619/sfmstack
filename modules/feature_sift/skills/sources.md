# Sources — FeatureDetectionSIFT

**Cite-only, like the evidence tier: this file exists to be referenced, not
browsed.** Every quantitative or mechanistic claim in the principled sections of
[tuning.md](tuning.md) and [limitations.md](limitations.md) resolves to a tag
here. Uncited numbers are not allowed in those sections. The provenance summary
rides `SKILL.md`; unsourced-band warnings sit in `tuning.md`; the re-check rule
is the one global rule in `SKILLS.md`.

| Tag | Source | Where | Claims it supports |
| --- | --- | --- | --- |
| S1 | Lowe, *Distinctive Image Features from Scale-Invariant Keypoints*, IJCV 60(2), 2004 | §3 (scale space, σ and prior smoothing), §4 (low-contrast rejection), §4.1 (principal-curvature / edge ratio, r=10), §3.2 (three scales per octave) | `n_octave_layers` default of 3; `contrast_threshold` as the low-contrast filter; `edge_threshold` being a curvature ratio whose sense is inverted; `sigma` assuming ~0.5 of existing blur |
| S2 | Arandjelović & Zisserman, *Three things everyone should know to improve object retrieval*, CVPR 2012 | §2 | RootSIFT: L1-normalise then square-root makes L2 distance behave as Hellinger; free and strictly better for L2 matching |
| S3 | OpenCV `SIFT_create` documentation and `sift.cpp` | `nfeatures` handling | The cap retains the strongest by contrast score rather than truncating detection, which is why `saturation` distinguishes cap-binding from filter-binding |
| S4 | Direct measurement, this repository | pilot run 2026-08-08, one controlled-rig capture | The single observed card in [tuning.md](tuning.md#observed) — 1024 vs 8192 on 8 images |
| S5 | The seventeen-capture sweep, 35 runs at 1.1.0 | scope: [evidence/CORPUS.txt](../../../skills/evidence/CORPUS.txt) | every measured band and episode in these skills |

## Deliberately absent

No claims here about SIFT's comparative accuracy against learned detectors. Those
comparisons are benchmark- and scene-dependent, and the useful form of that
knowledge is a routing decision, which belongs in
[limitations.md](limitations.md) as a capability escape rather than as a cited
number.
