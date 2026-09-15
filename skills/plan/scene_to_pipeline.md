---
name: scene_to_pipeline
description: How to read the step-2 scene analysis into an initial SfM pipeline. The measured ranges, what each number can and cannot tell you, and the shape of the plan that comes out.
status: accumulating — 16 scenes, 4 datasets. Every threshold here is an observation, not a law.
scenes: 16
datasets: [DTU, ETH3D, Tanks and Temples]
---

# Reading a scene into a pipeline

This file is the missing half of step 3. `skills/plan/<stage>.md` say *which member
of a stage to reach for* in prose — "when the scene is repetitive", "when the
detector fires on nothing". `SceneTriage`, `SceneMotion` and `SceneDescription`
produce numbers. **Nothing else in this repository translates between the two**,
and this file is where that translation is written down.

Measured against the family files: of the 29 metrics the three analysis modules
produce, exactly two are named anywhere in `skills/plan/` stage files —
`planar_dominance` and `pure_rotation_risk`, both in one paragraph of
`matching.md`. The families speak in adjectives; step 2 speaks in numbers. What
follows is the bridge, and it is empirical.

**A note on references.** `§N` always means a numbered section **of this file**,
listed at the top of each. A reference to another file always names it —
`matching.md §5`, `swap_or_build.md`, `modules/scene_triage/skills/limitations.md`.
Raw per-capture measurements are not kept here; they live in
[`skills/evidence/`](../evidence/EVIDENCE.md), and this file carries only what
generalises from them.

**Read this as evidence, not as rules.** Every band below is *the range observed
across N scenes*, and N is small. A number outside a range means "unlike the
scenes measured so far", which is a reason to look, not a verdict. Where a band
has been wrong, that is recorded here too, because a threshold that has already
failed once is the most useful kind.

> **A corpus maximum is an ORDER STATISTIC, not a bound**, and this is worth
> stating plainly because it has misled readers who understood everything else
> correctly. The highest value seen in seventeen captures is the largest of
> seventeen draws; the eighteenth exceeding it is the expected outcome, not an
> anomaly. Measured: a capture read outside a published maximum on a metric
> then described as "reliably quiet" while running at the exact protocol the corpus
> was fitted on — nothing about that run was unusual and nothing was wrong.
>
> The failure mode this creates is worse than a false alarm: a reader who trips a
> band that had no business bounding them learns to distrust a metric that was
> working. So when a reading sits just outside a band, the first question is
> whether the band could have contained it at all, and the second is whether any
> DIAGNOSTIC fired — a band with no diagnostic behind it is describing a corpus,
> not judging your capture.

---

## 1. What the numbers actually range over

**Sixteen captures across two benchmark families**, all at 12 images with
`sampling: head`: roughly half controlled-rig captures of a single object on a
lit backdrop, and roughly half field captures — building frontages, indoor
interiors, and open outdoor sites. Deliberately not enumerated: an earlier
version listed the kinds one by one, which made each a countable label, and a
reader recognised its own capture from a kind that had exactly one member.
Working resolution around 1024px on the long edge throughout.

> **The 12-image subset is how these numbers were FITTED. It is not how to run a
> reconstruction.** Load every frame the capture has. Frame selection is a
> decision for `SceneTriage` and for the modules that can drop what they cannot
> use — a reconstruction that never sees a frame cannot register it, and the
> frames a subset omits are disproportionately the ones that close a loop.
> Measured: rebuilding the same capture from a 12-frame head sample to its full
> set has returned more than twice the structure and four times the cameras, and
> a head sample has been shown to be a materially DIFFERENT scene from the
> capture it is drawn from — crossing a published band on a motion metric that
> the full capture reads comfortably inside.
>
> This matters for reading everything below, because it means your reading and
> the band may not be describing the same thing.

### Which bands survive a bigger capture, and which do not

Three groups, and the difference is mechanical rather than statistical:

- **Per-frame appearance metrics transfer in kind but NOT in value, because the
  fitting sample is a PREFIX.** `texture_density`, `textureless_fraction`,
  `sharpness_ratio`, `repetitiveness`, `empty_regions` and the clipping
  fractions are computed per image and averaged, so they measure the same
  quantity at any frame count. What they do not do is agree: `sampling: head`
  takes the *first* twelve frames, which is a **biased** sample of the traverse
  rather than a coarser one, and a capture whose content changes as it proceeds
  is a different scene in its first twelve frames than in all of them.

  Measured on every corpus capture rebuilt at the protocol: the head-sample
  `texture_density` runs from **half** the full-capture value to **half again
  above** it, and it is off by more than a third on a quarter of the corpus.
  `sharpness_ratio` nearly doubles on one capture. So a band in this file and
  your own reading may be describing different frames of the same capture, and
  the direction of the disagreement is not predictable from the frame count.
- **Adjacent-motion metrics are SAMPLING-DEPENDENT and do not transfer.**
  `overall_magnitude`, `combined_change`, `rotation_median_deg` and `variability`
  all measure what happens between neighbouring frames, and "neighbouring" means
  something different at 12 frames than at 50. The same capture reads LOWER on
  all of them when more frames are loaded, because consecutive frames are then
  closer together. See §3b.2 for how to normalise this rather than abandon it.
- **Whole-graph fractions do not transfer at all.** Anything denominated in
  *pairs* — most importantly the "roughly half the possible pairs" rule in §3b —
  is quadratic in frame count. Half of 66 pairs on a twelve-frame capture and
  half of 1176 pairs on a forty-nine-frame one are not the same statement, and
  that rule has since been measured failing in BOTH directions on full captures.
  Read per-image degree instead, which is linear and comparable: `min_image_degree`
  is the margin, and `graph_components` is only a terminal condition.

**The ranges below are what has been seen, not what is possible**, and their
extremes are named by the KIND of capture that produced them rather than by scene
id — a plan for a new capture can use "a controlled rig against a lit backdrop"
and cannot use a name. Per-capture numbers and their scene ids are in
[`skills/evidence/`](../evidence/EVIDENCE.md) for traceability.

| metric | low end is | median | high end is | spread |
| --- | --- | --- | --- | --- |
| `combined_change` | controlled rig | 0.0696 | open outdoor site | 3.6× |
| `texture_density` | indoor interior | 3479 | controlled rig | **12×** |
| `repetitiveness` | open outdoor site | 0.7163 | planar frontage | 1.3× |
| `textureless_fraction` | open outdoor site | 0.3865 | indoor interior | 6.3× |
| `sharpness_ratio` | indoor interior | 0.6280 | controlled rig | 5.9× |
| `sharpness_median` | indoor interior | 1363 | open outdoor site | **18×** |
| `highlight_clipped_fraction` | open outdoor site | 0.0421 | controlled rig | **bimodal, see below** |
| `shadow_clipped_fraction` | open outdoor site | 0.0000 | indoor interior | 11 of 16 at zero |
| `overall_magnitude` | controlled rig | 0.1193 | fast outdoor traverse | 9.7× |
| `high_motion_tail` | controlled rig | 0.1490 | indoor interior | 8.8× |
| `variability` | controlled rig | 0.0588 | indoor interior | 20× |
| `rotation_median_deg` | open outdoor site | 18.03 | indoor interior | 11× |
| `large_rotation_risk` | open outdoor site | 0.3636 | indoor interior | — |
| `planar_dominance` | — | **0.0000** | planar frontage, planar frontage | 13 of 16 at zero |
| `pure_rotation_risk` | — | **0.0000** | controlled rig, planar frontage | 14 of 16 at zero |
| `low_baseline_risk` | — | 0.0000 | **0.0000** | 16 of 16 at zero |

**The extremes are stated as capture KINDS, not values, and that is deliberate.**
The minimum and maximum of a sixteen-capture range are two specific captures'
readings, so printing them to four significant figures hands a reader a lookup key:
when their own number matches, they read their own capture back and mistake recall
for confirmation. Every reader in a ten-capture sweep identified its capture that
way, several to five figures. The median survives because it is far less likely to
be any single reading, and the spread column carries the shape of the range without
carrying an identifier.

**So locate yourself by kind, not by value.** "Is this a fast outdoor traverse or a
tight-arc rig?" is answerable from the description and transfers to a capture from
outside this corpus; "is 0.31 high?" is answerable only by lookup and does not. The
per-capture numbers remain in [`skills/evidence/`](../evidence/EVIDENCE.md) for
traceability — and following that link is how a reader leaks their own answer, so
go there to re-run a claim, not to place a reading.

