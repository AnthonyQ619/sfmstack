# Limitations — FeatureDetectionSIFT

When to stop tuning and change capability. Escapes name a **capability query**,
never a module, so they stay valid as the module set changes.

---

## Repetitive structure

**Signature:** `spatial_coverage` and keypoint counts both look healthy, yet
downstream matching yields few inliers and tracks stay two-view. Scene traits
include `repetitive-texture`.

**Why no parameter helps:** SIFT describes a local patch. On a brick facade, a
tiled floor, a row of identical windows, many patches are genuinely near-identical,
so the descriptors are near-identical too. The ratio test — the standard defence —
is *designed* to reject exactly this, which means correct matches get discarded
alongside wrong ones. Detecting more keypoints produces more ambiguity, not less.

This is the failure mode that costs the most time, because every metric this
module reports looks fine. The evidence is always downstream.

**Escape:** a detector-free matcher, which reasons over image context rather than
isolated patches:

```
sfm_find_alternatives(produces="pairwise_matches/v1", not_consuming="features/v1")
```

**Expected trade:** those need a GPU and run orders of magnitude slower.

---

## Textureless regions

**Signature:** `poor_coverage` fires and stays fired after
`contrast_threshold` reaches 0.01.

**Why no parameter helps:** there are no extrema to find. Blank walls, clear sky,
still water, and smooth painted surfaces contain no scale-space structure, and
lowering the contrast filter past a point returns sensor noise, which is not
repeatable across frames by definition.

**Escape:** as above — dense or semi-dense matching, which propagates
correspondence from textured regions into flat ones rather than requiring each
point to be independently distinctive.

**Partial mitigation first:** if only *part* of the frame is textureless (sky
above a textured building), coverage will be capped near the textured fraction
and that is fine. Judge coverage against how much of the frame *could* carry
detections, not against 1.0.

---

## Strong illumination change across the set

**Signature:** counts and coverage are fine per image, but matching inlier yield
is low, and scene analysis reports high `illumination_change` or
`exposure_shift`.

**Why parameters only partly help:** SIFT's descriptor is normalised, so it is
robust to affine intensity change — but not to the *detector* firing on different
structures when contrast changes. Detections stop being repeatable across frames
before descriptors stop being comparable.

**Try first:** `grayscale_clahe: true`. This is the case it exists for, and it is
cheap.

**Escape if that is not enough:** a learned detector, whose repeatability under
photometric change is trained rather than assumed:

```
sfm_find_alternatives(produces="features/v1", excluding="FeatureDetectionSIFT")
```

---

## Very large image counts

**Signature:** memory pressure rather than a quality metric.

**Why:** descriptors are the cost. At 128 float32 per keypoint, 8192 keypoints ×
500 images is ~2 GB in the artifact alone, and matchers hold more than that.

**Mitigation before escaping:** lower `max_keypoints`, or reduce the image count
at the scene level with `sampling: uniform` — a well-spread subset almost always
beats a dense one at equal budget.

---

## Not a limitation: low counts on a downscaled scene

If `SceneLoader` reported `heavy_downscale`, low keypoint counts are the expected
consequence and belong upstream. Raise `max_edge` there before concluding SIFT is
unsuitable. Scale-space detection has less to work with at lower resolution; that
is arithmetic, not a shortcoming of the detector.

---

## Observed switches

*None yet. Populated by the distillation loop as real sessions hit these.*
