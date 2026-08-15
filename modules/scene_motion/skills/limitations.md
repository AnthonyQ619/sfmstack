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

**The prognoses are opposite**, which is why the discrimination is worth the
intrinsics requirement. A plane is recoverable with a pose method that does not
decompose an essential matrix. A pure rotation is not recoverable at all.

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
predecessor [S1]. Across ten ETH3D and DTU scenes at 12 images each, **all of
which reconstruct** under a classical SIFT pipeline [S5]:

| metric | range over ten scenes | verdict |
| --- | --- | --- |
| `large_motion_risk` | 0.82 — 1.00 | fired on every scene → **cut** |
| `low_baseline_risk` | 0.00 — 0.00 | fired on none → **kept, untested** |
| `variability` | 0.029 — 0.208 | discriminates → kept |
| `rotation_median_deg` | 2.6 — 29.5 | discriminates → kept |

**The two zero-information results are not the same result**, and that is why
only one of them was removed.

**`large_motion_risk` was cut** for two reasons that compound. Structurally it
was `mean(pair_p90 > threshold)` — `high_motion_tail` with a cut point welded
into it — and the per-pair array it aggregates is written to the artifact anyway,
so nothing is lost by removing the fraction. Empirically it fired on ten scenes
out of ten that all succeeded, which is a metric reporting its own threshold.
Recalibrating was not an option: a threshold cannot be fitted on data where every
case is negative. You would only learn where these scenes sit, not where failure
begins.

**The likely reason it fails** is that normalised displacement is a weak proxy
for matching difficulty. A rotation-invariant descriptor is indifferent to how
far a point travelled across the frame; what costs it correspondences is how much
the *view* changed, which `rotation_median_deg` measures directly. A p90 flow of
0.08 diagonals is about 98 px on a 1024×682 frame, and 98 px of displacement
under 3° of rotation is nothing.

**`low_baseline_risk` was kept** on the opposite evidence. It never fired, but
none of the ten scenes is a dense capture: ETH3D and DTU both have coarse native
spacing, and `stride` cannot bring frames closer together than the dataset shot
them. Its positive case is absent from the sample rather than failing to exist,
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
