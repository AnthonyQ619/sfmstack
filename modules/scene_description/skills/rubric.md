---
module: SceneDescription
rubric_version: 7
revised: 2026-08-16
status: v7 — the repetition enum is gone; the note is the field, and it is asked of every scene.
---

# The rubric

**The test every field must pass:** *could `SceneTriage` or `SceneMotion` already
tell me this?* If yes, it does not belong here. Restating a measured number in
prose adds nothing and dilutes the fields that carry something new. Each field
below names what it is for.

---

## Look at these, in this order, before answering anything

This part is **fixed**, and that is the whole reason it is written down. Not
"look at what seems relevant" — the same three images, in the same order, on
every scene.

**1. The contact sheet.** `sfm_artifact_image(<the analysis artifact>)`. It is
the only image that artifact carries, so no `name` is needed.

*What the sheet actually is:* one JPEG grid, `grid_cols` wide, built from
`n_images` frames drawn `uniform`ly across the scene's working images. Each cell
is that frame thumbnailed to a `thumbnail_max_side` long edge with a 16px strip
underneath carrying `[k] original_filename`. The `[k]` is the index every answer
below should refer to.

The thing to keep in mind about it: **it is two downscales deep.** SceneLoader
already resized the capture, and the sheet resizes that again. On an ETH3D
capture — 6221×4146 native, loaded at `resize=fixed [1024, 682]`, thumbnailed to
384 — a cell is 384×256. That is 6% of the original linear scale and 0.4% of its
pixels. The sheet answers *what is this capture* very well and it cannot answer
*is that surface glossy*, *is that white clipped*, or *is that window glass or
printed card*. Three of the fields below ask exactly those.

**2 and 3. The first and last frames of the browse set, at full resolution.**
`sfm_artifact_image(<the SCENE artifact>, 'images/000000.png')` and the same for
the last. The `awaiting_description` diagnostic prints both calls with the names
already filled in — use those, do not construct them.

**Why those two are fixed.** Because a viewer who chooses all their own chooses
the interesting ones — and then every scene has been read by a different
procedure and no two readings are comparable. First and last also happen to be
the widest-separated pair in the set, which is where a capture is most likely to
have changed.

**4. One more cell, of your choosing, and say why.** Any cell except the first
and last. Record it in `third_frame` as `[k] — the reason`.

**Why there is a free one at all.** Because fixity has a cost and it was paid
immediately. On ETH3D facade the worst thing in the scene is a mirror-polished
sculpture standing between the camera and the building; it appears only in cells
[2]–[6], so under the two-frame protocol it could only be graded from a 384px
thumbnail, and the report had to say so. One free view recovers that without
giving up the comparable base — two frames read the same way on every scene, one
that follows the scene.

**Spend it on what the fixed two could not settle.** A hazard visible only in the
middle of the set. A frame the sheet suggests is different in kind. The cell a
diagnostic points at. Not "the nicest picture" — if the fixed two already
answered everything, say that in the reason and pick the least similar cell.

All three names are recorded in the artifact as `full_res_frames` and the chosen
index as the `third_frame` metric, so a second reader can repeat the reading
exactly — including the choice and the argument for it.

**If the full-resolution frames contradict the sheet, the frames win, and say so
in `notes`.** That has already happened twice: DTU scan15's shopfront "glazing"
reads as glass on the sheet and is printed card at full resolution, and ETH3D
office's flat regions read as ordinary and are *underexposed* — maximum pixel
187, which is the opposite gradient.

---

## Required

### `environment` — enum

`indoor` · `outdoor` · `studio` · `mixed`

*Studio* means a controlled capture rig: uniform background, controlled light, a
turntable or arm. It is not "indoor with good lighting".

**What this adds:** it selects trained weights. `FeatureMatchLoFTR` and
`FeatureMatchRoMa` each take a `setting: indoor | outdoor` that picks between two
separately trained models — MegaDepth (buildings, landmarks, wide baselines)
against ScanNet (rooms, close range, low texture). Nothing measured here
distinguishes those, and the modules' own tuning notes say the wrong one costs
`inlier_ratio` outright.

