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

## The motion thresholds are inherited and untested

`low_motion_thresh` (0.005) and `high_motion_thresh` (0.08) come from the
predecessor [S1]. Across ten ETH3D and DTU scenes at 12 images each [S5]:

| metric | range over ten scenes | fired |
| --- | --- | --- |
| `low_baseline_risk` | 0.00 — 0.00 | never |
| `large_motion_risk` | 0.82 — 1.00 | always |
| `variability` | 0.029 — 0.208 | discriminates |
| `rotation_median_deg` | 2.6 — 29.5 | discriminates |

All ten scenes reconstruct. So the two displacement thresholds currently carry no
information on captures of that character, while the variability and angular cues
do.

**The likely reason** is that normalised displacement is a weak proxy for
matching difficulty. A rotation-invariant descriptor is indifferent to how far a
point travelled across the frame; what costs it correspondences is how much the
view changed, which is what `rotation_median_deg` measures directly. A p90 flow
of 0.08 diagonals is about 98 px on a 1024×682 frame, and 98 px of displacement
under 3° of rotation is nothing.

**The defaults have deliberately not been changed.** They are a faithful port,
and re-fitting them to ten scenes would replace one unvalidated number with
another. What has changed is that the `large_motion` diagnostic is emitted at
`info` rather than `warn`, and that `overall_magnitude` carries no healthy band —
a band that flags nine scenes in ten is worse than none.

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
