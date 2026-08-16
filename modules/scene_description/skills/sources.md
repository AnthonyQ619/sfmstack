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