**`studio` and `mixed` do not map cleanly onto that switch, and saying so is the
useful part.** A rig capture of an object on a sweep is unlike ScanNet rooms and
unlike MegaDepth landmarks; neither weight set was trained on it. Report `studio`
rather than forcing it to `indoor`, and expect to have to try both.

### `main_subject` — free text, one line

**Is there a single object these images are of?** If yes, name it *generally*. If
no — the images are of a place, a street, a landscape, a collection — answer the
single word `none`.

**What this adds:** nothing in this system counts objects. It decides what
"coverage" even means downstream: covering an *object*, or covering a *volume*.

**Keep it general.** `a cardboard box`, `a stone building`, `a statue`. Not `a
Kellogg's cereal box` and not `St Mary's Church` — you may be right about the
category and wrong about the specific, and the specific buys nothing.

Answering `none` is a real answer, not a failure to look. A street scene has no
main subject and saying so is the correct report.

### `subject_completeness` — enum, required when `main_subject` is not `none`

`complete` · `cropped` · `occluded` · `both`

**Does the thing you just named actually fit?**

- `complete` — fully inside the frame in essentially every image
- `cropped` — extends past the frame edge; the capture never contains all of it
- `occluded` — something else in the scene hides part of it
- `both`

**What this adds:** this is the field DTU scan10 produced and v1 had nowhere to
put. The box is cropped in all twelve frames, so what is reconstructable is a
corner and not a box — and a reader judging point count against "a box" would
read a correct result as a failure. `cropped` and `occluded` are separated
because their consequences differ: cropping is a framing limit of the capture,
occlusion is holes where something was in the way.

The module refuses a report that names a main subject and leaves this empty, and
refuses one that answers this while `main_subject` is `none`.

### `subject` — free text, one line

Composition, as distinct from identity. What is in the frame and how it is
arranged — whether it is mostly subject or mostly context, where the subject
sits, what surrounds it. "A stone church filling the lower two-thirds; sky above"
is useful. "Building" is not.

`main_subject` answers *what is it*; this answers *what does the picture look
like*. A scene with `main_subject: none` still has a composition worth
describing.

### `empty_regions` — free text

**Answer three things about every low-texture region, in this order:**

1. **Where** it is, and roughly how much of the frame.
2. **Wanted or not** — is it surface someone is trying to reconstruct, or backdrop?
3. **Clipped or merely flat** — is it at 0 or 255, or just low-contrast?

**Why (2):** `textureless_fraction` counts area and is explicitly blind to it. On
DTU scan10 it reads 0.60 because the background is a blown-out white sweep, which
is harmless. The same number on a scene whose *subject* is a blank wall is fatal.

**Why (3):** clipped means the detail is **destroyed** — no exposure
normalisation, no CLAHE, no raising `max_edge` recovers a region at 255, and
suggesting any of them is wasted effort. Merely flat means the detail may survive
at another exposure or another scale, and normalising at detection is worth
trying. The fraction cannot distinguish these either, and they have opposite
gradients.

**A scene can be all three at once and usually is.** ETH3D meadow has unwanted sky,
wanted-but-degraded grass, and wanted-and-low-texture clapboard siding which is
the actual reconstruction target — one number covers all of it. Enumerate them
separately rather than averaging.

Say "none" if the frame is textured throughout.

### `repetition_notes` — mapping, always required

Two keys, both required, **one or two sentences each**. The module refuses a
half-filled note and refuses one over 260 characters per half.

```
repetition_notes: {
  texture: "...",     repeating SURFACE PATTERN
  objects: "...",     repeating DISCRETE OBJECTS
}
```

**`texture`** — brick coursing, roof tile, floor tiling, chain-link, cladding
fins, corrugation. A pattern *on* something, with no individual identity: you
cannot point at one brick and call it a thing.

**`objects`** — identical windows, identical dormers, identical street lamps,
identical canopies. Things you could count.

