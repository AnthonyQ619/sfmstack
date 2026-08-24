---
name: scene_to_pipeline
description: How to read the step-2 scene analysis into an initial SfM pipeline. The measured ranges, what each number can and cannot tell you, and the shape of the plan that comes out.
status: accumulating — 16 scenes, 4 datasets. Every threshold here is an observation, not a law.
scenes: 16
datasets: [DTU, ETH3D, Tanks and Temples]
---

# Reading a scene into a pipeline

This file is the missing half of step 3. `skills/families/*.md` say *which member
of a stage to reach for* in prose — "when the scene is repetitive", "when the
detector fires on nothing". `SceneTriage`, `SceneMotion` and `SceneDescription`
produce numbers. **Nothing else in this repository translates between the two**,
and this file is where that translation is written down.

Measured against the family files: of the 29 metrics the three analysis modules
produce, exactly two are named anywhere in `skills/families/` —
`planar_dominance` and `pure_rotation_risk`, both in one paragraph of
`matching.md`. The families speak in adjectives; step 2 speaks in numbers. What
follows is the bridge, and it is empirical.

**A note on references.** `§N` always means a numbered section **of this file**,
listed at the top of each. A reference to another file always names it —
`matching.md §5`, `swap_or_build.md`, `modules/scene_triage/skills/limitations.md`.
Raw per-capture measurements are not kept here; they live in
[`skills/runs/INDEX.md`](runs/INDEX.md), and this file carries only what
generalises from them.

**Read this as evidence, not as rules.** Every band below is *the range observed
across N scenes*, and N is small. A number outside a range means "unlike the
scenes measured so far", which is a reason to look, not a verdict. Where a band
has been wrong, that is recorded here too, because a threshold that has already
failed once is the most useful kind.

---

## 1. What the numbers actually range over

**Sixteen captures across two benchmark families**, all at 12 images with
`sampling: head`: seven controlled-rig captures of a single object on a lit
backdrop, and nine field captures — building frontages, a courtyard, an interior
of blank walls, a shelved indoor room, and outdoor sites with vegetation. Working
resolution around 1024px on the long edge throughout.

**The ranges below are what has been seen, not what is possible**, and their
extremes are named by the KIND of capture that produced them rather than by scene
id — a plan for a new capture can use "a controlled rig against a lit backdrop"
and cannot use a name. Per-capture numbers and their scene ids are in
[`skills/runs/INDEX.md`](runs/INDEX.md) for traceability.

| metric | min | median | max | spread |
| --- | --- | --- | --- | --- |
| `combined_change` | 0.0325 tight-arc panel | 0.0696 | 0.1156 vegetated site | 3.6× |
| `texture_density` | 475 blank-wall interior | 3479 | 5618 rig, high texture | **12×** |
| `repetitiveness` | 0.6213 vegetated site | 0.7163 | 0.8092 flat-panel wall | 1.3× |
| `textureless_fraction` | 0.1278 vegetated site | 0.3865 | 0.8013 blank-wall interior | 6.3× |
| `sharpness_ratio` | 0.1629 blank-wall interior | 0.6280 | 0.9590 tight-arc panel | 5.9× |
| `sharpness_median` | 140 blank-wall interior | 1363 | 2564 vegetated site | **18×** |
| `highlight_clipped_fraction` | 0.0000 masonry courtyard | 0.0421 | 0.6837 rig on lit backdrop | **bimodal, see below** |
| `shadow_clipped_fraction` | 0.0000 vegetated site | 0.0000 | 0.0223 shelved interior | 11 of 16 at zero |
| `overall_magnitude` | 0.0319 tight-arc panel | 0.1193 | 0.3092 fast outdoor traverse | 9.7× |
| `high_motion_tail` | 0.0413 tight-arc panel | 0.1490 | 0.3618 shelved interior | 8.8× |
| `variability` | 0.0103 tight-arc panel | 0.0588 | 0.2077 shelved interior | 20× |
| `rotation_median_deg` | 2.60 masonry courtyard | 18.03 | 29.47 shelved interior | 11× |
| `large_rotation_risk` | 0.0000 vegetated site | 0.3636 | 0.8182 shelved interior | — |
| `planar_dominance` | 0.0000 | **0.0000** | 0.1818 planar frontage, flat-panel wall | 13 of 16 at zero |
| `pure_rotation_risk` | 0.0000 | **0.0000** | 0.0909 rig with overhead pass, planar frontage | 14 of 16 at zero |
| `low_baseline_risk` | 0.0000 | 0.0000 | **0.0000** | 16 of 16 at zero |

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
extremes at each end) rather than whole. Every scene measured here is 12 images,
so nothing has been truncated yet.

