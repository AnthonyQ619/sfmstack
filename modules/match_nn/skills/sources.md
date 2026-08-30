---
module: FeatureMatchNN
module_version: 1.6.0
curated_at: 2026-08-07
---

# Sources

## The ratio test

**Lowe, "Distinctive Image Features from Scale-Invariant Keypoints", IJCV 2004,
section 7.1.**

The 0.8 default comes from figure 11 of that paper, measured on a 40000-keypoint
database: at 0.8 the test eliminates ~90% of false matches while discarding ~5%
of correct ones. Both numbers are worth remembering, because they set what tuning
this parameter can buy — the correct matches it costs you are already few, so
loosening it mostly buys false ones.

Lowe's framing is that the ratio is a proxy for whether a keypoint is
*distinctive*, not for whether the match is *correct*. That is exactly why it
fails on repeated structure: a window on a facade is a perfectly correct match
and completely indistinct.

## Mutual consistency

Not from Lowe; standard practice since. Its value is specific and narrow: the
ratio test is computed per query keypoint, so several keypoints in A can each
independently pick the same keypoint in B. Requiring agreement in both directions
makes the correspondence a partial bijection.

This matters more here than in a two-view pipeline, because many-to-one matches
are what fuse two distinct scene points into one track downstream. See the
tracker's `inconsistent_rate`.

## MAGSAC++

**Barath et al., "MAGSAC++, a fast, reliable and accurate robust estimator",
CVPR 2020.** Available in OpenCV as `USAC_MAGSAC`.

Chosen over plain RANSAC because it marginalises over the inlier threshold rather
than requiring one to be correct. `ransac_threshold` is therefore a softer
parameter here than the name implies — it sets a scale rather than a hard cut,
which is why the tuning advice is "raise it toward 4-6" rather than a precise
value.

Inherited from the predecessor, which also used `USAC_MAGSAC` with
`maxIters=10000`. Kept for continuity of results.

## Degeneracy detection

**Torr, Zisserman, Maybank, "Robust Detection of Degenerate Configurations while
Estimating the Fundamental Matrix", CVIU 1997** — the GRIC criterion, which the
predecessor implemented in `baseclass.evaluate_models`.

`planarity` here is a cruder thing: the ratio of homography inliers to
fundamental inliers on the same correspondences. GRIC is the principled version,
penalising each model by its parameter count and dimensionality, and would be a
better metric. The inlier ratio was chosen because it needs no free parameters and
no calibration of the penalty terms, and because it is comparable across scenes.

Worth revisiting if `planarity` ever proves to trigger on scenes that
reconstruct fine.

## Brute force rather than FLANN

The predecessor offered both (`FeatureMatchFlannPair`, `FeatureMatchBFPair`).
This module is the brute-force one: it computes every distance and returns the
true nearest neighbour.

That matters for what the ratio test *means*. Lowe's criterion compares the best
match to the true second best; if the search is approximate, both terms are
approximations and the filter's calibration — the 90%/5% figures above — no longer
strictly applies.

`FeatureMatchFLANN` is the approximate alternative and is the right choice once
descriptor counts make exhaustive search the bottleneck. Its `checks` parameter
controls how far the approximation goes, and it reports the agreement with exact
matching so the trade is measurable rather than assumed. See that module's
tuning file.

## Predecessor code

`scene_agent/breadth_agent/src/sfmcore/featurematching.py`, classes
`FeatureMatchBFPair` and `FeatureMatchFlannPair`; outlier rejection in
`baseclass.FeatureMatching.outlier_reject`.

Two behaviours were deliberately not carried over:

- **Sequential-only pairing.** Every matcher there looped
  `for scene in range(len(features) - 1)` and matched `(scene, scene + 1)`. The
  view graph is a parameter here.
- **`RANSAC_homography` as an input flag.** It asked the user to decide in
  advance whether the scene was planar. `planarity` measures it per pair after the
  fact, which is both easier and more accurate — the answer varies within a
  single scene.
