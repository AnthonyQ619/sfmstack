# Limitations — SceneMotion

---

## Planar and rotational degeneracy are the same measurement

`planar_dominance` is a model-selection result: GRIC prefers a homography to a
fundamental matrix on some fraction of pairs [S3]. A homography wins in exactly
two situations, and **the flow field alone cannot distinguish them**:

- the scene is planar, and the camera translated;
- the scene is arbitrary, and the camera did not translate.

They look identical because both produce correspondences that a single 2D
projective map explains. That is not a defect of this implementation; it is a
property of two-view geometry.

**What separates them is intrinsics.** Under pure rotation the inter-image
homography is exactly `K₂ R K₁⁻¹`, so `K₂⁻¹ H K₁` is a rotation matrix. Viewing a
plane from two positions gives `K₂ (R + t nᵀ/d) K₁⁻¹` instead, and the rank-one
term is not orthogonal for any nonzero baseline. `pure_rotation_risk` is the
fraction of pairs where that conjugate is orthogonal within `rotation_only_tol`.

**The tolerance is a baseline-to-depth ratio in disguise.** Measured on synthetic
homographies [S4], the orthogonality residual grows very nearly linearly in
`|t| / depth`, at roughly 1.4 × the ratio:

```
|t|/depth   0.02    0.10    0.50
residual    0.028   0.142   0.748
```

So the default `rotation_only_tol = 0.15` calls a pair rotation-only when its
translation is under about 10% of scene depth. That is the number to move if the
default disagrees with captures you know: tighten toward 0.05 for a near-exact
match, loosen toward 0.3 only on a noisy or badly-calibrated scene where the
residual has a floor unrelated to the camera.

**The consequence, observed: the flag can fire on a pair with almost no
rotation.** On a rig capture whose orbit includes one overhead pass across a flat
roof plane, that pass's pair is flagged `pair_pure_rotation` while its
`pair_rotation_deg` reads a twentieth of a degree — essentially no turn — against
mid-set flow. Substantial apparent motion, no rotation, and the flag still fires. That looks like the metric contradicting
itself and it is not. `rotation_deg` comes from the essential matrix; the
discriminator tests the *homography*. With R near identity the conjugate
`K⁻¹HK` reduces to `I + t nᵀ/d`, which passes an orthogonality tolerance whenever
`|t|/depth` is small. A short-baseline translation across a near-constant-depth
surface is therefore indistinguishable from a pure rotation by this test, exactly
as the residual table above predicts.

**Read the flag as "no usable parallax here", not as "the camera turned in
place".** Both are terminal for that pair and the remedy is the same, so the flag
is still correct about what to do — it is only the *name* that is narrower than
the condition it detects. A reader holding only `sfm_plan_brief` cannot reconstruct
any of this, because the brief carries the metric and not this file; that is why
such a reading gets reported as a suspected defect rather than understood.

**The prognoses are opposite**, which is why the discrimination is worth the
intrinsics requirement. A plane is recoverable with a pose method that does not
decompose an essential matrix. A pure rotation is not recoverable at all.

**Both are reported per pair as well as summarised**, and on the readings
measured so far the per-pair view is the one that decides anything. Every
non-zero `planar_dominance` observed has been one or two pairs of eleven — well
under the 0.5 band, so no diagnostic fires, and a fraction of 0.18 alone does not
say whether to change solver or simply to keep two views out of the seed. Read
`degeneracy/pair_planar` against `degeneracy/pair_index`, and
`pair_pure_rotation` against `rotation_pair_index`; the artifact note names the
flagged pairs in prose too. The fractions are the means of exactly those arrays,
so a caller asking about a subset of the capture recomputes rather than re-runs.

**A local degeneracy tells you what the cheap fix is, not that the safe fix is
wrong.** Clustered pairs mean the rest of the set carries baseline, so a seed
exclusion is available and costs nothing to try. That is worth knowing and the
fraction cannot tell you it. It is *not* a reason to keep a two-view bootstrap: a
global solver is robust to a handful of degenerate pairs. **The question to ask is
whether a clean seed survives the exclusion**: one flagged pair with the rest
connected leaves the incremental route safe; flagged pairs spread across the
capture, or covering the only wide-baseline pairs, leave it nothing to bootstrap
from. Measured, the global solver returned roughly a third fewer points on
captures where the incremental route did not visibly fail — but read that as a
premium, not as evidence, because the failure it insures against is a confident
wrong model that every metric here would score as healthy.

---

## Pure rotation is terminal

**The failure signature:** `pure_rotation_risk` above ~0.1, with
`planar_dominance` at least as high (it must be — the rotation test only runs on
pairs where the homography already won).

