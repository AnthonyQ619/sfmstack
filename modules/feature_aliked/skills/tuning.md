---
module: FeatureDetectionALIKED
module_version: 1.0.0
curated_at: 2026-08-08
---

# Tuning FeatureDetectionALIKED

## The scale trap, first

`detection_threshold` defaults to **0.2**. SuperPoint's defaults to **0.0005**.

They are not on the same scale and there is no conversion. Setting SuperPoint's
value here disables the filter entirely (everything clears 0.0005); setting this
value there detects nothing. If you are A/B-ing the two detectors, leave both at
their own defaults rather than trying to "match" them.

## Which parameter is binding

`saturation` tells you, exactly as with SuperPoint:

- **near 1.0** → the cap binds; raise `max_keypoints` for more.
- **near 0** → `detection_threshold` or `nms_radius` binds; the cap is irrelevant.

## `variant`

The parameter with real range, and worth trying before touching thresholds.

| variant | when |
|---|---|
| `aliked-t16` | tiny; try when detection is the bottleneck and you can afford weaker descriptors |
| `aliked-n16` | default balance |
| `aliked-n32` | wider descriptor head; slower for a modest gain in discriminability |
| `aliked-n16rot` | trained with rotation augmentation — **the answer to in-plane rotation** |

`aliked-n16rot` is the reason to reach for ALIKED over SuperPoint on a capture
with roll: SuperPoint has no rotation handling at all, and this variant has it
trained in.

## `nms_radius`

Defaults to 2, tighter than SuperPoint's 4. That is part of why ALIKED gives
denser, better-localised detections — and part of why it can cluster more.

Raise to 4-6 when `spatial_coverage` is poor. As with SuperPoint, this is the
counter-intuitive direction: a *larger* suppression radius spreads the cap across
the frame rather than spending it on one region.

## `keypoints_min` below 150

1. **`detection_threshold`** toward 0.05. On ALIKED's scale — check you have not
   accidentally set SuperPoint's.
2. **`nms_radius`** to 1, which is the floor and gives the densest detections.
3. **`variant`** to `aliked-n32` if the frame is genuinely hard rather than empty.

## What to expect downstream

ALIKED's claim is localisation, so the metric to watch is not this module's at
all — it is `SparseTriangulation`'s `mean_reprojection_error` and
`BundleAdjustmentGlobal`'s `reprojection_error_after`.

If swapping SuperPoint → ALIKED does not lower those, ALIKED is not buying you
anything on this capture, and SuperPoint's stronger descriptors are the better
trade. Compare with `sfm_compare` on the two BA artifacts rather than on the
detector artifacts, which measure the wrong thing for this decision.

## A note on CPU

This Docker daemon cannot pass a GPU through (see `docs/design/DECISIONS.md`), so
timings observed here are CPU timings and are one to two orders of magnitude
slower than this module should be. The metrics are unaffected — inference is
deterministic and device-independent — but `expected_duration_s` is calibrated for
GPU and will read as wildly optimistic until the toolkit is installed.
