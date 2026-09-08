# Campaign: reference-pipeline-2026-09 — one pipeline, every corpus capture

**This is a raw evidence table. Cite it; do not plan from it.** Every row is
one capture driven through the same fixed pipeline at full frame count. The
reasoning built on these rows lives in [`health/ladder.md`](../health/ladder.md)
(the profile and what each rung means) and
[`health/bounce.md`](../health/bounce.md) (what a persistently weak rung
implies). A plan for a new capture cannot use a row from this table.

## What ran

```
FeatureDetectionSIFT
  -> FeatureMatchLightGlue   pairing: exhaustive
  -> FeatureTrackUnionFind
  -> PoseEssentialToPnP
  -> SparseTriangulation
  -> BundleAdjustmentGlobal
```

Every parameter at its module default except `pairing`, which is exhaustive so
the view graph is not a function of frame ordering. Every image of every
capture, at a 1024 px working resolution. **One recipe applied to every
capture**: a reference corpus has to be fixed, or a percentile computed
against it says which pipeline ran rather than how healthy a model is.

16 captures reconstructed.

## The health profile, per capture

`reg` = registered fraction. `cond` = median widest triangulation angle (deg).
`comp` = share of points seen in more than two views. `cov` = median
per-frame occupied fraction of an 8x8 grid. `err` = median reprojection
error among well-supported points (px). `y_obs` / `y_trk` = observation-
and track-yield. `pose` = median disagreement between the final relative
rotations and the two-view estimates (deg).

| capture | imgs | reg | cond | comp | cov | err | y_obs | y_trk | pose | points |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| DTU/scan1 | 49 | 1 | 13.4 | 0.36 | 0.59 | 0.395 | 0.816 | 0.894 | 0.17 | 5273 |
| DTU/scan10 | 49 | 0.9 | 11.6 | 0.32 | 0.38 | 0.34 | 0.496 | 0.605 | 0.39 | 1902 |
| DTU/scan15 | 49 | 1 | 12.3 | 0.29 | 0.61 | 0.446 | 0.785 | 0.872 | 0.21 | 3984 |
| DTU/scan23 | 49 | 1 | 12.7 | 0.33 | 0.62 | 0.387 | 0.812 | 0.89 | 0.42 | 5283 |
| DTU/scan33 | 49 | 1 | 20 | 0.41 | 0.42 | 0.18 | 0.767 | 0.846 | 0.21 | 3031 |
| DTU/scan4 | 49 | 1 | 12.9 | 0.33 | 0.56 | 0.395 | 0.824 | 0.899 | 0.21 | 4826 |
| DTU/scan9 | 49 | 1 | 13.1 | 0.26 | 0.58 | 0.445 | 0.748 | 0.849 | 0.17 | 4247 |
| ETH/courtyard | 38 | 1 | 8.8 | 0.41 | 0.87 | 0.196 | 0.817 | 0.853 | 0.18 | 11768 |
| ETH/delivery_area | 44 | 1 | 9.8 | 0.48 | 0.63 | 0.241 | 0.752 | 0.783 | 0.19 | 5856 |
| ETH/electro | 45 | 0.04 | 39.6 | 0 | 0.21 | — | 0.009 | 0.013 | 0.15 | 79 |
| ETH/facade | 50 | 0.88 | 6.8 | 0.39 | 0.73 | 0.202 | 0.475 | 0.494 | 0.07 | 7103 |
| ETH/kicker | 31 | 0.77 | 11.3 | 0.38 | 0.5 | 0.274 | 0.495 | 0.557 | 0.41 | 1852 |
| ETH/meadow | 15 | 0.13 | 42.7 | 0 | 0.12 | — | 0.032 | 0.038 | 43.49 | 72 |
| ETH/office | 26 | 0.08 | 9.5 | 0 | 0.45 | — | 0.109 | 0.15 | 0.06 | 168 |
| ETH/playground | 38 | 0.5 | 4.3 | 0.27 | 0.77 | 0.51 | 0.267 | 0.3 | 0.15 | 3677 |
| ETH/relief | 31 | 0.71 | 13.7 | 0.44 | 0.59 | 0.217 | 0.52 | 0.506 | 0.37 | 1746 |

## Ground truth, beside the internal readings