**There is no enum in front of this, and there used to be.** It was graded four
ways in four revisions — four values, then two enums, then one enum, then a
yes/no — and it never discriminated: `both` on eleven readings of fourteen, then
`present` on eight scenes of eight. By the last version it had been reduced to a
gate meaning *read the note*, and a gate that is always open is not a gate. So
the note is asked of every scene and the enum is gone.

**Answer both halves even when the answer is `none`.** A blank half reads as an
oversight. `none` is a finding, and on DTU scan33 it is the whole story: the cast
stone is genuinely aperiodic, which is exactly what makes its two identical ear
cups the thing to worry about.

**Keep it short.** The cap is enforced because this note now carries the entire
field, and the temptation is to grow it into a second `overall` — which puts the
reasoning in two places and leaves a reader unsure which to act on. Say *what*
repeats and *in which cells*; argue about it in `overall`.

> `texture: "Roof tile as a fine regular grid on both roofs, plus brick coursing
> and a paving-slab grid. Locally varied by chimneys and vents, so this is the
> milder half."`
> `objects: "Three identical dormer castings per roof in [11], identical window
> surrounds on every storey, two identical model trees. Same part repeated, not
> merely similar."`

**What this adds over what is measured:** `repetitiveness` measures
self-similarity *within one image* and its own limitations file says it cannot
see between-image ambiguity. It has been caught being wrong in the direction that
matters — 0.6213 on ETH3D meadow, the lowest of ten scenes, for a building of
near-identical repeating bays. And nothing here counts objects at any level.

**Why two halves rather than one — the escapes are opposite.**

| | what can separate two instances | what cannot |
| --- | --- | --- |
| **texture** | scale, and what surrounds the patch — a bigger descriptor support, a higher working resolution, more context | a per-match ratio test, which sees only the two patches |
| **objects** | a matcher reasoning jointly over *all* correspondences, using the global arrangement | any descriptor, however invariant — two castings of one mould are identical at every scale, and invariance is precisely what makes them match |

That second row is the one worth internalising. Reaching for a better detector
against repeated objects is reaching in the wrong direction: it makes the wrong
match *more* confident.

**No diagnostic fires for this.** There is no level left to threshold, and both
halves land in the artifact's narrative body, which `sfm_run` returns inline. If
the repetition is the thing that will break this scene, say so in `overall` —
that is the field a reader acts on.

### `dynamic_content` — enum

`none` · `minor` · `substantial`

**What this adds: nothing else in the stack sees this.** Both measuring modules
list it as unimplemented. Moving content is the failure that hides — the
correspondences are real, the geometry is not, and every downstream metric looks
healthy.

- `minor` — a person at the edge of one or two frames, leaves moving
- `substantial` — movers across much of the set, water, a crowd

Requires `hazard_notes` when not `none`.

### `material_hazards` — enum

`none` · `diffuse` · `coherent`

**Does the reflective surface carry a legible IMAGE of something else?**

- `none` — no glass, mirror, water, polished metal or glossy surface in frame
- `diffuse` — glossy, but the highlight has no image in it. A sheen, a bright
  patch, a soft specular lobe
- `coherent` — you can make out *what* is being reflected: a building, a window
  frame, the sky with structure in it

**Why coherence and not amount.** Coherence is the mechanism. A coherent
reflection is a correspondence to a virtual point **behind** the surface, so it
triangulates confidently, reprojects beautifully, and can be a RANSAC inlier —
nothing downstream will find it. A diffuse highlight creates no virtual point at
all. It creates a bright patch that moves with the *camera* rather than the
surface, so correspondences there drift or drop out and that part of the model
thins. **Opposite failures, opposite responses**, and a reader who goes hunting
for phantom structure after a diffuse reading wastes the effort.

Measured nowhere else in this system, at any level.

**The material list is indicative, not exhaustive.** Glass, mirrors, standing
water, polished metal, chrome — and anything else whose appearance changes with
viewpoint. DTU scan33's ear defenders are glossy injection-moulded plastic, on
none of those lists, and in [11] the near cup carries a legible window frame
while the printed text beneath it stays put. That is `coherent`.

