# Tuning — SceneMotion

Sourced claims resolve in [sources.md](sources.md).

Before any section below: **check `stride` first.** Every motion score is a
statement about the pairs this module chose, and `stride` chooses them. A reading
taken at the wrong spacing is not a wrong measurement, it is a measurement of a
different question.

---

## `low_baseline_risk` above 0.35

**Read it as:** more than a third of pairs move less than `low_motion_thresh` of
the image diagonal. Rays from those two views are nearly parallel, so
triangulated depth is unconstrained however precise the correspondences are.

**Gradient:**

1. **Is the capture dense?** If it is video or a finely-sampled sequence, raise
   `stride` to the spacing the reconstruction will actually use and re-read.
   *Expect:* the score to fall sharply. If it does, the capture was never
   narrow-baseline and the first reading was about the frame rate.
   *This is the first move, not the last, and it costs one re-run.*
2. If the score stays high at a realistic stride, the capture genuinely lacks
   parallax. Expect high reprojection error concentrated at low triangulation
   angle, and expect bundle adjustment to be unable to fix it — the constraint is
   missing, not mis-weighted.
3. Consider a capability that infers structure from a learned prior instead of by
   ray intersection:
   `sfm_find_alternatives(produces='sparse_model/v1', not_consuming='poses/v1')`.
   A prior supplies the depth the geometry cannot.

**Do not** lower `low_motion_thresh` to make the score fall. It is a threshold on
a risk count, not on the measurement; moving it changes what is counted and
nothing about the scene.