**That rule covers the ANALYSIS series described in this section, and nothing
else.** A pipeline artifact's stored arrays come back whole however large they are —
a detector's keypoint table is tens of thousands of rows and arrives as tens of
thousands of rows, megabytes of it. Readers have been surprised in both directions:
some expected a summary and got the raw array, one assumed the raw array was
unavailable and did not try. Whole is the useful behaviour and worth knowing about,
because it is what makes the content-masked coverage analysis in
`families/detection.md` §3 possible at all — but ask for one deliberately rather
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
- **One scene sits seven times below the next lowest**, and it is a room of blank
  painted walls — the case `detection.md` names: *"Neither, when the detector
  fires on nothing… a case for a detector-free matcher, which skips this stage
  entirely."* The shape to recognise is *a built interior whose surfaces are
  uniform paint or plaster*, not the number on its own.

**The gap between 475 and 1624 is empty**, so there is no calibration in the
middle. A scene landing at 900 is genuinely unknown and worth running both ways.

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

Laplacian variance per frame cannot separate *this frame is blurred* from *this
frame is aimed at something flat and sharply in focus*. **Before dropping a frame
on this signal, open it.** The diagnostic's own suggested action leads with
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

### `combined_change` — reliably quiet

Illumination, colour and exposure drift. 0.0325–0.1156 across everything, healthy
ceiling 0.12, and **it has never fired**. Benchmark captures are photometrically
stable. Expect it to matter on outdoor sequences shot over hours, which is not
what has been measured.

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

`skills/families/matching.md` §5 separates the two causes and prescribes
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

Two things this makes possible that the fraction alone did not. **Keep the named
pairs out of the seed** rather than raising `init_min_angle_deg` globally and
hoping. And **recompute the fraction over a subset**, to see whether the planarity
is spread through the capture or concentrated in a few views.

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
| a single flagged pair, the rest clean and well connected | the seed is safe. Exclude that pair, stay incremental, and say which pair you excluded |
| flagged pairs sharing a common frame | that frame is the problem, not the geometry. Exclude the frame from seed candidacy; incremental still works |
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

**A caution worth carrying:** a subject that *looks* planar need not read as
planar. A carved stone relief photographed head-on scored 0.0, and the
full-resolution view showed why — the figures project far enough to cast their
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
   and `split_rate` together.
7. **`heavy_downscale` bites hardest where texture is already thin.** Office at
   0.165 destroys the only signal its walls have. On that scene the first move is
   not a detector but a larger working resolution — which means building a NEW
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
`judgment/swap_or_build.md` was written admitting none existed. The per-capture
numbers are in [`skills/runs/INDEX.md`](runs/INDEX.md); what follows is what
generalises.

### 1. The failure that actually costs you frames is view-graph fragmentation

Four of the fourteen registered **less than the full set** under a classical
detector and ratio-test matcher — as low as a quarter of it. The mechanism is not
keypoint scarcity. On every one of those captures the detector fired abundantly
and spread well; what failed was that **too few image PAIRS survived verification
to hold the graph together.** Below roughly half the possible pairs, registration
starts dropping frames; above it, every capture measured completed.

**A learned detector and matcher recovers exactly this**, and it does so while
finding *fewer* keypoints — it recovers the marginal pairs rather than adding
points to the pairs that already worked. On all four fragmenting captures it
restored full or near-full registration.

**So the question a detector choice should answer is not "is there enough
texture" but "will enough pairs survive".** Those come apart, and the first is
what step 2 measures.

