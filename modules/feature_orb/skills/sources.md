---
module: FeatureDetectionORB
module_version: 1.0.0
curated_at: 2026-08-07
---

# Sources

## ORB

**Rublee, Rabaud, Konolige, Bradski, "ORB: an efficient alternative to SIFT or
SURF", ICCV 2011.**

Two contributions: orientation for FAST corners (via the intensity centroid), and
a learned sampling pattern for BRIEF chosen to maximise variance and minimise
correlation between the binary tests. The paper reports roughly two orders of
magnitude speedup over SIFT; in this pipeline, on 1024px images, the observed
detection-time ratio is closer to one order.

Section 7.2 is worth reading before deciding ORB is failing: the paper is explicit
that the descriptor is designed for in-plane rotation and modest scale change, and
does not claim affine invariance.

## ANMS-SSC

**Bailo, Rameau, Joo, Park, Bogdan, Kweon, "Efficient adaptive non-maximal
suppression algorithms for homogeneous spatial keypoint distribution", Pattern
Recognition Letters 2018.**

Suppression via Square Covering. Binary-searches a covering radius such that
keeping one keypoint per radius-sized cell yields approximately the requested
count, then keeps the strongest per cell. O(n log n) rather than the O(n²) of
classical ANMS.

The closed-form bracket for the binary search (the `exp1`-`exp4` expressions in
the adapter) is from the paper's derivation, and is the part most likely to look
like line noise — it solves a quadratic relating covering radius to target count so
the search starts with tight bounds rather than an arbitrary range.

Why it matters here specifically: OpenCV's `nfeatures` truncation keeps the
highest-response corners, and FAST responds most strongly where texture is already
dense. The default selection therefore actively worsens clustering. Measured on
DTU: `spatial_coverage` 0.734 → 0.850 at identical keypoint count.

## Harris scoring

`cv2.ORB_HARRIS_SCORE` rather than `ORB_FAST_SCORE`. Slower and better-behaved for
ranking; since SSC's selection depends on that ranking being meaningful, the
cheaper FAST score would undermine the suppression.

## Predecessor code

`scene_agent/breadth_agent/src/sfmcore/features.py`, `FeatureDetectionORB`
(lines 245-385), with an `anms_ssc` helper.

Same algorithm and the same default `fast_threshold=20`, `edge_threshold=31`,
`WTA_K=2`. Differences:

- **Suppression is on by default here.** The predecessor's `set_nms` defaulted to
  `False`, so the out-of-the-box behaviour was the clustered one. Given the measured
  coverage difference, the default was backwards.
- **`detect_multiplier` is explicit.** The predecessor's `set_nms_allowed_points=3000`
  was an absolute detection budget independent of `max_keypoints`, so the two could
  be set inconsistently — a budget below the cap silently made suppression a no-op.
- **The cap is a real cap.** SSC lands within `ssc_tolerance` of the target and can
  overshoot; the excess is trimmed by response so `max_keypoints` means what it says.
