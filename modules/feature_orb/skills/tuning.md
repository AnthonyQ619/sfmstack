---
module: FeatureDetectionORB
module_version: 1.0.0
curated_at: 2026-08-07
---

# Tuning FeatureDetectionORB

Read `spatial_coverage` first, always. The keypoint count is capped by
construction and is nearly uninformative; coverage is what actually predicts
downstream behaviour.

## Reference run

A controlled-rig capture, 8 contiguous images, `max_edge: 1024`, defaults:

| metric | `suppression: none` | `suppression: ssc` |
|---|---:|---:|
| `keypoints_per_image` | 4096 | 4096 |
| `keypoints_min` | 4096 | 4096 |
| `saturation` | 1.0 | 1.0 |
| `spatial_coverage` | 0.734 | **0.850** |
| `suppression_ratio` | 1.0 | ~0.30 |

`suppression_ratio` of 0.30 means SSC chose 4096 from about 13600 detections —
that is `detect_multiplier: 4` doing its job. Near 1.0 it had nothing to choose
between.

## `spatial_coverage` below 0.35

The dominant ORB failure, and the reason SSC exists.

1. **`suppression: ssc`** if it is off. Free, and usually the whole fix.
2. **Raise `detect_multiplier`** to 5-6. SSC can only select from what was
   detected; with a multiplier of 1 there is nothing to choose between and
   suppression is a no-op. Watch `suppression_ratio` — near 1.0 means raise it.
3. **Lower `fast_threshold`** to reach flatter regions, which gives SSC candidates
   in the empty parts of the frame rather than more candidates in the busy parts.

## `keypoints_min` below 200

One frame is starved. In order:

- **`fast_threshold`** to 5-10. This is ORB's analogue of SIFT's
  `contrast_threshold` and the right knob for dim or low-contrast frames. Below
  about 5 you are detecting sensor noise, which matches confidently and wrongly.
- Check whether the frame is blurred or genuinely textureless. ORB degrades on low
  texture faster than SIFT — a frame SIFT handles may be one ORB cannot.

## `saturation` at 1.0

The cap is binding everywhere, which is normal for ORB — it is cheap enough to
detect far more than you want. Raising `max_keypoints` to 8192-16384 is nearly
free compared to the same change in SIFT.

But raising the cap **without** SSC mostly adds keypoints to the clusters that
already exist. Check `spatial_coverage` before and after; if it does not move, the
extra keypoints are not buying you geometry.

## `scale_factor` and `n_levels`

Raise `n_levels` (and lower `scale_factor` toward 1.1) when the capture has large
scale change — approaching or receding shots. 1.2 with 8 levels covers roughly a
4x scale range.

On a wide-baseline set this matters more than the keypoint cap does, and it is the
first thing to try before concluding ORB cannot handle the capture.

## `wta_k`

Leave at 2. Values of 3 and 4 produce descriptors that require `NORM_HAMMING2`;
the matchers here select the norm from the artifact's `binary` flag, which does
not distinguish the two, so 3 and 4 would be matched incorrectly. If you need
them, that is a change to `features/v1` (an additive `wta_k` array), not a
parameter you can safely set today.

## Downstream expectations

ORB feeding `FeatureMatchNN` on the reference scene gives ~200 verified matches
per pair at 0.86 inlier ratio, against ~467 at 0.96 for SIFT on the same images.
That is the honest cost: roughly half the matches at a noticeably lower inlier
ratio, for roughly a tenth of the detection time and much cheaper matching.

Whether that trade is right depends on whether matching or detection is your
bottleneck, and on whether the tracker's `long_track_fraction` survives it.

## `suppression_ratio` near 1.0

Spatial suppression kept nearly everything it was given, which means it did
nothing. Two different causes, and they need opposite responses:

- **The detector found fewer keypoints than `max_keypoints`.** There was nothing to
  suppress. `saturation` will be well below 1.0 and the fix is upstream — lower
  `fast_threshold`, raise `n_levels`, or accept that the scene is textureless.
- **SSC is off.** `use_ssc: false` makes this metric meaningless rather than
  informative; it will sit at 1.0 forever. Turn SSC on before reading it.

Read it beside `spatial_coverage`. A ratio near 1.0 with healthy coverage is fine:
the keypoints were already well spread. A ratio near 1.0 with poor coverage is the
one to act on.

## Metrics that mislead

`keypoints_per_image` is capped and will read exactly `max_keypoints` on almost any
real scene. It tells you the cap was reached, nothing more. `spatial_coverage` is
the metric with information in it.

`saturation` at 1.0 is normal for ORB, not a warning. It means the same thing as in
SIFT — the cap is binding — but ORB reaches it on scenes where SIFT would not.

`suppression_ratio` near 1.0 means suppression did nothing, which usually means
`detect_multiplier` is too low rather than that the image had few keypoints.
