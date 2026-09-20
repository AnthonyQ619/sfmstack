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
  repetition_texture () str  EXTRA -- always present, <=260 chars
  repetition_objects () str  EXTRA -- always present, <=260 chars
  third_frame     ()  str   EXTRA -- '[k] - why', the chosen full-res cell
  dynamic_content ()  str   EXTRA
  material_hazards()  str   EXTRA -- none / diffuse / coherent
  hazard_position ()  str   EXTRA, when a reflector was reported
  hazard_notes    ()  str   EXTRA, when present
  notes           ()  str   EXTRA, when present
  browsed         (B,) str  EXTRA -- the filenames actually shown
  full_res_frames (3,) str  EXTRA -- first, last, and the chosen one

data/browse/contact_sheet.jpg         sidecar, both runs -- the ONLY image written
```

**Only two arrays are declared in the type**, and the rest ride as extras
recorded in the manifest's `extras` block. That is not laziness: the rubric is
expected to be revised, and a schema that churned with it would drag every
producer of `scene_analysis/v1` along. Promote a field into the type once it has
stopped moving.

**`browsed` and `full_res_frames` are the provenance.** Without the first, the
report is a claim about a set nobody can reconstruct — the browse set is a
*sample* of the scene, and which sample matters. The second records the three
frames opened at full resolution, which is what makes a claim about gloss or
clipping traceable to something better than a 384px cell. Two of the three are
the same on every scene; the third is the reader's, and `third_frame` carries
their argument for it. Neither array attests that anyone looked — they record
what the protocol REQUIRED.

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
| `material_hazards` | 0 none, 1 diffuse, 2 coherent - graded by whether the reflection carries an image |
| `hazard_position` | 0 background, 1 on_subject, 2 between_camera_and_subject, 3 throughout. Codes, not a severity |
| `third_frame` | which cell the reader chose to open at full resolution |
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

**Going from a cell to that path: the filename under the cell is the key, not the
index.** `[k]` numbers the browse set, which is a subset of the scene in scene order;
it is not the scene's own image index, and the two coincide only when every frame was
browsed. The filename under cell `[k]` is `browsed[k]`, and the scene's `images/names`
array holds the same filenames in scene order, so the frame's scene index is where that
filename sits in `names` — the one lookup that turns a sheet observation into an
addressable frame. Name frames by filename when reporting, and the question does not
arise for a reader.

**Know what the sheet cannot settle.** It is two downscales deep: SceneLoader
resized the capture, and each cell resizes that again to a
`thumbnail_max_side` long edge. A DSLR frame at 6221x4146 loaded with
`resize=fixed [1024, 682]` reaches the sheet as a 384x256 cell — 6% of the
original linear scale, 0.4% of its pixels. Whether a surface is glossy, whether a
white region is *clipped* or merely bright, whether a shopfront is glass or
printed card: none of those survive to there. Which is why the reading protocol
opens three frames at full resolution — two fixed, one chosen — and records all
three as `full_res_frames`.

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
| `repetitiveness` | `repetition_notes.texture` | within-image vs between-image ambiguity |
| nothing | `repetition_notes.objects` | no module here counts objects at any level |
| nothing | `material_hazards`, `hazard_position` | whether a reflection carries an image, and where it lands |
| — | `dynamic_content`, `material_hazards` | nothing else measures these at all |
| — | `main_subject`, `subject_completeness` | whether "coverage" means an object or a volume, and whether the object even fits |

A worked reading on a studio-rig capture — and the first field is why this module exists:

```
SceneTriage       textureless_fraction 0.5954   repetitiveness 0.6515
SceneDescription  empty_regions "blown-out white background surrounding the
                                 object; not wanted"
                  repetition_notes.texture "none - aperiodic granular stone"
```

Which turns a warning into a non-event: 60% of the frame carries no texture and
none of it is surface anyone asked for.

**That example is also a warning about this module.** The first draft of this
paragraph said *"black turntable background"* — written from a memory of what DTU
looks like, without opening the sheet. It is white. The report was fluent,
correctly shaped, would have passed validation, and was wrong about the scene.
Nothing here can catch that; see
[limitations.md](limitations.md#the-report-can-be-wrong).
