# Limitations — SceneDescription

This module has one limitation that dominates the rest, so it goes first.

---

## The report can be wrong

Every other artifact in this system is the output of an algorithm reading pixels.
This one is the output of someone *looking*, and **nothing in the container can
check whether the answers are true.** Validation covers shape only: required
fields present and non-empty, enums inside their vocabulary, a note attached to
any flagged hazard.

That means the failure modes are unlike anything else here:

- **A confident wrong answer costs more than no answer.** `dynamic_content: none`
  on a scene with people walking through it does not merely fail to help — it
  actively licenses trusting an `inlier_ratio` that should have been distrusted.
  `unknown` and `none` are not the same claim; when you cannot tell, hedge in
  `overall` rather than guessing an enum.
- **The reader cannot tell a careful report from a careless one.** They are the
  same shape. `browsed` records which images were shown, which is the only
  provenance available.
- **It ages differently from a measurement.** Re-running `SceneTriage` on the same
  scene gives the same numbers forever. Re-running this gives whatever the viewer
  says today.

**So: treat a hazard flag as a reason to look, and treat a clean report as weaker
evidence than a clean measurement.** The asymmetry is deliberate — a warning here
is worth acting on because nothing else would have raised it; a clean bill of
health here is worth less than a clean bill from `SceneMotion`.

---

## What this adds over the measured modules

Stated as a boundary rather than a feature, because the rubric will drift toward
restating numbers if nobody holds the line.

Four things are covered that are **measured nowhere in this system**:
`dynamic_content`, `material_hazards`, `hazard_position`, and the `objects` half
of `repetition_notes`. Both are failures that hide. A track through a moving object
is locally consistent — the correspondences are real, the geometry is not, and
reprojection error will not find it. A reflection triangulates confidently to a
virtual point behind the surface and reprojects beautifully.

Three fields cover things a measurement **sees partially**:

- `empty_regions` resolves the ambiguity in `textureless_fraction`, which counts
  area and cannot say whether the empty region was wanted. This is the exact trap
  a studio-rig set: 60% textureless, entirely harmless, because it is a blown-out
  white studio sweep.
- `repetition_notes.texture` covers the between-image case that `repetitiveness`
  explicitly cannot see, being a within-image measurement. Its `objects` half
  covers something no module here sees at ANY level, because nothing counts
  objects, so that half sits with the group above as much as here. There is no
  enum in front of the note any more: four gradings across four revisions never
  discriminated, and the note carried the difference every time.
- `main_subject` and `subject_completeness` cover what nothing here counts: whether
  the images are of one thing, and whether that thing fits inside them. Without
  them a correct reconstruction of a cropped object reads as a coverage failure.

**The test for a new field:** could `SceneTriage` or `SceneMotion` already tell me
this? If yes, it does not belong.

---

## Two fields were tried and cut

`capture_style` — turntable / orbit / walk_along / sweep / aerial / unordered —
was removed in v3 for failing the rule the rubric opens with: `rotation_median_deg`,
`variability`, `overall_magnitude` and `metadata.ordered` between them already say
what the camera did, and they say it by measurement rather than assertion.

**It cost one thing, and it is worth knowing what.** `sweep` was the only way to
report a rotation-dominant pan that `pure_rotation_risk` misses, because that cue
is computed over consecutive pairs only — a capture that pans back and forth can
read 0.0 there and still be rotation-dominated overall. That observation now has
to go in `overall` as prose, where nothing counts it.

---

## A subjective grade was tried and cut

v1 had an `expected_difficulty` enum — `easy` / `moderate` / `hard` — on the
argument that a prediction made *before* the pipeline runs and stored where it
could be scored was worth something.

It was removed in v2 without ever being scored, on a simpler objection: it
carried nothing the `overall` paragraph does not, and it put a number where a
reason belongs. A reader who sees `2` learns that someone was pessimistic; a
reader who sees *"the object is cropped in every frame so only a corner is
reconstructable"* learns what to do. The paragraph was always doing the work.

The general form of the lesson, for anyone adding a field: **a field that
compresses a judgement into a grade is the kind most likely to be read instead of
the reasoning it came from.** The fields that survived all name a specific
observable thing.

---

## One sheet is not the dataset

The browse set is a sample — 12 of however many, uniform by default. A hazard
present in three frames out of eighty may not appear on the sheet at all, and the
report will say `none` in good faith.

`browsed` records the filenames actually shown, so the claim's scope is
recoverable. Raising `n_images` widens the sample and shrinks the cells, and the
second effect is the dangerous one: a sheet with 40 unreadable cells looks exactly
like a sheet with 12 readable ones.

---

## The rubric is version 3 and thinly tested

Eight required fields, targeting the documented blind spots above, exercised
against **three scenes**: a studio rig, a low-contrast field capture, and a masonry courtyard. Across three
versions it has added two fields and cut two. Expect more to move — three scenes
is enough to see that a field is missing and not enough to know that one is
right. [rubric.md](rubric.md) carries a revision log; the closed vocabularies
are duplicated in the adapter, and a test asserts the two agree so they cannot
drift apart silently.

---

## Two artifacts per description

The un-described run and the described run are separate artifacts with separate
ids, because the report is part of the recipe. This is deliberate and it has a
cost: the sheet is rendered twice, and a run summary shows two
`SceneDescription` steps where a reader might expect one.

The alternative — mutating an artifact to add the report — is not available, and
should not be: artifacts are write-once, and a description that could be edited in
place after downstream work consumed it would be a provenance hole.
