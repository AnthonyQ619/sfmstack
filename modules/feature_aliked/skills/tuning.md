---
module: FeatureDetectionALIKED
module_version: 1.2.0
curated_at: 2026-09-02
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

**Until 1.2.0 only `aliked-n16` was actually usable.** The image baked one
checkpoint and the other three sent the container to the network at run time,
where it has none — so selecting any of them failed, and `aliked-n16rot` failed
on precisely the captures it exists for. All four are baked now. If you are
reading a run older than 1.2.0 that reports an ALIKED failure on a non-default
variant, that is this defect and not the capture.

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

The timings recorded here are CPU timings.

**The recorded timings may not describe your environment.** They were taken when
this stack could not reach a GPU, and GPU passthrough has since been observed
working -- a run of this module has failed with a CUDA out-of-memory error raised
inside the container, which is only possible with a device attached. So treat any
absolute number here as a lower bound on speed and nothing more, and check
`device` in the artifact's own note for what actually ran.

**Read cost as relative, not absolute.** What transfers is the shape: this stage
grows with the pair count, and the pair count grows with the square of the image
count under exhaustive pairing. What does not transfer is seconds on a machine
whose configuration changed under the file. A recorded wall-clock figure is a fact
about a host, and a skill file is the wrong place to keep one.

**The metrics are unaffected either way** -- inference is deterministic and
device-independent; only the timing and the `expected_duration_s` calibration
differ.