**The four numbers that actually separate scenes** are `texture_density`,
`textureless_fraction`, `sharpness_ratio` and `overall_magnitude`. They span an
order of magnitude and their extremes are different scenes each time.

**`repetitiveness` barely separates anything** — 0.62 to 0.81 across every scene
including ones that are obviously repetitive and ones that are not. Treat a
reading in that range as no information. See §3.

**The degeneracy pair is almost always zero**, which is what makes a non-zero
reading worth acting on immediately rather than weighing.

**`low_baseline_risk` has never fired.** Not a defect — no capture measured here
is a dense video-rate sequence, and none should trip it. It is untested, not
broken, and it should not be read as reassurance.

### Every one of those numbers is a median, and the advice attached to them is not

A median cannot answer *which frame* or *which pair*, and half the guidance in §2
is per-frame: open the soft frame before dropping it, keep the planar pair out of
the seed, find the window that is blown out. That guidance was unfollowable from
the brief until **SceneTriage 1.1.0 and SceneMotion 1.1.0**, which ship the series
the summaries are computed from. `sfm_plan_brief` puts them under `series`,
grouped as the artifact stores them:

| series | indexed by | answers |
| --- | --- | --- |
| `texture.sharpness` (+ `sharpness_median`) | image | which frame is soft, and against what scale |
| `texture.density_per_image` / `textureless_per_image` | image | **which frame will starve the detector** — the set median hides a scene whose texture sits in half its frames |
| `photometric.highlight_clipped` / `shadow_clipped` | image | which frame is burnt, and at which end |
| `photometric.pair_combined` (+ `pair_index`) | pair | where the appearance drifts |
| `motion.pair_p75` / `pair_p90` (+ `pair_index`) | pair | where the capture is fast or slow |
| `motion.pair_rotation_deg` (+ `rotation_pair_index`) | pair | where the view swings |
| `degeneracy.pair_planar` (+ `pair_index`) | pair | **which pairs prefer a plane** |
| `degeneracy.pair_pure_rotation` (+ `rotation_pair_index`) | pair | which pairs have no parallax |

Indices are positions in `scene.images`, which the brief also carries; a pair
index is two of them. **Each series has the index it was written against** — they
are different subsets, because a pair can fit a homography and no rotation, so do
not zip one series against another's index.

Above 200 elements a series arrives summarised (min / median / max and the eight
extremes at each end) rather than whole. A pairwise series on a full capture under
exhaustive pairing passes that size, so expect the summary form there.

**That rule covers the ANALYSIS series described in this section, and nothing
else.** A pipeline artifact's stored arrays come back whole however large they are —
a detector's keypoint table is tens of thousands of rows and arrives as tens of
thousands of rows, megabytes of it. Readers have been surprised in both directions:
some expected a summary and got the raw array, one assumed the raw array was
unavailable and did not try. Whole is the useful behaviour and worth knowing about,
because it is what makes the content-masked coverage analysis in
`plan/detection.md` §3 possible at all — but ask for one deliberately rather
than in passing, and check the row count against the array shape the artifact
reports before you compute anything on it.

---

## 2. Metric by metric: what it decides

### `texture_density` — the detector question

Keypoints per megapixel. **The single most decisive number in step 2**, because
it is the one that says whether a detector-based pipeline is viable at all.

- **1600–5600** on fifteen of sixteen scenes. Anywhere in there, a classical
  detector works and the choice of detector is about the *matcher* rather than
  about texture.
- **One scene sits far below the rest**, and it is a room of blank painted walls
  — the case `detection.md` names: *"Neither, when the detector fires on
  nothing… a case for a detector-free matcher, which skips this stage
  entirely."* The shape to recognise is *a built interior whose surfaces are
  uniform paint or plaster*, not the number on its own.

> **The size of that gap was a property of the sampling, not of the capture, and
> this is the clearest case of the §1 warning above.** At the twelve-frame head
> the outlier reads about a seventh of the next lowest scene and leaves a wide
> empty band beneath the rest. **At full frame count it reads roughly double
> that**, lands *inside* the band the fitted numbers left empty, and sits within
> a factor of two of the next lowest capture rather than a factor of seven.
> Nothing about the capture changed; the later frames simply carry more texture
> than its first twelve do.
>
> So there is no calibrated empty middle to fall into, and a scene reading in it
> is not anomalous. What survives is the ordering and the recognisable shape —
> *a built interior of uniform paint or plaster is the case to worry about* —
> which is what §1 says to locate yourself by in the first place.

### `textureless_fraction` — meaningless without `empty_regions`

Area below a local-standard-deviation floor. **It counts area and is documented
as blind to whether that area was wanted**, which makes it uninterpretable alone.

| reading | what it was | what it meant |
| --- | --- | --- |
| ~0.60 | an object on a blown-out white studio sweep | harmless — the empty part is backdrop |
| ~0.60 | the same rig, a different object | harmless, same reason |
| ~0.80 | a room whose blank walls are the reconstruction target | **fatal** — the empty part is the subject |

Three readings within a few points of each other, two of them non-events and one
of them the hardest capture in the corpus. **Always pair this with `empty_regions` from
`SceneDescription`**, which answers three things the fraction cannot: where the
region is, whether it is wanted, and whether it is *clipped* or merely flat.

**Clipped versus flat is the part that changes the action**, and they have
opposite gradients. **`SceneTriage` 1.1.0 measures both ends** —
`highlight_clipped_fraction` and `shadow_clipped_fraction` as metrics, and
`series.photometric.highlight_clipped` / `shadow_clipped` per frame. Neither
carries a healthy band and neither should: a sky-heavy outdoor capture reads high
and is fine. Read them **against `textureless_fraction`**, which is the pairing
that separates the two cases:

**The rule is one line: neither number means anything until `empty_regions` says
which region it landed on.** The pairing below is a way of *asking that question*,
not a verdict, and every row ends in the same instruction.

| `textureless_fraction` | clipped fraction | ask | if the region is WANTED | if it is BACKDROP |
| --- | --- | --- | --- | --- |
| **≥ ~0.5** | **≥ ~0.3** | which region is which? | **burnt** — detail destroyed, no exposure or scale recovers it. Re-shoot or accept the loss | harmless. This is the studio-rig signature; plan as if the region were not there |
| **≥ ~0.5** | **≤ ~0.05** | which region is which? | **flat, not burnt** — the hardest recoverable case. Detail may survive at higher working resolution or with exposure normalisation at detection | harmless |
| **≤ ~0.4** | **≥ ~0.3** | is the clipped area one region or the frame edge? | a blown region *inside* a textured frame — a window, a sky, a specular highlight. Locate it | a lit backdrop occupying a minority of frame |
| **≤ ~0.4** | **≤ ~0.05** | nothing to ask | — | — |

The thresholds are soft and are there so the table can be *called* at all; an
earlier version gave the rows as bare "high" and "low" and four independent readers
reported it unusable or reported it returning the wrong row for their scene.

**What the number is.** Fraction of the frame at `L >= 250` in LAB, computed per
image; the metric is the **median over images**. It is an *area* measure with no
notion of where the subject is, and three consequences follow.

**1. A high reading is a capture-modality signature, not a difficulty one.**
Across the corpus the metric is sharply bimodal, and the split is not between hard
and easy scenes — it is between *captures made against a lit backdrop* and
*captures made in the world*. Every studio-rig scene sits an order of magnitude
above every field scene, with nothing in between, and the most-clipped scene in the
corpus is one of the easiest in it because the clipping is all backdrop. **So the
reading tells you how the scene was lit and shot; it does not tell you whether
anything you wanted was damaged.** That second question is `empty_regions` and
nothing else.

**2. Both numbers are whole-frame medians, so on a capture where a large backdrop
dominates every frame, neither says anything about the subject.** This is the
harder version of point 1 and it is not fixed by reading per frame. When the
backdrop is most of the picture, the subject's own exposure contributes too little
area to move either metric — so a scene can read "burnt" and have a perfectly
exposed subject, or read clean and have a blown highlight on the one surface that
mattered. On any capture with a dominant backdrop, treat both numbers as
describing the backdrop and get the subject reading from the description.

**3. The bimodal gap is a property of scene medians and does not hold per frame.**
Roughly one frame in seven across the corpus lands inside the gap the scene-level
readings leave empty, and they come from scenes on both sides of it. A capture
whose sky grows across the traverse, or whose backdrop enters frame partway
through, will straddle it on its own. **Never read a per-frame value against a
band computed from scene medians** — that applies to every series in this file,
and this is the metric where it is easiest to do by accident.