Requires `hazard_notes` and `hazard_position` when not `none`.

### `hazard_position` — enum, required when `material_hazards` is not `none`

`background` · `on_subject` · `between_camera_and_subject` · `throughout`

**Where the reflector sits, which decides where the phantom structure LANDS.**
Coherence says *whether* it can happen; this says *where it goes*, and they are
independent — a mirror in the background is a curiosity, the same mirror between
the camera and the subject is a hole in the model.

- `background` — behind the surface being reconstructed. Spurious points
  somewhere nobody is looking; often ignorable, but decide rather than assume
- `on_subject` — on the surface being reconstructed, so the phantom lands on the
  thing you wanted
- `between_camera_and_subject` — **the dangerous one.** Close to the camera, so
  the virtual points land well inside the model. ETH3D facade's mirror-polished
  sculpture is this, and no earlier version of this rubric could say so
- `throughout` — across most of the frame; no part of the model is clear of it

**This is a position, not a severity**, which is why it is a separate field
rather than more values on the enum above. It is also asked directly rather than
derived from the subject, because half the scenes read so far report
`main_subject: none` and "on the subject" has no meaning there.

**The module refuses this when `material_hazards` is `none`** — there is nothing
to place — and refuses its absence when there is.

### `third_frame` — free text, one line, format enforced

**Which cell you opened at full resolution beyond the fixed first and last, and
why.** Format: the index in brackets, then the reason.

```
third_frame: "[5] - the only cell where the whole reflector is in view"
```

Four things are checked and any of them refuses the report: it must name a cell
as `[k]`, that cell must exist in the browse set, it must not be the first or
last (those are opened anyway, so choosing one adds nothing), and a reason must
follow.

**This is the only judgement in the viewing protocol, which is why it is
recorded.** An unexplained choice cannot be reviewed, and a reading whose third
view was "a nice frame" is worth knowing about.

### `overall` — free text, one paragraph

What this scene is, and what will be hard about it. This is the field a reader
actually reads.

**No difficulty rating.** v1 had an `expected_difficulty` enum and it was cut: a
one-word subjective grade carried nothing the paragraph does not, and it invited
a number to be read where a reason was needed. Say what will be hard and why; do
not grade it.

---

## Optional

### `hazard_notes` — free text

**Required** when `dynamic_content` or `material_hazards` is not `none`; the
module refuses the report otherwise. Say *what* and *where* — cell indices from
the contact sheet are the useful unit: "mirrored shopfront in [3] and [4]".

### `notes` — free text

Anything else worth recording. Fields that keep reappearing here are candidates
for promotion into the required set. **Where a full-resolution frame contradicted
the sheet, that belongs here.**

---

## Answering well

**Refer to cells by index.** The sheet labels each `[k] filename`. "Water in
[8]–[11]" is checkable; "some water" is not.

**Three cells are privileged and the rest are not.** The first, the last, and
the one you chose were seen at full resolution; everything else was seen at a
thumbnail. A claim about material, gloss, clipping or fine detail is well founded
in those three and is an inference everywhere else. Write it that way — "matte in
[0] and [11], and nothing on the sheet suggests otherwise" is honest; asserting
the same about all twelve is not. Where a grading rests on a thumbnail, say so in
the field itself, not just in `notes`.

**Describe the set, not the best image.** The question is what the capture is
like, and one clean frame does not make a clean capture.

**Say what you cannot tell.** A hedge in `overall` is better than a confident
guess in an enum. The report is asserted, not measured, and its only defence is
that it is honest about its own confidence.

**Do not predict metrics.** If you find yourself writing "texture looks dense",
delete it — `texture_density` measured it. Write what a number cannot hold. This
is the rule that killed `capture_style` in v3: `rotation_median_deg`,
`variability`, `overall_magnitude` and `metadata.ordered` between them already say
what the camera did, and they say it by measurement.

