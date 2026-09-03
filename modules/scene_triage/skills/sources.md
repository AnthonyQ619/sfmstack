# Sources — SceneTriage

The photometric block is a port with its measurements and weights unchanged; the
texture and metadata blocks are new here. No paper backs any of it — these are
standard image statistics assembled for a purpose — so what needs citing is where
each number came from and what has actually been measured.

| Tag | Source | Where | Claims it supports |
| --- | --- | --- | --- |
| S1 | Predecessor source | `scene_agent/breadth_agent/src/agent/core/utility/illumination_analysis.py` | The LAB statistics, the Bhattacharyya histogram distances, the four weighted scores and their weights (0.35/0.25/0.15/0.25 for illumination, 0.65/0.35 for colour, 0.45/0.25/0.25/0.05 for exposure, 0.45/0.35/0.20 for the combination), the p75 dataset aggregation, and the LOW/MEDIUM/HIGH cut points at 0.12 and 0.28 |
| S2 | OpenCV documentation | `cv2.compareHist`, `HISTCMP_BHATTACHARYYA` | The distance is bounded to [0, 1] for normalised histograms, which is what makes the weighted sums comparable across scenes |
| S3 | Classical practice | Laplacian variance as a no-reference focus measure; Shi–Tomasi corner response | Both are standard and neither is novel; cited so it is clear no claim of a new measurement is being made |
| S4 | Direct measurement, this repository | 2026-08-14, ten scenes at 12 images each: ETH3D courtyard, delivery_area, electro, facade, kicker, meadow; DTU scan1, scan4, scan9, scan10 | `repetitiveness` ranges 0.62–0.81 with facade (0.808) and delivery_area (0.809) highest and meadow (0.621) lowest; `combined_change` ranges 0.055–0.116; `textureless_fraction` ranges 0.14–0.60; all ten reconstruct under a classical pipeline |

## What changed from the predecessor, and why

Recorded because the numbers are meant to stay comparable across the two systems
while the surrounding behaviour deliberately does not.

**Unchanged:** every measurement and every weight in [S1]. A score computed here
and one computed there are the same quantity.

**Changed:**

1. **Output is numeric.** The predecessor's entry point returned a formatted
   English paragraph with the thresholds interpolated into the text. Prose that
   ships inside a measurement cannot be revised without re-running the
   measurement; here the numbers go into the artifact and the prose lives in
   these files.
2. **Recommendations name capabilities, not modules.** `make_agent_interpretation`
   emitted "Consider SuperPoint+LightGlue, DISK+LightGlue, LoFTR, or RoMa"
   ([S1], line 415). Four hardcoded module names in a system whose registry is
   meant to change. The diagnostics here emit a query the orchestrator resolves
   against whatever is registered.
3. **LOW/MEDIUM/HIGH labels are gone.** They were a trait vocabulary living inside
   the measurement. Traits belong to the orchestrator, derived from thresholds in
   `skills/judgment/`, so that revising a boundary does not invalidate every
   analysis already computed.

## What is asserted without a source

Stated plainly so it is not mistaken for measurement:

- That `repetitiveness` predicts matcher failure. It is *motivated* — identical
  appearance defeats a local descriptor by construction — and the ranking over
  [S4] is plausible, but no run in this repository has yet paired a high reading
  with a measured `inlier_ratio` collapse. That pairing is the experiment this
  metric is waiting on.
- That `texture_floor = 5.0` is the right contrast floor. It was chosen so that
  sensor noise on a flat surface does not register as texture, and checked only
  for plausibility against [S4].

**Audited 2026-09-02, in addition to the above:**


- **Healthy bands with nothing behind them.** `texture_density`, `repetitiveness`, `textureless_fraction` declare a range and no diagnostic on this module reads them. A band with no diagnostic is a description of the captures measured so far, not a judgement on yours -- and a corpus maximum is the largest of N draws, so the next capture exceeding it is expected rather than anomalous.
- **Numeric tuning advice with no citation in this file.** `texture_floor`, `patch_size`, `source_dir` name specific values in their tuning prose. The reasoning behind them may be sound; the numbers are settings that worked here, not results anyone has published.
- **Scope of the measurements.** What is written here was exercised across 19 runs of this module in a seventeen-capture sweep of benchmark captures, at version 1.4.0. That is the whole evidence base: no capture outside those two benchmark families has been run through it.

## Review triggers

Re-read and re-check this file when any of these happens:

- **This module's version changes from 1.4.0.** These notes were written against it; a metric set or a published band can change with a version and the prose does not follow automatically.
- **A capture unlike the benchmark families appears.** Every band here was fitted on controlled-rig and field captures from two benchmark datasets. Per-frame appearance readings transfer to a larger capture; adjacent-motion readings and anything denominated in pairs do not.
- **A reading crosses one of `texture_density`, `repetitiveness`, `textureless_fraction` and nothing fires.** That is this file's known gap, not a defect in the capture -- but it is the signal that the band deserves either a diagnostic or a wider range.
