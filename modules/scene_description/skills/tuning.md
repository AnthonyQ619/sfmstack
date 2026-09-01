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

## Coherent reflection

The `coherent_reflection` diagnostic points here. This module cannot do anything
about the hazard — it only reports it — so what follows is what to do about it
*downstream*, which is the question a reader arriving from the diagnostic actually
has.

**What is true.** A legible reflected image produces correspondences to a virtual
point behind the reflecting surface. Those features are self-consistent, so they
pass RANSAC, and a healthy `inlier_ratio` is not evidence against them. Bundle
adjustment does not remove them: measured on a capture where the flagged surface
could be isolated in the finished cloud, the error ratio between reflection points
and the rest was unchanged to two decimal places either side of a global solve.

**What is NOT true, and this section exists because the diagnostic used to say it
was.** Reprojection error is not blind to the hazard. Point by point a virtual
point does reproject well — that part is right. As a *population* it does not. On
the same capture, points on the reflecting surface carried **3.1× the mean
reprojection error** of the rest of the model (0.524 px against 0.170 px, medians
0.350 against 0.129). The distribution separates cleanly even though no individual
point looks wrong. Several readers were told the metric could not see this and
stopped looking.

**The probe, in order of cost.**

1. **Read `p95_reprojection_error` beside `mean_reprojection_error`** on the
   finished `sparse_model/v1`. A p95 far above the mean is a localised population
   of bad points, which is the shape this hazard makes. This costs nothing and is
   the reason that metric is published.
2. If the flagged surface is separable — by colour, or by which frames see it —
   isolate those points and compare error *distributions*, not individual points.
   That is the measurement above, and it has to be built from the raw arrays.
3. `hazard_position` says where the phantom lands. Between camera and subject is
   the worst case; a reflection in a background window is often ignorable.

**What still has no answer.** Nothing localises a *named surface* in a finished
cloud, so step 2 needs a segmentation you invent yourself, and a null result from it
is weak. No module in the sparse or optimization families has a parameter, filter or
metric that separates a virtual point from a real one. The honest position on a
capture with this hazard is that the model is internally consistent and that
internal consistency and correctness are further apart here than usual.