**That rule forbids something §3b asks you to do, and the two need reconciling
rather than obeying in sequence.** §3b tells you to read the per-pair motion series
when you ask the connectivity question — correctly, because the series is where the
mechanism is visible — while the only calibration on offer is a corpus band built
from per-capture medians. So there is no legal way to score a single fast pair
against anything, and a reader following both instructions literally is stuck.

The reconciliation is that **the series and the band answer different questions and
neither substitutes for the other.** Locate your *capture* in the band using the
capture-level number, which is what the band is denominated in. Then read the series
for **shape, not level** — is the capture homogeneous, or does it break into a fast
stretch and a slow one, and does the break land where the description says something
changed. A break is interpretable without any band at all, because it is internal to
the capture: the comparison is pair against pair, not pair against corpus. What you
must not do is take the fastest pair's number and look it up in the range table.

`fastest_pair` and `pair_p90_across` exist to make the capture-level half of that
honest, since `overall_magnitude` and `high_motion_tail` are both medians and a
minority of fast pairs cannot move either.

**4. It cannot locate subject blowout, and must not be used to try.** On a
studio-rig capture the per-frame reading ranks *how much backdrop is in view*,
which is close to uncorrelated with whether the subject is damaged. Measured
against a description that named the frames where a specular subject blew out:
the named frames read at or **below** the scene median while a frame verified at
full resolution as unblown read second-highest of the set. The ordering was not
weak, it was inverted. **Locating a blown subject is a looking task, not a
measuring one** — the metric bounds how much of the frame is at the ceiling and
says nothing about where.

**Where the pairing earns its place: three captures reading the same ~0.6 empty,
and three different problems.** Two were objects on a lit sweep, reading ~0.6
clipped alongside it — backdrop, harmless, plan as if it were not there. The
third was a room of blank painted walls reading essentially **zero** clipped at
0.8 empty: the emptiness is the subject, and it is flat rather than burnt, which
is precisely what makes it a hard-but-attackable scene instead of an impossible
one. Higher working resolution and exposure normalisation at detection are live
options on the third and pointless on the first two.

**Check that the branch you are on can execute that advice before you plan around
it.** Exposure normalisation at detection exists as `grayscale_clahe`, and
`grayscale_clahe` exists on the classical detector and on none of the learned ones.
So on a capture where §3b's connectivity question sends you to a learned detector
*and* the emptiness is flat-not-burnt on wanted surface, the two prescriptions
collide and the photometric one has nowhere to run. Several readers have hit this
and had no resolution to reach for.

There is no parameter that resolves it, and **the order of preference stated here
was measured backwards.** It used to say to raise the working resolution instead,
"which addresses the same shortfall a stage earlier". Measured on a flat-not-burnt
capture: four times the pixels *lowered* the learned detector's keypoint count
(1496 to 1396 per image), while exposure normalisation at the ORIGINAL resolution
took a classical detector from 696 to 4180 per image and its worst frame from 66
to 913. The two remedies are not interchangeable and the photometric one was
worth roughly two orders of magnitude more on the frame that mattered.

Raising the working resolution is also not a free move — it re-denominates every
pixel metric in the pipeline and invalidates comparison with everything already
built, which is why `SceneLoader`'s tuning notes now treat it as a fixed policy
rather than a knob.

So, in order: **take the classical detector for its exposure normalisation and
re-ask the connectivity question**, since §3b.1's fragmentation risk is itself
reduced by loading every frame; or accept the detector's reading on those regions
and carry the risk into the plan's watch line.

**Driven cold over the corpus, that first option is the one that keeps winning,
and on more captures than this row was written for.** Exposure normalisation at
detection improved three separate captures with large flat *wanted* regions —
a dim built interior, a confined indoor room and an outdoor site under hard sun
— on registration, point count and coverage together, and on one of them it was
the difference between two thirds of the frames and nearly all of them. The row
above frames it as the remedy for the hardest recoverable case; the evidence is
that it is worth trying wherever the wanted surface is flat and unclipped,
which is a wider set.

> **It does not work alone, and this is the part that is easy to miss.**
> Normalising raises the number of keypoints the detector *would* return, so on
> a capture where the cap was already binding the extra keypoints are simply
> clipped and the change reads as a non-event. `detection.md` §5 already says a
> cap that binds is not a measurement; the coupling is that **exposure
> normalisation and the keypoint cap have to move together.** Turn on
> normalisation, read `saturation`, and raise `max_keypoints` until it reaches
> zero before you read the count or judge the change.
>
> The same trap has now been measured on a *learned* detector, which is where it
> is least expected: a run left at the default cap reported saturation on three
> quarters of its frames, registered a sixth of the capture, and read as
> evidence against the detector. At a cap raised until saturation reached zero
> the same detector on the same capture registered **all of it**. The first run
> measured the cap.
What is *not* available is taking the classical detector for its CLAHE when the
graph is at risk — that trades a connectivity failure for a contrast one, and only
the first costs you frames.

`textureless_fraction` alone cannot tell those apart — the three readings differ
by four percentage points. The clipped fraction separates them completely, and
`empty_regions` says which side of the separation you are on.

**Shadow clipping is the rarer failure and reads differently.** It is zero on most
captures and never reaches the magnitudes the highlight fraction does — a few
percent at most. Do not read that as unimportant. Crushed shadow lands in window
reveals, under eaves, inside doorways and beneath overhangs, which are *on the
structure being reconstructed* rather than on a backdrop behind it. A highlight
fraction of 0.6 can be entirely harmless and a shadow fraction of 0.02 can destroy
the only detail on a facade's depth. That asymmetry is why the two are reported
separately and never summed.

**The distinction that matters, in physical terms:**

- **Clipped** — pixels at the very top or bottom of the range have no detail left
  to recover. No exposure normalisation, no CLAHE, no larger `max_edge` brings it
  back. On a lit-backdrop capture, a third to two-thirds of the frame is typically
  in this state and it is all backdrop.
- **Merely flat** — low contrast, but the histogram has headroom above and below.
  A blank painted wall can occupy most of the frame, carry no usable texture at
  the working resolution, and still have its whole upper range unused — which is
  exactly the case where normalising at detection or raising working resolution
  is worth spending on.

The cheap test is whether the emptiest region's histogram is pressed against a
limit or sitting in the middle of the range. The metrics answer that at whole-frame
scale; `empty_regions` answers it for the region you care about.

### `sharpness_ratio` — it does not measure focus

Minimum over median of per-frame Laplacian variance. **`blurred_frames` fires
below 0.4** — the declared healthy band is `[0.4, null]`, not the "about 0.5" an
earlier draft of this file claimed. The error was caught by readers noticing a
scene just above 0.4 that raised no diagnostic, which is the useful shape of that
mistake: *when a stated threshold and an observed diagnostic disagree, the
manifest is authoritative and the prose is the thing that is wrong.*

**This metric reports content, not focus, on every capture where it has fired.**
Five for five, each confirmed by opening the frames at full resolution. The
recurring signature is not blur at all:

| what the low frames were | why the metric read low |
| --- | --- |
| near-nadir views of a smooth roof plane, from an orbit that passes over the subject | the frame is filled by one flat surface, sharply imaged |
| the frames of an interior aimed at blank painted wall | there is nothing in them to have contrast |
| looking up into shade at smooth timber | low illumination and a low-frequency surface together |
| the frames of a studio-rig capture holding the most empty backdrop | not flat CONTENT but backdrop SHARE — the subject is sharp and simply occupies less of the frame |

Laplacian variance per frame cannot separate *this frame is blurred* from *this
frame is aimed at something flat and sharply in focus*. **Before dropping a frame
on this signal, open it.**

The fourth row is the one that generalises least obviously and is worth stating
directly: on a capture with a dead backdrop, this metric effectively **ranks
frames by how much backdrop is in them**. The lowest frame is then the one that
frames the subject most tightly, which is frequently the best frame in the set.
`textureless_per_image` on the same frames separates it — a low sharpness reading
that tracks a high textureless fraction is composition, not focus. The diagnostic's own suggested action leads with
exclusion; on this evidence that action is wrong more often than it is right.

**Read the per-frame array, not the ratio**, from `series.texture.sharpness`
indexed by `scene.images` — and read it against `series.texture.sharpness_median`,
the value the ratio divides by and then discards. Without the divisor a raw
variance is uninterpretable: the same number is a sharp frame in a high-contrast
capture and a soft one in a low-contrast capture.