**Calibration caveat:** on ten benchmark scenes this metric read 0.00 every time
[S5]. It has never fired on a scene measured here, so its sensitivity is untested
— see [limitations.md](limitations.md#what-the-displacement-thresholds-did-and-did-not-show).

---

## `high_motion_tail` large

**Read it as:** the median pair's p90 flow, as a fraction of the image diagonal.
How far the fastest tenth of the frame travels. There is no band on it and no
diagnostic keyed to it, and that is the finding rather than an omission — the
`large_motion_risk` fraction that used to sit here fired on all ten benchmark
scenes measured, at 0.82–1.00, and all ten reconstruct under a classical SIFT
pipeline [S5]. It was reporting its own threshold.

**So read it in pairs, never alone:**

1. **Against `rotation_median_deg`.** Displacement under small rotation is
   usually harmless: a rotation-invariant descriptor does not care how far a point
   moved across the frame, it cares how much the *view* changed. ETH3D facade sits
   at 0.118 tail with 3.1° median rotation and matches fine.
2. **Against itself, across the set.** `variability` is the spread of the
   underlying per-pair series. A large tail at low variability is a uniform
   wide-baseline capture — DTU's arc. A large tail at high variability means part
   of the capture moved much faster than the rest, which is the case worth acting
   on.
3. **Against the `motion/pair_p90` array.** It is written to the artifact, so
   "which pairs" is answerable without re-running flow, and any threshold you do
   want can be applied there rather than inherited from this module.

**When the concern is real** — a large tail *and* rotation past ~20°, as ETH3D
kicker (29.5°) and electro (23.3°) show — the problem is viewpoint change, not
displacement. Lower `stride` if the capture supports it; otherwise prefer a
detector-free matcher:
`sfm_find_alternatives(produces='pairwise_matches/v1', not_consuming='features/v1')`.

---

## `variability` above 0.035

**Read it as:** the interquartile range of per-pair motion is wide — one exposure
interval is not like another. This is the motion metric that *did* discriminate
across the benchmark set, running 0.029–0.208 [S5].

**Gradient:**

1. Read the extra `motion/pair_p75` array. It is the per-pair series, so "which
   part of the capture is uneven" is answerable without re-running flow.
2. High variability means no single pairing strategy is right everywhere in the
   set. If the unevenness is localised — a pause, a sprint, a change of subject —
   the honest fix is to split the scene, not to average over it.
3. Raise `max_pairs` if the sequence is long and its character changes partway
   through; 60 uniformly spaced pairs can average two regimes into a meaningless
   middle.

---

## `rotation_median_deg` large, or `large_rotation_risk` above 0.33

**Read it as:** typical inter-frame viewpoint rotation, from the essential matrix
fitted to flow correspondences. This is the angular cue, and unlike the
displacement ones it is a direct statement about how much the *view* changed.

**Gradient:**

1. Past roughly 20–30° a detector-based matcher loses correspondences to
   viewpoint change rather than to anything tunable. Both ETH3D kicker (29.5°) and
   electro (23.3°) sit here.
2. Lower `stride` if the capture supports it. Displacement and rotation both
   fall with it, and here it addresses the cause rather than the symptom.
3. Otherwise this is a detector-family question. Learned descriptors are more
   viewpoint-tolerant than hand-crafted ones; a detector-free matcher more so
   again.

**Null on an uncalibrated scene**, along with `large_rotation_risk` and
`pure_rotation_risk` — see
[limitations.md](limitations.md#what-needs-intrinsics).

---

## Reading a wide-stride run

Raising `stride` is the cheap way to look at the pairs an exhaustive matcher will
actually build — at the default the module reports on roughly a sixth of them, and
connectivity failures live in the rest. It is worth doing. It is also the one probe
in this module that **fails silently, and fails in the direction that reads as good
news.**

**Read the direction against the stride-1 run, never the level.**

| the wide-stride reading | what it means |
| --- | --- |
| **higher** than stride 1 | Real. Frames that far apart genuinely have moved further apart, and you have measured how little non-adjacent pairs share instead of inferring it. This is the strongest pre-matching evidence about connectivity there is. |
| **lower** than stride 1 | **The measurement failed.** Camera motion between frames *N* apart cannot be smaller than between adjacent frames. Dense flow returns small vectors when it cannot find correspondence, and it loses correspondence exactly when the frames stop overlapping — so the reading is evidence *of* the problem, dressed as evidence against it. |
| **non-monotonic** across strides 1, 2, 3 | The mechanism is not reproducing on this capture. Not a reason to change the decision; a reason to hold it less firmly and say so. |

Roughly a third of captures measured this way read down. Nothing in the artifact
flags it — there is no validity or confidence field on the flow — so the check is
yours to make: **compare against the rotations.** If the per-step rotations between
frames *i* and *i+N* sum to far more than the stride-*N* pair reports, the wide read
collapsed. A capture has been seen whose four adjacent steps summed to roughly 105°
while the stride-4 pair reported 12°.

The same collapse can fire `low_baseline` on a wide-stride run, which then reads as
"the camera barely moved" on a pair that has no shared content at all. That
diagnostic's suggested actions now say so.

**Never locate a wide-stride number in a published band.** Every band quoted for
this module's metrics is at the default stride, and a wide-stride run is a different
quantity over a different set of pairs — the fractions especially, which are over
*fitted* pairs, and a wide pair that fails to fit leaves the denominator entirely. A
capture has been seen reading above a corpus maximum at stride 4 and comfortably
mid-range at stride 1; taken against the band, the two artifacts place it in
opposite groups.

## The flow parameters move the headline number

`max_side` and `flow_step` change what `overall_magnitude` reports on the same
capture — raising the flow resolution has been measured to shift it by a sixth and
`rotation_median_deg` by several degrees. That is not instability; a percentile over
a denser, sharper field is a different statistic. But it means **a reading is only
comparable to a published band, or to another capture, at the settings that produced
them.** Note the settings whenever you quote the number, and do not sweep the flow
resolution and the corpus band in the same argument.

This bites hardest on the captures most likely to tempt you into raising it: the
tuning advice for a scene whose textured area is a small part of the frame is to
lower `flow_step`, and that is exactly the kind of capture whose motion reading is
already being asked to carry a detector decision.