**`overall` is the field that gets acted on.** It leads the artifact's narrative
body and it is what a reader weighs against the `SceneTriage` and `SceneMotion`
metrics when choosing a pipeline. Everything else here is its machine-readable
shadow — the enums make a hazard countable and a diagnostic possible; they do not
carry the reasoning. Write the paragraph as though it were the only field, because
for the decision it usually is.

---

## Revision log

| Version | Date | Change |
| --- | --- | --- |
| 7 | 2026-08-16 | **Removed the `repetition` enum.** Four gradings in four revisions and it never discriminated — `both` on eleven readings of fourteen, then `present` on eight of eight. v6 had already reduced it to a gate meaning "read the note"; a gate that is always open is not a gate. `repetition_notes` is now required unconditionally and is the field. The metric and its diagnostic go with the enum: there is no level left to threshold, and both halves reach the reader through the artifact's narrative body, which `sfm_run` returns inline. |
| 6 | 2026-08-16 | **`repetition` is now yes/no.** Three graded versions in three revisions answered `both` on eleven of fourteen readings; the only question the level was really asking was whether to read the note. The note carries the field and is capped at two sentences per half so it cannot become a second `overall`. **`material_hazards` regraded by COHERENCE** — does the reflection carry a legible image — because that is the mechanism that separates phantom geometry from drift, and the old WHERE rule graded a soft sheen on a wall the same as a mirror. **`hazard_position` split out as its own field**, which finally lets a reflector between camera and subject be named; the old rule graded that worst case mildest, and its "on the subject" test was undefined on the four scenes reporting no main subject. Two hazard diagnostics now, `coherent_reflection` (warn) and `diffuse_reflection` (info), carrying opposite advice. |
| 5 | 2026-08-16 | **A third full-resolution view, chosen and justified.** Two stay fixed for comparability; the third follows the scene, because v4's fixity cost ETH3D facade a full-resolution look at its worst reflector. Named as `[k]` in `third_frame` with a reason, checked four ways, recorded as a metric so the choices can be audited. **And the repetition split moved out of the enum into the note.** v4's two enums agreed on four of six scenes and their diagnostics fired together on every scene where either fired but one — a duplicate alarm and no extra discrimination. The prose carried the difference every time. So: one `repetition` enum, one `between_image_repetition` diagnostic carrying both escapes, and `repetition_notes` promoted from free text to a mapping that must answer `texture` and `objects` separately. |
| 4 | 2026-08-16 | **Fixed the viewing.** The sheet plus the first and last frames at full resolution, prescribed rather than chosen, because a reader who picks their own two picks the interesting ones and no two scenes are then read alike. Documented what the sheet actually is and that it is two downscales deep. **Split `repetition` into `repetition_texture` and `repetition_objects`**, with `repetition_notes` contingent on either. One enum was answering two questions: the DTU model-town scans repeat *objects* out of a mould over ordinary brick, a tiled floor repeats *texture* with no objects at all, and both answered `both` under v3. The escapes differ — a bigger descriptor support can separate repeated texture, and cannot separate two castings of one mould. `between_image_repetition` becomes two 0–3 metrics with two diagnostics carrying different advice. |
| 3 | 2026-08-15 | Removed `capture_style` — measured elsewhere, and it failed the rule at the top of this file. Cost: `sweep` was the only way to report a rotation-dominant pan that `pure_rotation_risk` misses, being computed over consecutive pairs only; say it in `overall` now. Graded `material_hazards` by WHERE the reflector is rather than how much of it there is. Made `empty_regions` a three-part answer, adding clipped-vs-flat because those have opposite gradients. Named `overall` as the field to act on. |
| 2 | 2026-08-15 | Added `main_subject` (required) and `subject_completeness` (contingent). Removed `expected_difficulty`. Split identity from composition: `subject` was carrying both and did neither cleanly. The completeness field comes straight out of the scan10 run, where the object is cropped in all twelve frames and v1 had nowhere to say so — it went into `notes`, which is where a missing required field goes to be noticed. Nine required fields still, one of them new and one retired. |
| 1 | 2026-08-15 | Initial. Nine required fields, chosen to target the five documented blind spots of `SceneTriage` and `SceneMotion`. Untested against any scene. |
