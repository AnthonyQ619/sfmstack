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
