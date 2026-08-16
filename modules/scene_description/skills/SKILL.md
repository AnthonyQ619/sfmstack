---
module: SceneDescription
module_version: 0.3.0
upstream: none (in-house)
curated_at: 2026-08-15
sources: 1
---

Renders a contact sheet from the scene, then records what a viewer reports after
looking at it. **The third scene-analysis module, and the only one whose output
comes from outside the container.**

**It cannot describe anything by itself.** There is no model in this image. It
prepares something to look at and holds the answer; the looking is yours.

## The two-call flow

```
1.  sfm_run(SceneDescription, {scene})            -> contact sheet, described 0
                                                     raises `awaiting_description`
2.  sfm_artifact_image(<id>)                      -> the sheet, in your context
                                                     (no `name`: it is the only image)
    sfm_module_skill('SceneDescription', 'rubric')
3.  sfm_run(SceneDescription, {scene},
            params={'report': {...}})             -> the answers, described 1
```

**Both artifacts persist**, because the report is part of the recipe. The
un-described one is the record that the sheet was rendered; two different
readings of one scene sit side by side under `sfm_compare` rather than one
silently replacing the other.

The first call is not a failure and `awaiting_description` is `info`. It tells you
where the sheet is.

## What it is for

Not description in general. The rubric targets the **specific blind spots the two
measuring modules document in their own `limitations.md`** — and if a field could
be answered by reading a number those modules already produce, it does not belong
in the rubric.

| The blind spot | Field |
| --- | --- |
| textureless area — but is that region *wanted*? | `empty_regions` |
| repetition *between* images, not within one | `repetition` |
| moving people, vehicles, water | `dynamic_content` |
| glass, mirrors, polished metal | `material_hazards` |
| whether there IS one thing being reconstructed | `main_subject` |
| whether that thing even fits in the frames | `subject_completeness` |

Two of those — dynamic content and reflective material — are **measured nowhere
in this system at all**, and both are failures that hide: the correspondences are
real, the geometry is not, and every downstream metric reads healthy.

## What it is not

**`overall` is the field to act on.** A paragraph, and the first thing in the
artifact's narrative body. Read it against the `SceneTriage` and `SceneMotion`
metrics when choosing a pipeline. The enums are its machine-readable shadow —
they make a hazard countable and a diagnostic possible; they do not carry the
reasoning, and a reader who takes `material_hazards: 2` without `hazard_notes`
has a number and no idea what to do with it.

**Not a measurement.** The report goes into the `description` group of
`scene_analysis/v1`, which the schema marks as asserted. It can be wrong in ways a
measurement cannot — see [limitations.md](limitations.md#the-report-can-be-wrong).

**Not a validator of truth.** The module checks the report's *shape*: required
fields present and non-empty, enums inside their vocabulary, a note attached to
any flagged hazard. Nothing in the container can check whether the answers are
right.

**Not a substitute for either measuring module.** Run all three. `SceneTriage`
says what the images are like, `SceneMotion` says how the camera moved, this says
what is in them.

**Cheapest thing that usually works:**

```
defaults (12 images, uniform, 384px, 4 columns)
```

**Cost:** the smallest image in the repository — the plain runtime plus Pillow.
No OpenCV, no torch, no weights.

**Reading the output:** [artifact.md](artifact.md). The rubric itself:
[rubric.md](rubric.md), which is **version 3** — it carries a revision log saying
what each version learned. Two fields have been cut for failing the rule at the
top of it: `expected_difficulty` (a grade where a reason belongs) and
`capture_style` (already measured, by `rotation_median_deg`, `variability` and
`metadata.ordered`).
