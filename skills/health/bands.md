# What a `healthy` band is, and what a firing one means

A band is a claim that outside this range something needs attention. Whether that is
true depends on what the metric measures, and **four kinds of metric answer to different
rules.** Reading a firing band without knowing its kind is how a capture comes to show
thirteen alarms on its best possible outcome.

Measured across every capture in every batch on disk: **ten bands fire on more than
seven readings in ten, and every one of them is at or below the base rate for a poor
delivery.** They are not cautious; they are carrying no information. Twenty-nine more
have never fired once. The evidence is in
[`evidence/band-calibration-2026-10.md`](../evidence/band-calibration-2026-10.md).

## The four kinds

| kind | what it measures | may it carry a band? |
|---|---|---|
| **input** | a property of the **capture** — texture, motion, reflections, exposure | Not as a *health* verdict. As a difficulty forecast, only if it discriminates |
| **explains** | exists to account for another reading, not to judge anything | **No.** A band turns an explanation into an accusation |
| **quality** | whether the produced artifact is good | Only if it discriminates — see below |
| **structural** | whether the artifact is **usable at all** | Yes. This is what bands are for |

**`input` has no healthy state, but it can have a difficult one.** A capture is
low-texture or it is not; the reading is how you plan for it, and
`plan/scene_to_pipeline.md` is where it is read. A band saying such a scene is
*unhealthy* is a category error. A band saying it is *likely to defeat this pipeline* is
not, and two earn their place: `dynamic_content` fires on 5 captures and 4 delivered
poorly (**80%**), `pure_rotation_risk` on 4 with 3 poor (**75%**), against a 40% base
rate. Both name a condition that genuinely breaks a reconstruction — movers corrupt
tracks, and no parallax leaves nothing to triangulate.

So the kind does not decide whether a band may exist; it decides **what a firing one
means**, and the test is the same for all four: does it discriminate? Measured across the
scene stage the answer ranges from 80% down to 0%, and the weak end is where the noise
is: `illumination_change` 31%, `large_rotation_risk` 17%, `subject_complete` and
`exposure_shift` 0% — each firing *more* often on a good delivery than a poor one. The
scene stage supplies **31% of all band firings in the batch** and most of that volume
comes from the bands at the bottom of that range.

**`explains` is the subtlest.** `subject_complete` says a thin point count on part of an
object is the *capture's* limit rather than the pipeline's. That is the reader's defence
against blaming the wrong stage. Its band fired on 32 readings and **not once on a poor
delivery** — precision zero, because the thing it reports is not a defect.

**`structural` is what a band is for**, and the well-behaved ones look alike: they fire
on **0.3% to 5% of readings**. Twenty-two bands already behave this way, including
`SparseVerification.supported_second_size` at 4.5% over 1080 readings. A rare alarm that
means something is the target shape.

## Calibrating a `quality` band: against the population, not the ideal

The ten noisy bands share one cause. They were set to describe what a good model *ought*
to look like, and this pipeline sits outside them:

| band | set at | observed p10 | median | p90 |
|---|---|---|---|---|
| `mean_track_length` | ≥ 3.0 | 2.00 | 2.31 | **2.92** |
| `two_view_fraction` | ≤ 0.6 | 0.56 | **0.75** | 1.00 |

**No cloud this pipeline produces reaches a mean track length of three.** That is a real
property worth knowing and a useless per-capture alarm, because it is true of every
capture. The aspiration belongs in `tuning.md` prose, where it can be explained; the band
belongs where it separates this capture from its neighbours.

So: **a `quality` band is calibrated on the distribution actually observed, and it earns
its place by discriminating.** Recalibrated against ground truth, the same two readings go
from 41% and 44% precision to **83%** at thresholds of 2.22 and 0.843.

**Two cautions on that fitting.** Those thresholds were fitted on seventeen captures, and
a band fitted on the set it is scored against is the error that put
`camera_spread_ratio` into this tree — validated on models known to be wrong, deployed on
models that had survived every check, and reading rho +0.05 against the outcome. A
recalibrated threshold is a proposal until a batch it was not fitted on agrees with it.

And **check whether a second band already carries the reading.** At their recalibrated
thresholds `mean_track_length` and `two_view_fraction` fire on the **same six captures,
six of six**, correlation −0.90. They are one signal written twice.

## What this says per family

Metrics by kind, with how many carry a band today:

| family | input | explains | quality | structural |
|---|---|---|---|---|
| scene | **32 (15 banded)** | 4 (1) | 0 | 0 |
| sparse | 0 | 5 (2) | 70 (49) | 19 (16) |
| match | 0 | 0 | 55 (29) | 24 (18) |
| track | 0 | 6 (0) | 35 (24) | 3 (3) |
| bundle | 0 | 1 (0) | 29 (25) | 8 (8) |
| pose | 0 | 1 (0) | 28 (10) | 9 (8) |
| dense | 0 | 4 (0) | 18 (9) | 0 |
| feature | 0 | 0 | 15 (8) | 4 (4) |
| **total** | **32 (15)** | 21 (3) | 250 (154) | 67 (57) |

Three things to read off it:

**The `scene` family is entirely `input` and fifteen of its metrics carry bands.** That is
the largest single block to audit, not a block to delete: scored against the outcome they
run from 80% precision down to 0%. The two at the top are worth keeping and most of the
rest are firing at the base rate. The readings stay either way — the planning files that
consume them read the value, not the band.

**`structural` is 57 banded of 67**, which is the ratio to expect: these are the readings
whose violation means unusable, and they are the ones that should alarm.

**`dense` has no `structural` metric at all.** Twenty-two metrics, none of which reports
whether the cloud is usable, in the family whose deliverable is the cloud. That is the
gap to fill rather than a band to retune — and it matches the promoted capture whose
dense failure is pure coverage, in
[`evidence/dense-saturated-2026-10.md`](../evidence/dense-saturated-2026-10.md).

## Before you add or keep a band

1. Name the kind. `explains` does not take a band at all; `input` takes one only as a
   difficulty forecast that demonstrably discriminates, never as a health verdict.
2. For `quality` and `structural`, state the fire rate over the captures on disk. Above
   roughly 7 in 10 it is noise whatever its threshold says; **0 over a decent sample is
   the same failure inverted** — a threshold outside the range the quantity reaches.
3. State the sample. Under about eight observations no rate is readable, and saying so is
   the honest answer. Forty-one bands are in that position today.
4. Check no existing band already fires on the same captures.
5. A band and the reading are separable. The usual fix for a noisy band is to remove **the
   band** and keep the metric.
