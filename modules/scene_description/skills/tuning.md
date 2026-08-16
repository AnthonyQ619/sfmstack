# Tuning — SceneDescription

Four parameters shape the browse set and one carries the payload. None of them
changes a measurement, because there is no measurement — so "tuning" here means
*making the thing legible*, and the failure mode is that an illegible sheet looks
exactly like a legible one.

---

## The sheet is unreadable

**Read it as:** cells too small to answer the rubric from. There is no metric for
this and there cannot be. Open the sheet.

**Gradient:**

1. Lower `n_images` toward 10 before raising `thumbnail_max_side`. Fewer, larger
   cells beat more, smaller ones — the rubric is about the character of the
   capture, not about completeness.
2. Raise `thumbnail_max_side` from 384 toward 512 when the open question is
   material (glass? water? polished?) rather than layout.
3. For a question about one frame, stop using the sheet — reach for the scene's
   own working image at full resolution:
   `sfm_artifact_image(<scene_id>, 'images/000003.png')`. This module writes no
   per-frame thumbnails, because a 384px copy of a picture you already have is
   worse than the original.
4. `grid_cols` is layout only. 4 suits 12 cells; 3 gives taller cells for a
   portrait capture.

**Do not** raise `n_images` past ~15 hoping to catch a rare hazard. It shrinks
every cell to buy coverage of a thing you probably still will not see, and the
report will read `none` with more confidence than before. Widen the sample by
running the module twice over different `sampling` instead — both artifacts
persist.

---

## `sampling` — which question are you asking

**`uniform` (default)** spans the capture. This is right for a description,
because the rubric asks what the whole set is like.

**`head`** shows a contiguous run. Use it only when the question is specifically
how much *consecutive* frames differ — for instance when `SceneMotion` reports
low `variability` and you want to see whether that is a rig or a slow pan.

The two produce different artifacts, so you can hold both.

---

## The report was refused

The module raises with a list of what failed. Three cases:

1. **A missing or empty required field.** Nine are required; the rubric names
   them. A half-filled report is refused rather than recorded, because a
   description with holes is worse than none — it reads as a completed assessment.
2. **An enum outside its vocabulary.** The closed vocabularies exist so the
   derived metrics mean one thing. `probably outdoor` is not `outdoor`.
3. **A flagged hazard with no `hazard_notes`.** `dynamic_content` or
   `material_hazards` above `none` requires a note. A hazard flag without a note
   raises a warning nobody can act on.

Extra keys beyond the rubric are **not** refused — they ride into the artifact as
extras. Fields that keep appearing there are candidates for promotion into the
required set.

---

## Re-describing a scene

Just run it again with a different `report`. The two are separate artifacts and
`sfm_compare` will show them side by side.

Worth doing after a pipeline has run and disagreed with the description. The
disagreement is the lesson: a report that said `material_hazards: none` on a scene
whose structure landed behind a window is a correction worth having on the record
beside the original, which is why the original is not overwritten.