**Watch the absolute level too.** Across the corpus `sharpness_median` spans
roughly eighteen-fold, and the ratio hides all of it — two captures can differ
fourfold on the ratio and twelvefold on the level, and it is the *level* that says
one of them is a fundamentally different kind of scene. A low level with a high
ratio is a uniformly low-contrast subject, evenly imaged, and is usually fine; a
low level with a low ratio is a capture in trouble.

### `repetitiveness` — narrow, and it measures the wrong axis

Self-similarity **within one image**, by template matching at corners: how well
does a patch correlate with somewhere else in *its own* frame.

**There are two numbers and they do different jobs.** The declared healthy band in
`module.yaml` fires nothing — it only changes what `sfm_describe_module` reports
and whether a reader calls a value in-band. The diagnostic trip in `adapter.py`
sits above it and is the only thing that raises `repetitive_texture`. Conflating
the two is how an earlier draft of this file miscounted which captures exceed
"the ceiling".

**The trip is a delivery mechanism, not a severity threshold.** What is worth
having is the diagnostic's *text* — that repetition produces confident WRONG
matches rather than missing ones, that no ratio-test threshold recovers from it,
and the capability query that follows. Firing is how that text reaches a reader,
and it is set above the band on purpose so it does not fire on most captures.

*A naming trap worth one line: `repetition_notes` is the name of the field in the
`report` parameter you SUBMIT, where it is a mapping of required questions. The
artifact publishes the answers as flat fields — `repetition_objects` and
`repetition_texture`. Both names are real and they live at different layers; a
reader looking for `repetition_notes.objects` on an artifact will not find it.*

**Moving either number cannot make this metric discriminate**, because the
observed range is narrow and has no gap anywhere in it. Lower the trip and the
text becomes boilerplate; raise it and it reaches almost nothing. The band was
recalibrated once already, and that bought ordering, not separation.

**It has been caught reading backwards, and the reason generalises.**
`matchTemplate` is not scale invariant. On a subject whose repeating elements
recede in perspective — a long facade of bays, a colonnade, a row of windows seen
obliquely — a near element does not correlate with a far one, and the metric reads
*low* on the most repetitive subject in the corpus. Conversely a **fronto-parallel
grid** (a wall of identical panels shot square-on) correlates strongly and reads
*high* for reasons that have nothing to do with how hard the matching is. **So the
reading is dominated by viewing geometry, not by ambiguity.**

**And the axis is wrong.** The hazard that breaks reconstructions is *between-image*
ambiguity — element *n* in one frame matching element *n+1* in the next. This
metric is within-image only, and its own `limitations.md` says it cannot see
between-image ambiguity at all. Nothing in the stack counts repeated objects at
any level. **Read `repetition_objects` from `SceneDescription` for that, and treat
this number as weak corroboration at best.**

#### The one use with evidence behind it, and its limits

Holding a classical detector's keypoints fixed and swapping a ratio-test matcher
for a jointly-reasoning one, the change in sparse point count is **loosely**
predicted by this metric: captures reading toward the top of the range tend to
gain, captures toward the bottom tend to lose, and the losses are large — a third
to a half of the model.

**Treat that as a direction, not a threshold, and understand why.** The
correlation is real and the mechanism is not: a metric that cannot see
between-image ambiguity has no business predicting a matcher that exists to
resolve it. What is almost certainly happening is a confound — on *architectural*
subjects, within-image self-similarity co-occurs with repeated objects, so the
number rides along with a hazard it cannot measure. It comes apart exactly where
that co-occurrence breaks:

- **A fronto-parallel repeating grid** reads at the very top of the range and the
  joint matcher *lost* — the geometry inflated the reading without the ambiguity
  being harder.
- **A vegetation-dominated capture** reads at the very bottom and the classical
  branch collapsed outright — see the detector entry below, which is a different
  failure altogether.

So: let it nudge you, never let it decide. Where it and `repetition_notes`
disagree, the description is describing the real hazard and this number is
describing the wallpaper.

### `combined_change` — quiet on adjacent pairs, not on full pairing

Illumination, colour and exposure drift. Measured with adjacent-frame pairing it
stays inside its healthy band on every capture, and the lighting diagnostic has
never fired there. **Read it against the pairing it was computed with.** Pairing
every frame with every other compares frames from opposite ends of the trajectory,
and on a studio orbit whose backdrop swings from bright to dark it reads well above
the band — enough to fire `illumination_unstable` — while the subject's own
lighting has not changed and the capture reconstructs fully. Under full pairing,
open the worst pair it names and check whether the change sits on the backdrop
before acting on it. Expect it to matter for real on outdoor sequences shot over
hours, which is not what has been measured.

### `overall_magnitude`, `variability`, `rotation_median_deg` — what the camera did

Between them these replace an asserted `capture_style` field, which was cut in
rubric v3 for exactly that reason.

- **`overall_magnitude` 0.032–0.309**, a tenfold spread and the honest measure of
  how far the camera moved between consecutive frames.
- **`variability`** is the more useful of the two for planning: it spikes when
  the capture is inhomogeneous. The two highest readings in the corpus belong to
  captures that visibly change character partway through — one of them a site
  walked in two passes whose halves barely overlap.
- **`rotation_median_deg` 2.6–29.5.** Report it; do not gate a detector on it.
  An earlier draft of this file said "above ~20°/pair expect wide-baseline
  matching to be under stress" and attributed that to `detection.md`, **which
  states no such number**. It was invented here. It also does not survive
  measurement: two captures reading identically on this metric take different
  branches, and another pair sitting a fraction of a degree apart also differ. No
  threshold on this axis reproduces any observed outcome. See §3
  the trap list in §3 ("a module run at its defaults") and §2's detector entry.

**None of these say the view graph will connect.** A set that splits in two is
visible in `variability` only weakly and in `overall` (the description) plainly.
When the description says the capture moved to a different part of the site,
choose `pairing: exhaustive` and watch `graph_components` — no measurement here
will tell you.

### `planar_dominance` and `pure_rotation_risk` — rare, and act immediately

GRIC homography-vs-fundamental preference, and the rotation discriminator
(`K₂⁻¹HK₁` is exactly a rotation under pure rotation).

Zero on thirteen of sixteen for `planar_dominance`, fourteen for
`pure_rotation_risk`. The exceptions, and they corroborate each other:

- **A near-planar masonry frontage walked past nearly parallel to it** — about a
  fifth of pairs prefer a plane, a tenth read rotation-only.
- **A wall of flat panels photographed nearly square-on** — the same fifth of
  pairs planar, and rotation-only at **zero**. The cleanest confirmation the pair
  works as designed: a genuinely flat subject, with the rotation discriminator
  correctly silent because the camera did translate.
- **An orbit around an object including one overhead pass across a flat roof
  plane** — a single pair of eleven on both. That is one frame's geometry, not the
  capture's; watch the seed, not a reason to change solver.

Both of those planar readings came from captures near the bottom of the
`rotation_median_deg` range — only a few degrees between adjacent frames. A
near-planar subject shot with small rotation is the
configuration that produces this, and it now has two independent instances.

`skills/plan/matching.md` §5 separates the two causes and prescribes
different fixes, and
**`SceneMotion` has already done that separation** — which is the one place a
measured number reaches a module choice directly. When the reading is the planar
branch — real baseline, flat structure — the response is to avoid a two-view
bootstrap: `SparseGlobalCOLMAP` solves the view graph globally, or keep the
incremental route and raise `init_min_angle_deg`.

**Read that against the per-pair series before acting on it**, because the
paragraph above is written for a capture that is planar *throughout* and the
readings observed have not been. When the flagged pairs share a single frame,
the table below sends you to "keep that frame out of seed candidacy" and the
incremental route survives — which is the opposite conclusion, reached from the
same fraction.

A single flagged pair out of eleven is a reason to watch the seed, not to switch
solver.

**"Watch the seed" needs to know which pair, and as of SceneMotion 1.1.0 you can.**
The fractions above are means of boolean series that are now shipped beside them:
`series.degeneracy.pair_planar` against `series.degeneracy.pair_index`, and
`pair_pure_rotation` against `rotation_pair_index`. Each index is a pair of
positions in `scene.images`. The artifact note names the flagged pairs in prose as
well, and it does so **even when no diagnostic fires** — which is every reading
measured so far, since 0.1818 is well under the 0.5 band.

The indices are separate per series because the subsets differ: a pair can admit a
homography fit and no rotation estimate, and an uncalibrated scene fills the planar
series and neither of the others. Do not zip one against the other's index.

