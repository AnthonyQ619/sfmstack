# Sources — SceneMotion

| Tag | Source | Where | Claims it supports |
| --- | --- | --- | --- |
| S1 | Predecessor source | `scene_agent/breadth_agent/src/agent/core/utility/optical_flow.py` | RAFT-large over consecutive pairs; normalisation by image diagonal; the p75/p90/IQR summary; the `low_motion_thresh = 0.005` default and the `high_motion_thresh = 0.08` one that has since been cut; the 20° large-rotation cut; the essential-matrix rotation estimate from flow correspondences |
| S2 | Teed & Deng, *RAFT: Recurrent All-Pairs Field Transforms for Optical Flow*, ECCV 2020 | torchvision `raft_large`, weights `C_T_SKHT_V2` | The flow model. Weights are baked into the image at build time and loaded with `strict=True`, which the build step asserts |
| S3 | Torr, *An assessment of information criteria for motion model selection*, CVPR 1997 | GRIC | The homography-vs-fundamental criterion, its penalty terms, and the constants `r = 4`, `λ₃ = 2`, `d = 2/3`, `k = 8/7` |
| S4 | Direct measurement, this repository | 2026-08-14, synthetic homographies at f = 800, principal point (320, 240) | `K⁻¹HK` orthogonality residual is 2–5 × 10⁻¹⁶ for `H = K R K⁻¹` at 2°, 8° and 20°; for a plane at unit depth with lateral baselines 0.02, 0.10 and 0.50 the residual is 0.028, 0.142 and 0.748 — very nearly linear in the baseline-to-depth ratio at ≈1.4 × |
| S5 | Direct measurement, this repository | 2026-08-14, ten scenes at 12 images each, stride 1: ETH3D courtyard, delivery_area, electro, facade, kicker, meadow; DTU scan1, scan4, scan9, scan10 | `low_baseline_risk` 0.00 on all ten; the since-cut `large_motion_risk` 0.82–1.00 on all ten; `overall_magnitude` 0.075–0.31; `variability` 0.029–0.208; `rotation_median_deg` 2.6–29.5; `planar_dominance` 0.00–0.18; `pure_rotation_risk` 0.00–0.09. All ten reconstruct under a classical SIFT pipeline (see `docs/import_lessons.md`) |

## What changed from the predecessor

**Unchanged:** the flow model, the normalisation and the summary statistics. A
motion score computed here and one computed there are the same quantity.

**One threshold removed rather than re-fitted.** `high_motion_thresh` and the
`large_motion_risk` fraction it fed were cut on 2026-08-14 after [S5] — see
[limitations.md](limitations.md#what-the-displacement-thresholds-did-and-did-not-show).
The remaining defaults are the predecessor's, untouched.

**Changed, and all three were flagged as defects in
`docs/design/scene-analysis.md` before the port:**

1. **The model no longer loads at import time.** [S1] built RAFT as a module-level
   global at line 17, so importing the file for any reason — a helper function, a
   docstring — allocated a GPU. It loads in `warmup()` here, the hook the warm
   server calls once per container.
2. **Nothing is formatted into English.** [S1] returned a paragraph with the
   thresholds interpolated into it. Numbers go into the artifact; prose lives in
   these files, where it can be revised without a re-run.
3. **The degeneracy tests are new.** Both were listed as missing. They come nearly
   free once flow exists — the expensive part is the flow field, and these are two
   model fits over correspondences sampled from it.

Also changed: [S1] read the whole calibration file and asserted stereo geometry
when `baseline_ext` was present. Intrinsics come from `scene/v1` here, per image,
scaled to the flow resolution.

## What is asserted without a source

- **That `rotation_only_tol = 0.15` is the right cut.** [S4] establishes what the
  residual *means* — a baseline-to-depth ratio of about 0.1 — but not that 0.1 is
  the ratio below which reconstruction fails. No scene measured here has been
  rotational, so the discriminator's specificity is demonstrated and its
  sensitivity is not.
- **That displacement is a weak proxy for matching difficulty.** [S5] shows the
  displacement thresholds do not discriminate across ten scenes that all
  reconstruct, which is evidence they are mis-set; the explanation offered in
  [limitations.md](limitations.md#what-the-displacement-thresholds-did-and-did-not-show)
  — that a rotation-invariant descriptor cares about view change rather than
  displacement — is reasoning, not measurement.

**Audited 2026-09-02, in addition to the above:**


- **Healthy bands with nothing behind them.** `variability`, `large_rotation_risk` declare a range and no diagnostic on this module reads them. A band with no diagnostic is a description of the captures measured so far, not a judgement on yours -- and a corpus maximum is the largest of N draws, so the next capture exceeding it is expected rather than anomalous.
- **Numeric tuning advice with no citation in this file.** `stride`, `max_pairs`, `max_side`, `low_motion_thresh`, `rotation_only_tol` name specific values in their tuning prose. The reasoning behind them may be sound; the numbers are settings that worked here, not results anyone has published.
- **Scope of the measurements.** What is written here was exercised across 66 runs of this module in a seventeen-capture sweep of benchmark captures, at version 1.3.0. That is the whole evidence base: no capture outside those two benchmark families has been run through it.

## Review triggers

Re-read and re-check this file when any of these happens:

- **This module's version changes from 1.3.0.** These notes were written against it; a metric set or a published band can change with a version and the prose does not follow automatically.
- **A capture unlike the benchmark families appears.** Every band here was fitted on controlled-rig and field captures from two benchmark datasets. Per-frame appearance readings transfer to a larger capture; adjacent-motion readings and anything denominated in pairs do not.
- **A reading crosses one of `variability`, `large_rotation_risk` and nothing fires.** That is this file's known gap, not a defect in the capture -- but it is the signal that the band deserves either a diagnostic or a wider range.
