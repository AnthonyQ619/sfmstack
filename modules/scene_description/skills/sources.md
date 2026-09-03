# Sources — SceneDescription

There is nothing to cite. No paper, no upstream implementation, no port — the
module decodes images, pastes them into a grid, and validates a dictionary
against a list of required keys. None of that is a claim about the world.

What *is* a claim is the rubric: that these nine fields are the ones worth asking
for. That claim has one basis, and it is internal.

| Tag | Source | Where | Claims it supports |
| --- | --- | --- | --- |
| S1 | This repository's own limitations files | `modules/scene_triage/skills/limitations.md` ("What is not measured at all", "Textureless scenes", "Repetitive structure"); `modules/scene_motion/skills/limitations.md` ("What is not measured") | That dynamic content and reflective material are measured nowhere in this system; that `textureless_fraction` counts area and cannot say whether the region was wanted; that `repetitiveness` is a within-image measurement explicitly blind to between-image ambiguity; that `metadata.ordered` establishes only that an order exists |

## What is asserted without a source

Nearly all of it, and it is worth being blunt about which parts:

- **That these five blind spots are the ones that matter most.** They are the ones
  this system has written down. Whether they are the highest-value things a viewer
  could report is untested — that is what the planned experiments are for.
- **That a viewer can answer them reliably from a 12-cell contact sheet.** Never
  checked. A 384px cell may be too small for a mirror at the edge of frame.
- **That `main_subject` and `subject_completeness` change a decision.** They came
  out of the scan10 run, where the object is cropped in all twelve frames and v1
  had nowhere to record it. That it is a real observation is established; that a
  reader acts differently on it is reasoning.
- **That reporting a hazard changes the right decision.** The suggested actions on
  `dynamic_content` and `material_hazards` are reasoning from how SfM works, not
  from any measured case in this repository.

The honest summary: the *mechanism* is trivial and correct; the *rubric* is a
hypothesis at version 3, revised twice against three scenes. See the revision log in [rubric.md](rubric.md).

**Audited 2026-09-02, in addition to the above:**


- **Healthy bands with nothing behind them.** `dynamic_content`, `material_hazards`, `subject_complete` declare a range and no diagnostic on this module reads them. A band with no diagnostic is a description of the captures measured so far, not a judgement on yours -- and a corpus maximum is the largest of N draws, so the next capture exceeding it is expected rather than anomalous.
- **Numeric tuning advice with no citation in this file.** `n_images`, `thumbnail_max_side` name specific values in their tuning prose. The reasoning behind them may be sound; the numbers are settings that worked here, not results anyone has published.
- **Scope of the measurements.** What is written here was exercised across 48 runs of this module in a seventeen-capture sweep of benchmark captures, at version 0.7.0. That is the whole evidence base: no capture outside those two benchmark families has been run through it.

## Review triggers

Re-read and re-check this file when any of these happens:

- **This module's version changes from 0.7.0.** These notes were written against it; a metric set or a published band can change with a version and the prose does not follow automatically.
- **A capture unlike the benchmark families appears.** Every band here was fitted on controlled-rig and field captures from two benchmark datasets. Per-frame appearance readings transfer to a larger capture; adjacent-motion readings and anything denominated in pairs do not.
- **A reading crosses one of `dynamic_content`, `material_hazards`, `subject_complete` and nothing fires.** That is this file's known gap, not a defect in the capture -- but it is the signal that the band deserves either a diagnostic or a wider range.