Two things this makes possible that the fraction alone did not. **Check the seed
the estimator actually chose against the named pairs** — the pose artifact's note
says which pair it seeded on, and the flagged list says which pairs it must not
have. And **recompute the fraction over a subset**, to see whether the planarity is
spread through the capture or concentrated in a few views.

**What this does NOT make possible, corrected.** An earlier version of this
paragraph said to "keep the named pairs out of the seed rather than raising
`init_min_angle_deg` globally and hoping." **There is no parameter that does that.**
No pose module here takes a pair or frame exclusion; `init_min_angle_deg` is the
only seed lever and it is exactly the global one the sentence disparaged. The
executable version is a post-run check: run it, read the seed, confirm it is not a
flagged pair. On every capture measured, the scorer avoided them unprompted —
because it prefers parallax and a degenerate pair has little.

**Localised does not mean harmless, and this is a correction.** An earlier draft
of this paragraph said that if the flagged pairs cluster, "a global solver switch
is the wrong response to a local fact." That was written as a blanket rule, and a
blanket rule in either direction is wrong here. **What matters is not whether the
degeneracy is local but whether the incremental route still has a clean seed
available.**

An incremental solver needs exactly one well-conditioned pair to bootstrap from,
and then grows by resection. So the question the per-pair series answers is: *after
excluding every flagged pair, is there still a pair with real parallax, and is it
connected to the rest?*

| what the series shows | what it means for POSE |
| --- | --- |
| a single flagged pair, the rest clean and well connected | the seed is almost certainly safe. Stay incremental, then READ which pair it seeded on and confirm it was not the flagged one |
| flagged pairs sharing a common frame | that frame is the suspect. Same check after the run. If the seed did land there, `init_min_angle_deg` is the only lever and it is global -- which is where a global solver becomes the cheaper answer |
| flagged pairs spread across the capture, or covering the only wide-baseline pairs | there is no clean seed to find. **Use a solver that does not bootstrap from two views** |
| the reading is high enough to fire `planar_scene` | the same conclusion, reached without needing the series at all |

The last two rows are the case the earlier correction was reaching for and
overshot. A global solver is *available* on any of these rows; what it is not is
mandatory the moment a single pair reads non-zero, which is what a previous
wording implied and which collided with the single-pair guidance above.

**What it costs, measured.** Run on the same matches as the incremental route, on
captures reading up to a fifth of pairs planar, a global solver registered every
frame and returned roughly a third fewer points. **Do not read that as evidence
against it.** The failure a global solver prevents is a *confident wrong model* —
a mis-decomposed essential matrix gives you a full, plausible, well-reprojecting
cloud — so point count, registered count and reprojection error all look healthy
on exactly the outcome you were trying to avoid. **On a degeneracy question, more
points is not better and the usual metrics cannot referee.** Treat the global
solver as insurance with a known premium and an unmeasured payout, and say so in
the plan rather than implying the choice is settled either way.

**The "third" is a defaults artefact, not a property of the solver.** Measured
twice on different captures: the global solver defaults to `min_track_len: 3` and
the triangulators default to `2`, so their raw point counts are not the same
quantity. At a MATCHED track-length floor the ranking inverted on the two captures where
both were compared that way — the global solver returning 7.5% and 8% more
points. **That direction does not replicate.** A later capture compared the same
way at matched `min_track_len` measured the global solver returning 35% FEWER
points. So the matched comparison is the right comparison and its OUTCOME is
capture-dependent: what the defaults artefact establishes is that the raw counts
are not the same quantity, not which solver wins once they are. So the premium is not "a third less structure";
it is "no two-view structure", which is a different trade and one some downstream
consumers would take. Compare at matched `min_track_len` or do not compare counts
at all. (This is trap 10 of this same file — a module run at its defaults is not
the module the plan specified — applied to the comparison the paragraph above
invites.)

**A caution worth carrying:** a subject that *looks* planar need not read as
planar. A shallow-relief surface shot square-on scored 0.0, and the
full-resolution view showed why — the modelling projects far enough to cast its
own shadows. The metric was right and the intuition was wrong.

### The asserted group — what no measurement reaches

From `SceneDescription`. These have no numeric backing and are the only source
for what they cover:

| field | decides |
| --- | --- |
| `environment` | `setting: indoor \| outdoor` on `FeatureMatchLoFTR` and `FeatureMatchRoMa` — ScanNet against MegaDepth weights. **Nothing measured distinguishes these**, and the modules' tuning notes say the wrong one costs `inlier_ratio` outright. `studio` maps to neither; expect to try both. |
| `repetition_objects` | repeated *castings* — identical windows, dormers, street lamps. **Counted nowhere at any level.** |
| `material_hazards` / `hazard_position` | whether a reflection carries a legible image, and where the phantom lands |
| `dynamic_content` | movers. Both measuring modules list this as unimplemented. |
| `empty_regions` | wanted-vs-not and clipped-vs-flat, which `textureless_fraction` cannot give |
| `main_subject` / `subject_completeness` | whether coverage means surrounding an object or filling a volume |

---

## 3. The traps, in the order they have bitten

### 0. Read the bands, not the diagnostics

A diagnostic firing is sufficient evidence that something is wrong. **Its silence is
not evidence that nothing is.** Diagnostic thresholds and healthy bands are set
independently, and where they disagree the gap between them is a region where a
metric is out of band and nothing says so.

Measured across one stage on eight captures, three metrics sat outside their
published bands with **no diagnostic on any of them**: a conflict rate at 0.08
against a ≤0.05 ceiling on a warning that does not trip until 0.1; a split rate
above the ceiling published at the time; a median track length under its floor.
The first of those was the capture's real defect, and fixing it improved every
other reading — a reader working from diagnostics alone would have shipped it.

**Two of those three examples have since been retired, and how they were retired
is the more useful lesson.** The split-rate ceiling was raised once it was measured
being breached routinely with nothing wrong, and the median-track-length metric was
dropped once it was found to carry no information its neighbours did not. So do not
read the numbers in this paragraph as current bands — **read the module's manifest
for that, always.** A band quoted in a guide is a snapshot; the manifest is the
contract, and when the two disagree the manifest wins.

So the order is: **read every published metric against its own band first, and
treat diagnostics as a second pass that catches what you did not think to check.**
A band with no diagnostic behind it is the common case, not an anomaly.

Two corollaries worth stating, because both have cost runs:

- **A band can be wrong, or unreachable, and the metric's own text is the
  authority over the band.** Several here are documented as inapplicable under the
  pairing this guide mandates, or unreachable given the detector in use. When the
  gloss and the band disagree, the gloss wins — and say so in the plan rather than
  tuning against a number that cannot move.
- **A diagnostic's suggested actions can name parameters the module in use does not
  have.** Check the action against the schema before spending a run on it.


1. **A textureless reading is meaningless alone.** 0.5954, 0.5981 and 0.8013 —
   two non-events and one fatal case. Read `empty_regions`.
2. **`blurred_frames` fires on flat content, not blur.** Five for five. Open the
   frame before dropping it.
3. **`repetitiveness` can read LOWEST on the most repetitive subject.** It
   template-matches within one image and is not scale invariant, so a subject
   whose repeating elements recede in perspective — a long frontage of bays, a
   colonnade, a receding row of windows — fails to correlate with itself and reads
   near the bottom of the range. A fronto-parallel grid of identical panels reads
   near the top for the same geometric reason and not because it is harder.
   **The reading is dominated by viewing geometry, not by ambiguity.** Read
   `repetition_notes` from the description for the hazard itself.
4. **Repeated objects and repeated texture want opposite responses.** Context and
   scale separate a *pattern*; nothing separates two castings of one mould, and a
   more invariant descriptor makes the wrong match **more** confident. Reaching
   for a better detector against repeated objects is reaching the wrong way.
5. **A coherent reflection is a RANSAC inlier.** It triangulates confidently and
   reprojects beautifully, so `inlier_ratio` and bundle adjustment will both look
   healthy. A *diffuse* highlight is the opposite problem — drift and dropout, no
   phantom geometry — and hunting for phantom points after a diffuse reading
   wastes the effort.
6. **A detector-free matcher costs a tuning job two stages later.** No
   `feature_index` means the tracker merges by proximity, and `merge_eps_px` is
   specific to the matcher *and* the working resolution. Read `inconsistent_rate`
   and `split_rate` together. Before spending runs on the eps, read the matcher's
   own `cycle_split_rate`: it counts points already detected twice, which is a
   detector result no tracker tolerance reaches, so it is the floor the eps cannot
   get under.
