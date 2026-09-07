# Campaign: detection-phase-2026-08 — the detection stage driven cold, five captures

**This is a raw evidence table. Cite it; do not plan from it.** The lessons live in
[`plan/detection.md`](../plan/detection.md) §3 and §5, in the two sparse detectors'
`tuning.md`, and in `SceneTriage`'s `textureless` diagnostic — stated as capture
properties, not as rows from this table. The names are here so a claim can be
traced back and re-run.

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

`terrace` is the only one outside the fourteen-capture corpus of
[branch-comparison-2026-08](branch-comparison-2026-08.md) and the only one the
connectivity question sent to the learned branch — the first out-of-sample
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
