# Tuning — FeatureDetectionSIFT

Indexed by what you observe, not by parameter. Sourced claims carry a tag
resolved in [sources.md](sources.md). **Observed** sections come from real runs
and carry their scene context, because a DTU number need not transfer to ETH3D.

---

## `saturation` near 1.0

**Read it as:** every image is hitting `max_keypoints`. The cap is what limits
detection, not the image content — SIFT found more and OpenCV discarded the
weakest by contrast score [S1].

**Gradient:**

1. `max_keypoints` ×2. This is the whole answer when saturation is 1.0.
   *Expect:* keypoint count roughly doubles, runtime and descriptor memory scale
   linearly, `spatial_coverage` rises as detections reach flatter regions.
2. Repeat while saturation stays near 1.0 **and** downstream track survival is
   still the binding constraint.

**Stop when** saturation drops below ~0.5 — content, not the cap, is now the
limit, and further raising it does nothing.

**Do not** raise the cap to fix low counts when saturation is already low. That
is the contrast filter binding, not the cap; see the next section.

### Observed

> **L-0001 · Doubling from 1024 to 8192 on DTU scan1**
> **Run:** first real pilot, 2026-08-08 · **Seen in:** 1 run · **Confidence:** low
> **Context:** DTU scan1, 8 images, 1600×1200, calibrated, well-lit turntable object.
> **Observed:** 1024 → mean 1024/image, saturation 1.00, coverage 0.65.
> 8192 → mean 7672/image (min 4677), saturation 0.75, coverage 0.80.
> **Takeaway:** at 8192 the cap is no longer fully binding on this kind of scene,
> and coverage gained more than count did. The coverage move is the part that
> matters for geometry.
> **Untested:** whether the extra keypoints survive matching; no downstream
> module existed at the time of measurement.

---

## `keypoints_per_image` low while `saturation` is low

**Read it as:** SIFT is rejecting candidates before the cap applies. The image is
dim, flat, or soft.

**Gradient:**

1. `contrast_threshold` 0.04 → 0.02 → 0.01. This is the dominant knob here: it
   is the low-contrast rejection test, applied per octave layer [S1].
   *Expect:* counts rise substantially on dim scenes; below ~0.01 the added
   detections are noise and repeatability falls.
2. `grayscale_clahe: true` if the set has strong shadow/highlight variation.
   The point is not the extra keypoints in dark regions but that equalisation
   makes detection more *repeatable* across frames with different exposure.
3. `sigma` 1.6 → 1.0 if the inputs are soft or slightly out of focus. The default
   assumes the image already carries ~0.5 of blur [S1]; over-smoothing a soft
   image destroys the extrema.

**Check the scene first.** If `SceneLoader` reported `heavy_downscale`, the
keypoints were thrown away before SIFT ever ran — raise `max_edge` there rather
than loosening thresholds here. That is a pointer, not an ordering rule; loosen
here first if you prefer, but the scene fix is usually the larger effect.

---

## `keypoints_min` below 200 while the mean is healthy

**Read it as:** the set is uneven. One or a few frames are starved, and the mean
is hiding them.

**Why it matters more than the mean:** tracks chain through consecutive frames. A
single frame with 150 keypoints breaks every track passing through it, so the
worst frame bounds multi-view support for the whole sequence — not the average.

**Gradient:**

1. Look at *which* frame. The diagnostic names it. If it is motion-blurred or
   points at a blank wall, no parameter fixes it; drop the frame at the scene
   level instead.
2. `contrast_threshold` down, as above — helps the dim frames without hurting the
   good ones, since the good ones are cap-limited anyway.
3. `grayscale_clahe: true` if the starved frames are the dark ones specifically.

---

## `spatial_coverage` below 0.35

**Read it as:** detections are clustered. A thousand keypoints in one corner give
a degenerate two-view geometry no matter how many there are — the estimated
essential matrix is poorly conditioned when correspondences do not span the frame.

**Gradient:**

1. `contrast_threshold` down, to reach the flatter regions that are currently
   filtered out.
2. `max_keypoints` up, but only if `saturation` is high — otherwise the extra
   budget goes unused.

**If coverage stays low after both**, the uncovered regions are genuinely
textureless and no detector setting will populate them. That is a
[limitations](limitations.md#textureless-regions) case, not a tuning one.

---

## Parameters that are rarely the answer

- **`n_octave_layers`** — 3 is the value from the original paper's own
  evaluation [S1]. Raising it finds more scale-intermediate keypoints at roughly
  linear cost, but it is not the lever when counts are low.
- **`edge_threshold`** — note its sense is *opposite* to `contrast_threshold`:
  higher keeps **more** edge-like keypoints. It is a principal-curvature ratio
  limit [S1]. Raise it only when the scene's real structure is linear (girders,
  window frames) and you accept keypoints that localise poorly along the edge.
- **`root_sift`** — leave on. It is two vector operations and strictly better for
  L2 matching [S2]; there is no scenario in this pipeline where turning it off is
  correct.