7. **`heavy_downscale` bites hardest where texture is already thin.** On a capture
   whose wanted surfaces carry only faint, fine-grained signal — a built interior
   of plain painted walls is the type case — an aggressive downscale destroys the
   only thing there was to detect, and no detector parameter recovers it. There
   the first move is not a detector but a larger working resolution — which means
   building a NEW
   scene, since a scene cannot be resized in place. The parameter depends on the
   loader's resize mode: `max_edge` under `resize: auto`, `target_resolution` under
   `resize: fixed` or `square`. Both names appear in this stack and they are two
   parameters for two modes, not two names for one knob. The scene producers are
   listed in the brief's `rebuild_scene`, separately from `menu` — `menu` is what
   consumes a scene, so the module that made it can never appear there, and readers
   have repeatedly concluded from that it did not exist.
8. **A capture can split into disconnected halves and no metric says so.**
   An outdoor site walked in two passes and a long frontage walked end to end have
   both done it. `pairing: exhaustive`, watch `graph_components`.
9. **Do not cut or dismiss a metric for over-firing until the pipeline has been
   run on the captures it fired on.** A displacement flag in this stack was
   removed on the grounds that it fired on every benchmark capture measured,
   "every one of which reconstructs" — an assumption, made because they were
   standard benchmarks, that nobody had checked. Run to a sparse model, the
   high-displacement captures do **not** fully reconstruct on a classical branch;
   they drop between a quarter and three quarters of their frames. The flag was
   reporting something real and was cut for a threshold complaint dressed as a
   validity one. **"It fires on everything" and "it is measuring nothing" are
   different claims, and only the second is a reason to remove a metric.**
10. **A module run at its defaults is not the module the plan specified, and the
   difference can invert your conclusion.** `FeatureMatchLightGlue` and
   `FeatureMatchNN` both default to `pairing: sequential`, which on a 12-image
   scene is 11 pairs. Every plan in §4 specifies `exhaustive`, which is 66. The
   first run of the swap experiment below passed no parameters and therefore
   measured sequential: the classical branch registered half the frames on two
   well-connected rig captures and appeared to collapse, and the write-up nearly
   recorded a texture band that does not exist. Re-run at the pairing the plans
   actually specify, **those two captures register in full, the phantom texture band
   disappears, and the ordering changes.** Pass the parameters your plan names; a
   default is a decision somebody else made.

   **What the re-run did *not* do is make fragmentation go away, and an earlier
   version of this trap said it did.** It read "every branch registers 12 of 12 on
   every scene", which is false against this repository's own evidence table: at
   exhaustive pairing the classical branch still drops between a quarter and three
   quarters of the frames on the fastest captures in the corpus. Taken literally the
   old sentence erased §3b — the finding this file calls its strongest signal, and
   the finding every detector choice downstream of it rests on. It was caught by a
   reader who noticed the contradiction and correctly downgraded their confidence in
   §3b as a result; two others cited the sentence as authority. **A correction that
   overshoots is worse than the error it corrects**, because it arrives with the
   credibility of a retraction. State what the re-run changed, not what it rescued.

---

## 3b. What the branch comparison established

Everything else in this file is a reading. This is a measurement: fourteen
captures run through three detector+matcher branches to a sparse model, everything
downstream held identical and all matchers at `pairing: exhaustive`. It is the
first swap in this repository carried through and compared —
`judge/swap_or_build.md` was written admitting none existed. The per-capture
numbers are in [`skills/evidence/`](../evidence/EVIDENCE.md); what follows is what
generalises.

### 1. The failure that actually costs you frames is view-graph fragmentation

Four of the fourteen registered **less than the full set** under a classical
detector and ratio-test matcher — as low as a quarter of it. The mechanism is not
keypoint scarcity. On every one of those captures the detector fired abundantly
and spread well; what failed was that **too few image PAIRS survived verification
to hold the graph together.** Below roughly half the possible pairs, registration
starts dropping frames; above it, every capture measured completed.

> **That pair-fraction rule has since failed in both directions and should not be
> used as stated.** It is a fraction of ALL pairs, which is quadratic in frame
> count, so it does not mean the same thing on a capture larger than the twelve
> it was fitted on. Measured on full captures: one completed every frame at 42.7%
> and another at 49.6%, both below the line; one dropped a third of its frames at
> 56.1%, above it. Read `min_image_degree` instead — it is per-image, so it is
> comparable across capture sizes, and it is what separates a graph that is
> connected from one that is robustly connected.

**A learned detector and matcher recovers exactly this**, and it does so while
finding *fewer* keypoints — it recovers the marginal pairs rather than adding
points to the pairs that already worked. On all four fragmenting captures it
restored full or near-full registration.

> **But read what the mechanism actually says: the problem is GRAPH DENSITY, and
> the learned branch is not the only lever on it.** Frame count is the other one,
> and it is free. Every capture in this comparison was a twelve-frame head
> sample; pairs grow quadratically with frames, so the same capture loaded in
> full presents a far denser graph before any module is changed.
>
> Measured once, and only once so far: a capture that dropped a quarter of its
> frames on the classical branch at twelve frames registered **30 of 31 on the
> same classical branch** when every frame was loaded. One observation is not a
> law, and it is enough to change the order of operations — **load all the frames
> first, then ask whether the graph still fragments.** A branch swap made to fix
> a fragmentation that a full capture would not have had is a swap made for
> nothing, and this file has been recommending it since before anyone ran a full
> capture.

**So the question a detector choice should answer is not "is there enough
texture" but "will enough pairs survive".** Those come apart, and the first is
what step 2 measures.

### 2. Adjacent-frame motion ranks the risk. It does not gate it.

Sorted across the fourteen twelve-frame captures this was fitted on, the ones
that fragmented were the four highest readings with a clear gap below them, and
nothing overlapped. **That gap does not survive a bigger corpus at full frame
count, and this section has been rewritten around what does.**

#### What the refit found

Every corpus capture, at its full frame count, scored against the outcome on the
branch this rule is about — a classical detector and a ratio-test matcher — over
seven candidate statistics and two definitions of "fragmented". Separation
measured as the probability that a fragmenting capture reads higher than a
complete one:

| statistic | any frame lost | a quarter or more lost |
| --- | --- | --- |
| `high_motion_tail` ÷ √`n_images` | **0.92** | 0.90 |
| `overall_magnitude` ÷ √`n_images` | 0.89 | 0.90 |
| `high_motion_tail`, full capture | 0.91 | 0.88 |
| `overall_magnitude`, full capture | 0.86 | 0.83 |
| `overall_magnitude` at the twelve-frame head | **0.73** | **0.94** |

**Three things follow, and the first is the one that changes how you use this.**

**No statistic produced a clean gap** — not one of the seven, under either
definition. A capture that completes reads above a capture that fragments in
every column. So this is a **ranking heuristic, not a threshold**, and the
published ratio band has been withdrawn rather than restated: a number that
looked like a gate was a gate fitted to fourteen draws of a smaller quantity.

**Which reading is best depends on which failure you are asking about, and the
two disagree sharply.** For an outright collapse the twelve-frame head reading
is the best of the seven; for *any* frame loss it is the **worst**, because two
captures shed a tenth to a sixth of their frames while reading at the very
bottom of the motion range. Those losses have nothing to do with motion, and no
motion statistic can see them.

**Frame count belongs in the rule and is absent from it.** Dividing by the
square root of the frame count improves every motion statistic tested, on both
definitions. That is §3b.1's own mechanism showing up in the arithmetic — pairs
grow quadratically with frames, so the same adjacent-frame speed presents a
denser graph on a longer capture. A reading taken without the frame count beside
it is missing half the quantity.

#### So how to use it

> **Rank, then verify.** A high reading says *try the robust branch first and
> expect to check it*, not *the cheap branch will fail*. Carry both to a model
> where the cost allows — which is what §5 and `matching.md` already say is the
> only thing that settles a branch choice.

Read `high_motion_tail` beside `overall_magnitude` and divide by the square root
of the frame count when you compare two captures of different length. Locate
yourself by capture kind rather than by value, as §1 says.

#### Do not correct the reading with `stride`

An earlier version of this section said `overall_magnitude` falls as more frames
are loaded — neighbours get closer — and told you to re-read at
`stride ≈ n_images / 12` to recover the fitted spacing. **Both halves are
wrong, and the reason is worth keeping.**

The fitting protocol drew its twelve frames with `sampling: head` — a contiguous
*prefix*, not a coarser sample. A prefix keeps the original spacing and simply
stops early, so there is nothing to correct for. Had the protocol been
`sampling: uniform` the correction would have been right, and **the sampling
mode is the whole of the difference.**