**Why nothing recovers it.** Structure from motion recovers depth from parallax:
the same point seen from two positions projects to two rays that intersect
somewhere. Without translation there is one position, the rays are the same ray,
and there is no intersection to find. Every module downstream — matcher,
tracker, triangulator, bundle adjuster — is solving a problem whose answer does
not exist. They will not fail loudly; a matcher matches fine under rotation, and
a triangulator will emit points at arbitrary depths that reproject correctly.

**This is the one diagnostic in this module emitted at `error` severity**, and
the only useful actions are about the capture, not the pipeline:

- if only part of the capture is rotational, re-run `SceneLoader` over the
  translating subset;
- if all of it is, the dataset does not support reconstruction.

**Sensitivity is untested on real data.** The discriminator is verified
synthetically [S4] and has never fired above 0.09 on the ten benchmark scenes
[S5], none of which is rotational. Its specificity is therefore demonstrated and
its sensitivity is not.

---

## What needs intrinsics

Three cues are omitted, not defaulted, on an uncalibrated scene:

| Cue | Why it needs K |
| --- | --- |
| `rotation_median_deg` | there is no metric angle without a camera model |
| `large_rotation_risk` | derived from the above |
| `pure_rotation_risk` | the conjugation `K⁻¹ H K` is the entire test |

The `uncalibrated_scene` diagnostic fires and the metrics are reported as **null
rather than zero**, because "not measurable" and "no rotation" are opposite
conclusions and a zero would read as the second.

**Everything else still works.** Flow magnitudes are pixel measurements
normalised by the image diagonal, and `planar_dominance` is a model comparison in
pixel coordinates. None of them touch K.

**A note on which K.** Per-image intrinsics are used, scaled from the scene's
working resolution to the flow resolution. The essential matrix is fitted in
normalised coordinates rather than by passing one K to `findEssentialMat`,
because a pair may carry two different cameras and the single-K call would apply
the first to both.

---

## What the displacement thresholds did and did not show

`low_motion_thresh` (0.005) and `high_motion_thresh` (0.08) both came from the
predecessor [S1]. `large_motion_risk` was cut because it fired on every benchmark
capture measured, "all of which reconstruct".

> **That premise was false and the cut was a mistake in reasoning, if not in
> outcome.** Nobody had run a pipeline when it was written — the captures were
> assumed to reconstruct because they are standard benchmarks. Run to a sparse
> model, the highest-displacement captures do **not** fully reconstruct on a
> classical detector with a ratio-test matcher: they drop between a quarter and
> three quarters of their frames, and they are separated from the captures that
> complete by a clean gap. The flag was reporting something real.

**What it was actually seeing.** Displacement between *adjacent* frames is a
proxy for overlap between *non-adjacent* ones, and an exhaustive view graph is
built from those. A capture that covers ground quickly between neighbours shares
proportionally less between distant frames, so fewer pairs survive verification
and the graph fragments. **A fast capture is a sparse graph.** That is a real
mechanism and it is what the fraction was tracking, clumsily.

**Not restored, and the reasons are narrow.** `high_motion_tail` and
`overall_magnitude` carry the same measurement without a cut welded into them and
separate the fragmenting captures on their own; the `pair_p90` array lets any
consumer threshold it themselves; and a fraction fitted on this corpus would
encode this corpus. Read the raw values.

**The general lesson is worth more than the specific one:** *"it fires on
everything" and "it is measuring nothing" are different claims, and only the
second justifies removing a metric.* Do not cut a metric for over-firing until the
pipeline has been run on the captures it fired on.

**`low_baseline_risk` was kept** on the opposite evidence. It never fired, but no
capture in the corpus is a dense video-rate sequence — the benchmark families used
here have coarse native spacing, and `stride` cannot bring frames closer together
than the capture shot them. Its positive case is absent from the sample rather than failing to exist,
and it names the failure this module exists to catch. Deleting it would be
reasoning from "no evidence" to "no value".

**What it would take to settle it:** one video-like capture, where consecutive
frames genuinely are nearly identical. Until then treat a 0.00 reading as
uninformative rather than as reassurance.

**`overall_magnitude` also lost its healthy band**, from the same reasoning: it
measured 0.075–0.31 across the ten and any inherited band would have flagged nine
of them.

---

## What is not measured

- **Dynamic content.** The flow residual after fitting a global motion model
  reveals moving objects, which corrupt tracks silently and are invisible to
  every metric here. The residuals are computed for GRIC and thrown away; this is
  the cheapest unimplemented cue in the module.
- **Non-consecutive structure.** Pairs are `(i, i + stride)`. Whether the capture
  closes a loop is not asked, and loop closure changes which reconstruction
  strategy is appropriate.
- **Per-pair degeneracy, exposed.** `planar_dominance` is a fraction; *which*
  pairs were planar is computed and not written. The `motion/pair_*` extras have
  no `degeneracy/pair_*` counterpart.
