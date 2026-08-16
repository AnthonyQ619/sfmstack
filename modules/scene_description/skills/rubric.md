---
module: SceneDescription
rubric_version: 3
revised: 2026-08-15
status: v3 — settling. Every field here has to earn its place, and two have failed to.
---

# The rubric

Answer these after looking at the contact sheet. Pass the answers as the `report`
parameter on a second `sfm_run`.

**The test every field must pass:** *could `SceneTriage` or `SceneMotion` already
tell me this?* If yes, it does not belong here. Restating a measured number in
prose adds nothing and dilutes the fields that carry something new. Each field
below names what it is for.

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

Say "none" if the frame is textured throughout.

### `repetition` — enum

`none` · `within_image` · `between_images` · `both`

**What this adds:** `repetitiveness` measures self-similarity *within one image*
and its own limitations file says it cannot see between-image ambiguity. Forty
photographs of forty near-identical bays defeat matching just as thoroughly and
score low there.

- `within_image` — one frame contains several near-identical structures
- `between_images` — different frames show different-but-identical-looking parts
  of the scene, so a matcher could link the wrong two

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

`none` · `minor` · `substantial`

Glass, mirrors, standing water, polished metal, chrome. **Measured nowhere.** A
reflection is a correspondence to a virtual point *behind* the surface, so it
triangulates confidently to the wrong place **and reprojects beautifully** —
reprojection error will never find it, and neither will bundle adjustment.

**The levels are graded by WHERE the reflector is, not by how much of it there
is**, because that is the axis that decides where the phantom structure lands:

- `none` — no glass, mirror, water or polished metal in frame
- `minor` — reflective surfaces are present but **in the background**, not on the
  surface being reconstructed. Expect spurious points somewhere nobody is looking.
- `substantial` — reflective surfaces are **on the subject itself**, or across
  most of the frame. Expect phantom structure *inside* the model you wanted.

Two worked cases from the scenes run so far. ETH3D meadow is `minor`: a
mirrored-glass office block sits in the mid-distance behind a matte painted
building. ETH3D courtyard is `substantial`: the arched windows are on the facade
being reconstructed, and at full resolution one of them shows a **coherent
reflected building** — facade, windows and all, not glare. Those features match
well and are self-consistent, so they can be RANSAC *inliers*.

Requires `hazard_notes` when not `none`.

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
for promotion into the required set.

---

## Answering well

**Refer to cells by index.** The sheet labels each `[k] filename`. "Water in
[8]–[11]" is checkable; "some water" is not.

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
| 3 | 2026-08-15 | Removed `capture_style` — measured elsewhere, and it failed the rule at the top of this file. Cost: `sweep` was the only way to report a rotation-dominant pan that `pure_rotation_risk` misses, being computed over consecutive pairs only; say it in `overall` now. Graded `material_hazards` by WHERE the reflector is rather than how much of it there is. Made `empty_regions` a three-part answer, adding clipped-vs-flat because those have opposite gradients. Named `overall` as the field to act on. |
| 2 | 2026-08-15 | Added `main_subject` (required) and `subject_completeness` (contingent). Removed `expected_difficulty`. Split identity from composition: `subject` was carrying both and did neither cleanly. The completeness field comes straight out of the scan10 run, where the object is cropped in all twelve frames and v1 had nowhere to say so — it went into `notes`, which is where a missing required field goes to be noticed. Nine required fields still, one of them new and one retired. |
| 1 | 2026-08-15 | Initial. Nine required fields, chosen to target the five documented blind spots of `SceneTriage` and `SceneMotion`. Untested against any scene. |