Measured across the corpus, the full capture reads *higher* than its own
twelve-frame head on ten captures of sixteen and lower on six, so the stated
direction is wrong more often than right. And the probe itself does not survive
contact: the stride 1 / 2 / 3 sweep is non-monotonic on two thirds of the field
captures and falls outright on several, which by the rule in the next section
means it has returned no local evidence at all.

**If you want the published quantity, rebuild the scene at the protocol** —
`max_images: 12, sampling: head`, same working resolution — and read
`SceneMotion` on it at stride 1. That is the same quantity by construction
rather than by approximation, and it costs one loader run plus one motion run on
a twelve-image scene. Given the refit above, the reason to want it is narrow:
it is the best available reading for an outright collapse and the worst for
partial loss.

#### The stride sweep still has a job, and it is a different one

`stride` remains the cheap way to ask **whether non-adjacent pairs still share
content**, which is the quantity fragmentation actually depends on and which no
single-stride reading answers. Read the *direction*, not the level.

**Read the sweep as well as the point.** If motion keeps climbing with stride and
then collapses, flow has lost correspondence rather than found more of it, and
the collapse point is itself the answer: it is the separation beyond which pairs
share nothing.

**The mechanism is straightforward, which is why it is worth trusting more than
the correlation alone.** `overall_magnitude` is median apparent motion between
*adjacent* frames. High adjacent motion means the camera covered ground quickly,
so any two frames further apart in the capture share proportionally less of the
scene — and it is those non-adjacent pairs that hold an exhaustive view graph
together. A fast capture is a sparse graph.

**This corrects a claim that stood in this stack for months.** `SceneMotion`'s
manifest declines to put a healthy band on this metric, on the grounds that every
benchmark capture measured spanned the range and "all of which reconstruct". They
do not all reconstruct — that was inferred from the scenes being standard
benchmarks, not from running them. Under a classical detector and ratio-test
matcher the top of that range drops between a quarter and three quarters of the
frames. **The band was rejected because nobody had run the pipeline to check.**

**One correction this file owes its own headline metric.** §2 spends four numbered
points establishing that an area-weighted measure is diluted when a large part of
the frame is a backdrop that carries nothing — the reason `textureless_fraction`
reads alarmingly on a perfectly good studio capture. `overall_magnitude` is a
percentile over a dense flow field, computed over the whole frame, and is
area-weighted in exactly the same way. On a capture where a large fraction of the
frame is featureless, the flow there is not measured so much as filled in, and the
reported percentile is effectively a *lower* percentile of the region that actually
carries motion. The module exposes no mask or region parameter, so the corrected
number cannot be computed through it at all.

Two consequences, and neither of them overturns the reading:

- On a diluted capture, the tail statistic is the closer estimate of what the live
  region is doing than the headline percentile is, so read them together and let
  the tail carry more weight when the frame is mostly backdrop.
- **The corpus is mixed, and this is one reason the gap did not survive.** It
  contains both heavily-diluted rig captures and undiluted field captures, so a
  reference point drawn from it is not clean in either direction. That was
  tolerable while the evidence was a gap — a gap is robust to a bias that shifts
  a subset of readings the same way — and it is not tolerable now that the
  refit above shows there is no gap. A rig capture against a dead backdrop is
  being read low, which is a reason to weight the tail statistic and a reason
  not to treat any level as a boundary.

**Read it this way:**

- **Low** — adjacent frames overlap heavily, the graph will be dense, and the
  cheap CPU branch is very likely to complete. This is most benchmark object
  captures.
- **High** — expect the view graph to be sparse. The capture is not necessarily
  bad; it is *fast*, and it needs to be matched more carefully than a slow one.
  Plan for `pairing: exhaustive`, plan to spend on the matcher, and treat a
  classical ratio-test branch as the thing to verify rather than the default.

**What to do when it reads high, in order:**

1. **Budget for a learned detector and matcher — as the first thing to TRY, not
   as the decision.** On every fragmenting capture in the fourteen this was
   fitted on, that branch restored full or near-full registration, and it did so
   with *fewer* keypoints, by recovering marginal pairs rather than enriching
   good ones. **Driven cold on full captures it went two for five**: it rescued
   the two whose classical branch had collapsed outright and it *cost* two
   others most of their registration, where the classical detector with exposure
   normalisation beat it comfortably. So the reading buys an ordering, and the
   ordering is settled by carrying both to a model. See the boundary in
   [matching.md](matching.md), which is the same shape: reach for the robust
   branch where the cheap one has **failed**, not where it is **struggling**.
2. **Choose `pairing: exhaustive`.** A sequential window is what a sparse graph
   can least afford, and the module default is sequential.
3. **Raise `stride` on `SceneMotion` and read it again** — but read the *direction
   of the change*, not the level, and read it knowing the probe fails silently in
   one direction. At the default stride the module reports on roughly a sixth of the
   pairs an exhaustive matcher will build, and fragmentation lives in the rest, so
   this is the one cheap way to look at the pairs that matter. The reading it gives
   back means two opposite things depending on which way it moves:

   - **It goes UP.** Frames further apart really have moved further apart. This is a
     measurement, and it is the strongest evidence available before matching: it
     converts "this capture resembles the ones that fragmented" into "this capture's
     non-adjacent pairs share little, and here is by how much." Captures have been
     seen where four-apart pairs move as far as the fastest capture in a corpus moves
     between *adjacent* frames.
   - **It goes DOWN.** Real camera motion between frames four apart cannot be smaller
     than between adjacent ones. A lower reading is dense optical flow losing
     correspondence and returning small vectors — and **flow loses correspondence
     precisely when the frames stop overlapping, which is the thing you were trying
     to detect.** So a falling stride reading is not reassurance. It is the failure
     you were looking for, wearing the costume of its opposite, and a reader who
     takes the number at face value is talked out of the correct conclusion.

   Roughly a third of captures measured this way read *down*. Nothing in the artifact
   flags it: there is no validity or coverage field on the flow, and a collapsed
   reading can even make the low-baseline diagnostic fire, which reads as "the camera
   barely moved" on a pair that has no shared content at all. Sanity-check against
   the adjacent rotations — if the per-step rotations between frames *i* and *i+N*
   sum to far more than the stride-*N* pair reports, the wide read has collapsed.

   **A non-monotonic sweep is its own answer.** Reading strides 1, 2 and 3 and
   getting a value that falls then rises means the mechanism is not reproducing on
   this capture, and you are back to the borrowed correlation with no local evidence
   for it. That is worth knowing and worth saying in the plan; it is not a reason to
   change the decision, but it is a reason to hold it less firmly.

   **Do not locate a raised-stride reading in the corpus band.** Every band in §1 is
   at the default stride, and a wider-stride number is a different quantity on a
   different denominator — the fractions especially, which are over *fitted pairs*.
   A capture has been seen reading above the corpus maximum at stride 4 and
   comfortably mid-range at stride 1, which would place it in the fragmenting group
   or well outside it depending only on which artifact you happened to read.
4. **Watch `pairs_matched` against `pairs_proposed`, which the matcher publishes beside it** —
   that is the reading that separates a matcher which recovered the marginal pairs
   from one that did not. Below roughly half, registration starts dropping frames;
   above it, every capture measured completed.

   **`graph_components` and `largest_component_fraction` are not that reading**, and
   an earlier version of this step said they were. They are *terminal conditions* —
   they report a split after it has happened — and on a small ordered capture the
   consecutive chain almost always survives, so they read healthy either way.
   Measured across ten captures and fifty-nine matcher runs they read 1 and 1.0 on
   fifty-four, including on two configurations that differed by half the possible
   pairs, and including on a graph where two images hung off a single edge each.
   Watch them, because when they *do* fire the failure is real and nothing
   downstream repairs it — but do not read a component count of 1 as evidence the
   graph is sound.

   **`min_image_degree` is the margin.** An image at degree 1 is connected and one
   pair from being lost. On the capture above, the two degree-1 images were exactly
   the frames the description named as the join between the capture's two halves —
   which is the shape to expect, because a weak image is weak for a reason the
   description usually already states.
5. **If the graph does fragment, change the detector and matcher together**, not
   the tracker. A tracker cannot connect components that were never matched.

### 3. A learned detector is not a way to get more points