### 2. `overall_magnitude` predicts it, and this is the strongest signal in the file

Sorted across the fourteen, the captures that fragmented are **the four highest
readings, with a clear gap below them**. Nothing overlaps. Texture density,
textureless fraction, rotation and large-rotation risk all fail to separate the
two groups; this one separates them completely.

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
- **The corpus band itself is mixed.** It contains both heavily-diluted rig
  captures and undiluted field captures, so its median is not a clean reference
  point in either direction. What survives that is the *shape* of the evidence, not
  the level: the fragmenting captures were the highest readings with a clean gap
  below them, and a gap is robust to a bias that shifts a subset of readings the
  same way. Locate your capture by where it sits relative to that gap, and be aware
  that a rig capture against a dead backdrop is being read low.

**Read it this way:**

- **Low** — adjacent frames overlap heavily, the graph will be dense, and the
  cheap CPU branch is very likely to complete. This is most benchmark object
  captures.
- **High** — expect the view graph to be sparse. The capture is not necessarily
  bad; it is *fast*, and it needs to be matched more carefully than a slow one.
  Plan for `pairing: exhaustive`, plan to spend on the matcher, and treat a
  classical ratio-test branch as the thing to verify rather than the default.

**What to do when it reads high, in order:**

1. **Budget for a learned detector and matcher.** On every fragmenting capture
   measured, that branch restored full or near-full registration — and it did so
   with *fewer* keypoints, by recovering marginal pairs rather than enriching good
   ones.
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
4. **Watch `graph_components` and `largest_component_fraction`** at the matcher —
   the first stage outputs that see the problem rather than predict it.
5. **If the graph does fragment, change the detector and matcher together**, not
   the tracker. A tracker cannot connect components that were never matched.

### 3. A learned detector is not a way to get more points

On ten of the fourteen the learned branch produced the **smallest** model of the
three — often by a factor of two or more. (This sentence used to continue "because
its keypoint budget is capped where a classical detector's is not." That explanation
is refuted: at caps neither detector binds on, the learned detector has returned
*more* keypoints than the classical one on several captures. The point-count result
stands; its cause is open. See `families/detection.md`.) That is not an argument against it: on the
fragmenting captures it was the only branch that finished. **It is an argument
against reaching for it by default.** Buy it for connectivity and robustness, and
expect to pay for that in point count; if the graph was never in danger, the cheap
CPU branch usually returns a larger model.

### 4. The two questions are ordered, and connectivity comes first

The detector-and-matcher choice is not one decision, it is two, asked in this
order:

**First: will the view graph hold together?** Read adjacent-frame motion
(`overall_magnitude`, `high_motion_tail`). A capture that covers ground quickly
will produce a sparse graph, and a classical detector with a ratio-test matcher
will drop frames from it. **When this reads high, spend on a learned detector AND
matcher, whatever the repetition looks like.**

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
- **Name the number.** "texture_density 475, seven times below the next lowest
  scene" beats "low texture".
- **`WATCH` is the most valuable line.** It is where a scene's real risk goes when
  no module choice addresses it. A tight-arc capture of a wall relief had an
  entirely ordinary plan whose watch line was
  *judge on `median_triangulation_angle`, not `inlier_ratio`*,
  because a tight baseline against a shallow subject makes every other number
  look excellent.
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

## 5. Recording protocol

**This file is a staging area, and deliberately so.** Everything here is written
in one place now so it can be split later, and the split is already known:

| destination | content |
| --- | --- |
| `skills/families/*.md` | *when a given module is good* — distilled per stage, joining the structural axes already there |
| `skills/judgment/*.md` | family-based, and specifically **when to swap a module or build a new one** |
| this file | the metric-to-adjective translation, which belongs to no single family |

Until that split happens, add here. The same applies to `docs/import_lessons.md`
and to any other experiment write-up: dump first, organise once there is enough
to organise, and do not fragment an observation across files before its shape is
clear.

