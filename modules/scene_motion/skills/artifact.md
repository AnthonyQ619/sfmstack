# Artifact — SceneMotion

Produces `scene_analysis/v1`, filling the `motion` and `degeneracy` groups.
`SceneTriage` fills `photometric`, `texture` and `metadata`. Every group of this
type is optional, which is what lets two producers cover it without a merge step.

---

## Files and arrays

```
motion.npz
  overall_magnitude    ()      float64  median over pairs of p75 flow / diagonal
  high_motion_tail     ()      float64  median over pairs of p90 flow / diagonal
  variability          ()      float64  IQR of the per-pair p75
  low_baseline_risk    ()      float64  fraction of pairs below low_motion_thresh
  large_motion_risk    ()      float64  fraction of pairs above high_motion_thresh
  rotation_median_deg  ()      float64  calibrated scenes only
  large_rotation_risk  ()      float64  calibrated scenes only
  pair_index           (P, 2)  int32    EXTRA -- which pairs were evaluated
  pair_p75             (P,)    float64  EXTRA -- per-pair series behind the median
  pair_p90             (P,)    float64  EXTRA
  pair_rotation_deg    (R,)    float64  EXTRA -- calibrated scenes only

degeneracy.npz
  planar_dominance     ()      float64  fraction of pairs where GRIC prefers H
  pure_rotation_risk   ()      float64  calibrated scenes only
```

`degeneracy.npz` is absent entirely when no pair admitted a model fit — a
scene too textureless or too static for a homography to be estimated at all.
Absent, not zero: zero would read as "no degeneracy detected", which is the
opposite of "the test could not run".

The `EXTRA` arrays are outside the type schema, legal under the
additive-extension rule, and listed in the manifest's `extras` block. `P` is the
pair count; `R` is the number of pairs whose essential matrix solved, which can
be smaller.

---

## Units

**All flow magnitudes are fractions of the image diagonal at the flow
resolution**, which is what makes them comparable across `max_side` settings and
across scenes of different size. To convert back: multiply by
`sqrt(h² + w²)` where `h, w` are the flow-resolution dimensions — 0.08 on a
1024×682 frame is roughly 98 pixels.

**Angles are degrees**, from `arccos((tr(R) − 1) / 2)` on the rotation recovered
from the essential matrix.

**`planar_dominance` and `pure_rotation_risk` are fractions of *fitted* pairs**,
not of all pairs. Pairs that produced too few correspondences are excluded and
counted in the `flow_fit_failed` diagnostic instead. A scene where 30 of 60 pairs
failed and all 30 survivors were planar reports 1.0.

---

## How the degeneracy tests work

Worth understanding, because the two numbers are the module's real contribution
and neither is a threshold on a magnitude.

**GRIC** [S3] scores each model by its residuals plus a penalty for the model's
dimension and parameter count:

```
GRIC = Σ min(e²/σ², λ₃(r − d))  +  ln(r)·d·n  +  ln(r·n)·k
       r = 4, λ₃ = 2, σ = ransac_threshold_px
       homography:  d = 2, k = 8
       fundamental: d = 3, k = 7
```

The penalty is the point. A fundamental matrix can fit everything a homography
can and more, so on residuals alone it never loses; charging it for its extra
dimension is what makes the comparison mean "which model is doing real work".
Residuals are symmetric transfer error for H and Sampson distance for F — both
geometric, so they are on the same scale.

**The rotation test** conjugates the homography back through the intrinsics and
asks whether the result is a rotation:

```
M = K₂⁻¹ H K₁,  normalised by |det M|^(1/3)
residual = ‖M Mᵀ − I‖_F
```

Zero under pure rotation, and growing at roughly 1.4 × the baseline-to-depth
ratio otherwise [S4]. See
[limitations.md](limitations.md#planar-and-rotational-degeneracy-are-the-same-measurement).

---

## Reading it beside the rest of the scene

```
SceneLoader   how much image there is
SceneTriage   what the images look like
SceneMotion   how the camera moved between them
```

A worked reading, DTU scan10 at 12 images, stride 1:

```
n_pairs 11   overall_magnitude 0.110   high_motion_tail 0.144   variability 0.029
low_baseline_risk 0.00   large_motion_risk 0.91
rotation_median_deg 16.4   large_rotation_risk 0.18
planar_dominance 0.00   pure_rotation_risk 0.00
```

Which reads as: eleven wide-baseline pairs at a very even spacing — variability
0.029 is the lowest of the ten benchmark scenes, which is what a robot arm on a
fixed arc produces. 16.4° of rotation per step is the DTU rig's own geometry, not
a problem. No degeneracy: the object has real depth and the camera really
translated. The `large_motion` info fires and is the inherited threshold rather
than a finding — see [tuning.md](tuning.md#large_motion_risk-above-045).

And the contrast, ETH3D facade at 12 images:

```
overall_magnitude 0.075   variability 0.104   rotation_median_deg 3.1
planar_dominance 0.18     pure_rotation_risk 0.09
```

Less motion, three times the unevenness, almost no rotation — a handheld walk
along a building rather than a rig. `planar_dominance` at 0.18 is the facade
being flat on a couple of pairs and is well under the 0.5 warn.