On ten of the fourteen the learned branch produced the **smallest** model of the
three — often by a factor of two or more. (This sentence used to continue "because
its keypoint budget is capped where a classical detector's is not." That explanation
is refuted: at caps neither detector binds on, the learned detector has returned
*more* keypoints than the classical one on several captures. The point-count result
stands; its cause is open. See `plan/detection.md`.) That is not an argument against it: on the
fragmenting captures it was the only branch that finished. **It is an argument
against reaching for it by default.** Buy it for connectivity and robustness, and
expect to pay for that in point count; if the graph was never in danger, the cheap
CPU branch usually returns a larger model.

### 4. The two questions are ordered, and connectivity comes first

The detector-and-matcher choice is not one decision, it is two, asked in this
order:

**First: will the view graph hold together?** Read adjacent-frame motion
(`overall_magnitude`, `high_motion_tail`), against the frame count. A capture
that covers ground quickly will produce a sparse graph, and a classical detector
with a ratio-test matcher may drop frames from it. **When this reads high, try
the learned detector AND matcher first, whatever the repetition looks like — and
carry the cheap branch alongside it, because this reading ranks the risk and
does not settle it (§3b.2).**

> **The exception this rule needs, and it is not about motion at all.** A block
> of frames shot at roughly ninety degrees of in-plane roll defeats a learned
> detector trained upright while a classical detector matches straight across
> the break, because its invariance is by construction. Nothing upstream sees
> it: the pixel dimensions are merely transposed and dense flow cannot fit
> anything across the break, so it reports only the frames it *could* match.
> The symptom is `min_image_degree` healthy for most frames and collapsing for
> a contiguous block. **On such a capture this rule is inverted and the learned
> branch is the fragile one.** [matching.md](matching.md) carries the full case
> and the remedy; it is named here because this is where the decision is made.

**Second, only if the graph is safe: will the matches be ambiguous?** Read
`repetition_notes` from the description, with `repetitiveness` as weak
corroboration. If the subject repeats, keep the classical detector and swap only
the matcher for a jointly-reasoning one — no re-detection needed.

**Otherwise take the cheap branch.** A classical detector and a ratio test
returns the largest model of the three on a well-conditioned capture, and costs
no GPU.

**Asked in that order, this reproduces the best-performing branch on thirteen of
the fourteen captures measured** — the miss being a marginal one where two branches
finished within a sixth of each other. Asked in the other order it fails on every
fast capture whose subject does not repeat, because the ambiguity question sends
you to the classical detector precisely where connectivity cannot afford it.

**This is also the answer to a conflict that had no tiebreak.** The family prose
says a repetitive subject wants a joint matcher; the repetition metric says the
cheap matcher is better below a certain reading. On a fast capture with a
repetitive subject, both are answering the wrong question — the graph fails before
ambiguity gets a chance to matter.

### 5. Swapping the MATCHER while keeping the detector is the cheap middle move

Holding a classical detector's keypoints fixed and replacing a ratio-test matcher
with a jointly-reasoning one needs **no re-detection** — the learned matcher
accepts classical descriptors and infers which weight set from the artifact's
provenance. Where the hazard is ambiguity rather than connectivity, this is the
move to try first, and it is far cheaper than re-running detection.

Its benefit is **conditional and the condition is not reliably measurable** — see
the `repetitiveness` entry in §2, which is the closest thing to a signal and is
measuring a different axis than the one that matters.

**And it is not unanimous. There is a counter-case in the evidence table, on the
configuration this move is prescribed for.** A well-connected rig capture with loud
object-level repetition — several castings of one mould, named by the description —
returned roughly 40% FEWER points under the joint matcher than under the ratio test,
with registration complete on both. That is the exact shape the rule says gains, and
it lost.

What makes it worth recording rather than dismissing is which source got it right.
The `repetitiveness` metric read near the bottom of the corpus on that capture and
so predicted no gain; the description read the repetition as severe and so predicted
one. **The metric was right and the description was wrong** — which inverts the
general finding elsewhere in this file that the description is the more trustworthy
of the two, and means neither can be leaned on here.

So read this move as: *cheap enough to try, reversible in one run, and not a thing
to assume.* The revert is `FeatureMatchNN` at exhaustive on the same keypoints,
which costs no re-detection either. If you are spending a run on the swap, spend the
run on the comparison rather than on the assumption — the two branches share their
detection artifact, so the A/B is nearly free and it is the only thing that settles
it. `[measured: 14, one counter-case]`

### What this does NOT establish

Fourteen captures, two dataset families, one parameter set, one downstream chain,
**no ground truth**. "Largest model" is not "best model": point count and median
triangulation angle disagree in direction on most captures, and a branch that
returns fewer points may be returning fewer wrong ones. Registration completeness
is the one axis here that is unambiguous — a frame that did not register is
simply absent — which is why the connectivity finding above is stated with more
confidence than the point-count ones. `[measured: 14]`

---

## 4. The plan that comes out

The output of step 3 is a **report, not a commitment, and not a lock**. It exists
to give the pipeline a defensible starting point, and every stage may be revised
by what the stage before it measures. The value of writing it down is knowing
**which observation would change your mind**, which is a thing you can only state
before the observation arrives.

**Two stages are provisional, and provisional does not mean blank.** The tracker
cannot be settled until the matcher has run, because detector-based and
detector-free matchers build tracks differently. Sparse cannot be settled until
tracking reports, because `long_track_fraction` and `track_survival_5` are
produced two stages after this plan is written.

Name a module anyway, in both. The conventional answer is right most of the time
— on sparse in particular — so "undecidable at plan time" is technically true and
less useful than a default plus its overturning condition. Write the line so it
**fills itself in**: the module, and the reading that would replace it.

Write it in this shape, family by family. Every claim names the reading it came
from, and where nothing supports a choice, **say that** rather than inventing a
reason.

```
SCENE           one line: what it is, from `overall`
WHAT IS HARD    the two or three things that will actually cost you

DETECTION       module + why, or "skipped" + why
MATCHING        module + pairing + why
TRACKING        provisional; module + what the matcher's output will decide
POSE            module + why, naming any degeneracy reading
SPARSE          provisional; module + the reading that would overturn it
OPTIMIZATION    module + why

WATCH           the metric to judge this scene on, which is often not the obvious one
ESCAPE          what to try if it fails, and the observation that would trigger it
UNSUPPORTED     what matters here that nothing in the brief backs, and what would
                settle it
```

**There is no `IGNORE` section.** An early version had one, for diagnostics that
fired and are non-events. It was cut: deciding which frames or warnings to discard
is the reconstruction's job, made against what the pipeline actually produces, and
pre-emptively dismissing a diagnostic at planning time is a decision taken too
early with less information. Where a reading is a non-event, say so in the line
that would otherwise act on it.

**Rules for the report.**

- **Every stage gets a line, even when the answer is the default.** "SIFT, because
  nothing here is hard" is a real answer and a cheap one; `matching.md` says so
  explicitly.
- **Name the number.** "texture_density seven times below the next lowest capture
  in this set" beats "low texture" — and name it as a RELATION, not as a value.
  A bare figure quoted against a published range is a lookup key: a reader whose
  capture sits on a range endpoint can identify it, which is the same leak as
  naming the scene. State where a reading sits relative to the others, not what
  it was.
- **`WATCH` is the most valuable line.** It is where a scene's real risk goes when
  no module choice addresses it. Where a capture orbits through a narrow arc
  against a shallow subject, an entirely ordinary plan can still need the watch
  line *judge on `median_triangulation_angle`, not `inlier_ratio`* — a tight
  baseline against little depth makes every other number look excellent.
- **`UNSUPPORTED` is where the honesty goes, and it is not optional.** Two of the
  first five plans written to this shape needed a second `WATCH` for a hazard no
  metric reaches -- a person walking through a background frame, crushed shadow
  where the depth discontinuities should be. Those belong here. So does a choice
  made on structural argument with no reading behind it. **Say what would settle
  it**, because that is what turns the line into future work rather than a hedge.
- **Do not restate the metrics as prose.** The reader has them. Say what they mean
  together.
- **Say what is unsupported.** Several choices here rest on one scene or on
  structural argument alone, and the report is more useful when it admits which.

---

## 5. Where the recording protocol went

**The protocol for writing into this file — and into the stage files beside it —
lives in [`distill/SKILL.md`](../distill/SKILL.md) §9**, with the rest of the
rules for turning a session into context. The two rules a READER of this file
still needs are stated where they bite: §1 says what corpus every range is
scoped to, and `sfm_plan_brief`'s `in_planning_corpus` field says whether the
capture in front of you is a member — in which case locating your readings in
these ranges is recall, not confirmation (the full caution is in
[`evidence/EVIDENCE.md`](../evidence/EVIDENCE.md)).
