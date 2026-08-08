---
module: FeatureDetectionORB
module_version: 1.0.0
upstream: OpenCV ORB + ANMS-SSC (Bailo et al. 2018)
curated_at: 2026-08-07
sources: 3
---

Oriented FAST corners with rotated BRIEF binary descriptors. Roughly an order of
magnitude faster than SIFT, 32-byte descriptors matched by Hamming distance, and
patent-free.

**Use when** throughput matters more than robustness — long sequences, a first
look at a large capture, or any loop you will run many times.

**Prefer SIFT when** the capture has wide baselines, large scale change, or low
texture. ORB's descriptor is genuinely weaker there and it shows up as shorter
tracks rather than as obviously bad matches. See [limitations](limitations.md).

**The thing that makes ORB usable: `suppression: ssc`.** ORB's real problem is not
the descriptor, it is spatial distribution. FAST fires in dense clusters on
high-contrast texture, and OpenCV's `nfeatures` cap keeps the *highest-response*
corners — which are concentrated exactly where texture is already strongest, so
the default selection makes clustering worse. ANMS-SSC selects a spatially even
subset at the same count.

Measured on DTU scan1, 8 contiguous images at 1024px, 4096 keypoints:

| suppression | keypoints/image | spatial_coverage |
|---|---:|---:|
| `none` | 4096 | 0.734 |
| `ssc` | 4096 | 0.850 |

Same count, 16% more of the frame covered, a few milliseconds per image.

**Descriptors are binary**, and the artifact carries a `binary` flag. Matchers
read it to select Hamming distance automatically. A uint8 descriptor matched under
L2 produces confident garbage, which is why the flag exists rather than a
convention.

**Cheapest thing that usually works:** defaults (`ssc`, 4096, `detect_multiplier: 4`).
Then read `spatial_coverage`, not the keypoint count — the count is capped and
tells you almost nothing.

**Reading the output:** [artifact.md](artifact.md).
