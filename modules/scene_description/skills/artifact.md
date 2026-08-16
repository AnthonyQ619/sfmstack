# Artifact — SceneDescription

Produces `scene_analysis/v1`, filling the `description` group. `SceneTriage` fills
`metadata`, `photometric` and `texture`; `SceneMotion` fills `motion` and
`degeneracy`. Three producers, one type, disjoint groups, no merge step.

---

## Files, arrays and sidecars

```
description.npz                       (only on a described run)
  overall         ()  str   DECLARED -- one paragraph, the field to act on
  environment     ()  str   DECLARED
  main_subject    ()  str   EXTRA -- the object, or the word `none`
  subject_completeness () str EXTRA, when there is a main subject
  subject         ()  str   EXTRA
  empty_regions   ()  str   EXTRA
  repetition      ()  str   EXTRA
  dynamic_content ()  str   EXTRA
  material_hazards()  str   EXTRA
  hazard_notes    ()  str   EXTRA, when present
  notes           ()  str   EXTRA, when present
  browsed         (B,) str  EXTRA -- the filenames actually shown

data/browse/contact_sheet.jpg         sidecar, both runs -- the ONLY image written
```

**Only two arrays are declared in the type**, and the rest ride as extras
recorded in the manifest's `extras` block. That is not laziness: the rubric is
expected to be revised, and a schema that churned with it would drag every
producer of `scene_analysis/v1` along. Promote a field into the type once it has
stopped moving.

**`browsed` is the provenance.** Without it the report is a claim about a set
nobody can reconstruct — the browse set is a *sample* of the scene, and which
sample matters.

---

## Reading it

The narrative body is the point here, more than on any other module, and
**`overall` leads it** — before the structured answers, because it is the field a
reader acts on. `sfm_run` returns the body as `notes`; `sfm_artifact(id,
full=True)` returns the whole `artifact.md`.

The metrics are a machine-readable shadow and are not a substitute.
`dynamic_content: 2` says something is moving; `hazard_notes` says what and where;
`overall` says what to do about it. In the loop, `overall` is what gets weighed
against the `SceneTriage` and `SceneMotion` metrics when a pipeline is chosen.

| Metric | Values |
| --- | --- |
| `described` | 0 browse-set only, 1 report present |
| `browse_images` | cells in the sheet |
| `dynamic_content` | 0 none, 1 minor, 2 substantial |
| `material_hazards` | 0 none, 1 minor, 2 substantial |
| `between_image_repetition` | 0 no, 1 yes (`repetition` was `between_images` or `both`) |
| `has_main_subject` | 0 a place or collection, 1 one identifiable object |
| `subject_complete` | 1 fully in view, 0 cropped or occluded |

All report `null` on an undescribed run — not zero. Zero is a claim.
`subject_complete` is null on a second ground too: when `has_main_subject` is 0
there is nothing whose completeness could be asserted, and that is different from
asserting it is incomplete.

---

## The contact sheet

One labelled grid, `[k] filename` under each cell. **The index is the referring
unit**: a report that says "mirrored shopfront in [3] and [4]" is checkable
against the sheet, and one that says "some reflections" is not. The rubric asks
for indices for this reason.

**Reach it with `sfm_artifact_image(<id>)`** — no `name` needed, because the sheet
is the only image the artifact carries. That is why per-frame thumbnails are not
written: for a question about one frame the scene artifact already holds every
working image at full resolution,

```
sfm_artifact_image(<scene_id>, "images/000003.png")
```

which beats a 384px copy, and keeping thirteen images here would have made
`sfm_artifact_image(<id>)` ambiguous in the one case it exists to make
frictionless.

---

## Reading it beside the rest of the scene

```
SceneLoader       how much image there is
SceneTriage       what the images are like        (measured)
SceneMotion       how the camera moved            (measured)
SceneDescription  what is in them                 (asserted)
```

The pairs worth reading together, because in each case one resolves an ambiguity
in the other:

| Measured | Asserted | What the pair settles |
| --- | --- | --- |
| `textureless_fraction` | `empty_regions` | whether the empty area was wanted |
| `repetitiveness` | `repetition` | within-image vs between-image ambiguity |
| — | `dynamic_content`, `material_hazards` | nothing else measures these at all |
| — | `main_subject`, `subject_completeness` | whether "coverage" means an object or a volume, and whether the object even fits |

A worked reading, DTU scan10 — and the first field is why this module exists:

```
SceneTriage       textureless_fraction 0.5954   repetitiveness 0.6515
SceneDescription  empty_regions "blown-out white background surrounding the
                                 object; not wanted"
                  repetition none
```

Which turns a warning into a non-event: 60% of the frame carries no texture and
none of it is surface anyone asked for.

**That example is also a warning about this module.** The first draft of this
paragraph said *"black turntable background"* — written from a memory of what DTU
looks like, without opening the sheet. It is white. The report was fluent,
correctly shaped, would have passed validation, and was wrong about the scene.
Nothing here can catch that; see
[limitations.md](limitations.md#the-report-can-be-wrong).