**Write the SCENARIO, not the scene.** This is the rule that decides whether an
entry is worth anything later. A plan for a capture nobody has seen cannot use
"scan15 gained 20%"; it can use "a capture whose subject repeats and whose graph
is not at risk gains from a joint matcher". Every claim here must be phrased so
that a reader can tell **whether their capture is the kind being described**,
without knowing any of ours.

| write this | not this |
| --- | --- |
| *a built interior whose blank walls are the subject* | *ETH3D office* |
| *a near-planar surface shot nearly square-on* | *facade and delivery_area* |
| *a capture that covers ground quickly between adjacent frames* | *the four high-`overall_magnitude` scenes* |
| *the highest readings you have seen, with a gap below them* | *above &lt;the cut point you happened to fit&gt;* |

### A corpus member cannot be a cold reading of itself

The de-naming above protects a reader planning a *new* capture. It does nothing for
the case that turns out to be common: **the capture in front of you is one of the
captures these bands were fitted on.**

When that happens, this file stops being guidance and becomes recall. Its range
table's extremes are, by construction, specific captures' own readings printed to
five significant figures — so a planner who "locates their reading in the observed
range" and finds it *is* the maximum has looked up their own number. Several
readings in this file have been recognised that way by readers who then said so.

Two things follow, and they pull in opposite directions.

**For the reader.** Before treating a band as independent evidence, check whether
your capture is in it. If your reading matches a quoted extreme to several digits,
it is yours. Say so in the plan rather than presenting the reading as confirmation —
a rule reproducing on its own training data is worth much less than the same rule
reproducing out of sample, and the difference is exactly the thing a plan should be
honest about.

**For whoever writes here.** The evidence records exist so a claim can be traced
back and re-run — that is their whole point, and this file links to them from three
places for exactly that reason. But those records are indexed by scene name and
carry downstream results, so **following the traceability link is itself the leak**:
a reader sent there to locate a threshold finds their own capture's registration
outcome on the same screen. That has happened, and the reader disclosed it rather
than pretending otherwise, which is the right behaviour and not a fix.

There is no clean way to have both. What is achievable: a brief that says plainly
when the capture it describes is already in the corpus, so a planner knows which
kind of reasoning they are doing before they start. Until that exists, treat
"unrecognised capture" as an assumption to check rather than a given.

**And note what this does *not* excuse.** A named capture in the prose is still the
wrong way to write a lesson, including where the name would let a reader detect
contamination — an evidence record is the place for names. The two problems have
different fixes and solving one with the other makes both worse.

**Thresholds are the same mistake in numeric form.** A cut point derived from N
captures is a property of those captures. **Do not print the number even as an
example of what not to write** — a reader in a hurry lifts it straight out of the
counter-example column and uses it as the threshold, which is exactly what
happened to an earlier version of the row above. State the *direction* and the *shape of
the evidence* (unanimous, a clean gap, one exception and why), and let the reader
locate their own reading in it. Where a number genuinely is load-bearing, name it
once and say what corpus produced it.

**Raw per-capture numbers belong in
[`skills/runs/INDEX.md`](runs/INDEX.md), not here.** Provenance matters and it
should be traceable — but it should be traceable from a place a planner is not
reading, so the reasoning in this file cannot quietly become a lookup table.

**What a new entry needs.** A claim without these is not usable later:

1. **The scenario** — what kind of capture this was, in terms someone could match
   against their own, plus the count so the sample is weighable
2. **The number**, not an adjective — and its direction, not just its value
3. **How it was checked** — measured end to end, seen at full resolution, or
   inferred. Say which; these are not interchangeable
4. **What it changed**, or explicitly that it changed nothing
5. **What the check could NOT have caught.** A comparison only settles a question
   whose failure mode shows up in the metrics collected. Say which failure modes
   would have been invisible to it

**Update the frontmatter `scenes:` count** when adding, and update §1's table when
a new reading moves a min or max. A range that has not moved in twenty scenes is
worth more than one asserted once.

**Contradictions stay.** When a reading disagrees with something written here, add
it beside the original rather than replacing it, and say which scene produced
each. Both `repetitiveness` failures in §2 are recorded that way, and they are the
most useful lines in the file.