**Used once, to check whether the internal readings track true error.**
Ground truth can never be a rung: the profile has to work on captures
that have none, and every column above is computable without it. Both
benchmark families ship reference poses — DTU as per-position projection
matrices (extrinsics only; the intrinsics in use are the repository's own
calibration), ETH3D as COLMAP `images.txt`.

Error is the median over image PAIRS of the relative rotation and the
relative translation DIRECTION, both gauge-free. Absolute poses would need
an alignment whose residual is itself a free parameter.

| capture | GT rot (deg) | GT transl (deg) | pairs | pose rung (deg) |
| --- | --- | --- | --- | --- |
| DTU/scan1 | 0.572 | 0.825 | 1176 | 0.175 |
| DTU/scan10 | 0.53 | 0.867 | 946 | 0.394 |
| DTU/scan15 | 0.539 | 0.766 | 1176 | 0.209 |
| DTU/scan23 | 0.553 | 0.823 | 1176 | 0.415 |
| DTU/scan33 | 0.608 | 0.695 | 1176 | 0.213 |
| DTU/scan4 | 0.622 | 0.856 | 1176 | 0.206 |
| DTU/scan9 | 0.552 | 0.746 | 1176 | 0.169 |
| ETH/courtyard | 0.072 | 0.122 | 703 | 0.181 |
| ETH/delivery_area | 0.107 | 0.252 | 946 | 0.187 |
| ETH/electro | 0.203 | 0.249 | 1 | 0.148 |
| ETH/facade | 0.261 | 0.213 | 946 | 0.069 |
| ETH/kicker | 0.105 | 0.237 | 276 | 0.408 |
| ETH/meadow | 43.435 | 77.806 | 1 | 43.495 |
| ETH/office | 0.071 | 0.344 | 1 | 0.058 |
| ETH/playground | 0.137 | 0.327 | 171 | 0.15 |
| ETH/relief | 0.135 | 0.133 | 231 | 0.373 |

### What the ground truth actually established

**Not what it was computed for.** The intent was to check whether each
internal rung orders captures the way true pose error does. It cannot,
and the reason is worth more than the intended result.

Ground-truth error here is a median over the image PAIRS a model
registered. A model that registers two images has exactly one pair to
be wrong about; a complete model has hundreds, including every hard
one. So the measure is not comparable across models of differing
completeness — and the corpus contains that comparison in its sharpest
form:

| capture | registered | GT rotation error | pairs compared |
| --- | --- | --- | --- |
| ETH/electro | 0.04 | 0.2° | 1 |
| ETH/office | 0.08 | 0.07° | 1 |
| ETH/meadow | 0.13 | 43.43° | 1 |
| ETH/courtyard | 1 | 0.07° | 703 |
| ETH/delivery_area | 1 | 0.11° | 946 |
| DTU/scan1 | 1 | 0.57° | 1176 |

**Two of the three models that abandoned most of their capture score at least as well on ground truth as all 8 fully-registered reconstructions here.** Each kept two images, got the one surviving pair nearly right, and is rewarded for it by a measure that never asks what happened to the other forty.

That is the ladder's first rung — *registration is a precondition, not
a tiebreak; error improves as cameras drop out because a smaller model
is an easier one* — demonstrated against ground truth rather than
argued from internal metrics. It is the strongest evidence in this
corpus for why the profile is a VECTOR with registration first, and
why a single accuracy number is not a substitute for it.

**So the rank correlations between each rung and GT error are
confounded and are deliberately not reported as a validation.**
Computed anyway they are mostly weak and two run opposite to their
expected sign, which is what the confound predicts: the rungs that
most clearly separate a broken model from a good one are exactly the
ones the GT measure cannot see past.

**What would validate a rung**, and what Phase B is shaped to produce:
two models of the SAME capture at EQUAL registration, where the GT
comparison is legitimate and the rung either orders them the way truth
does or does not.

## What this campaign is for

The columns above are the reference distribution a new reconstruction's
health profile is scored against, generated into `reference_profile.yaml`
beside this file and read by the run-summary health digest. Every value is
an **observed reading over this corpus**, never a threshold: a capture below
the minimum here is outside the observed range, which is not the same as
failing, because the minimum is the smallest of N draws.
