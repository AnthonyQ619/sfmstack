---
module: FeatureDetectionSuperPoint
module_version: 1.0.0
curated_at: 2026-08-07
---

# Tuning FeatureDetectionSuperPoint

Three parameters that matter: `max_keypoints`, `detection_threshold`,
`nms_radius`. They interact, and which one is binding is the first thing to
establish — `saturation` tells you.

## Reference run

DTU scan1, 6 contiguous images, `max_edge: 640`, `max_keypoints: 1024`, run in a
container **on CPU** (see the note below):

| metric | value |
|---|---|
| `keypoints_per_image` | 1024 (capped) |
| `keypoints_min` | 1024 |
| `saturation` | 1.0 |
| `spatial_coverage` | **0.932** |
| `mean_score` | 0.0493 |
| runtime | 10.8 s for 6 images |

0.932 coverage is far above what SIFT reaches on the same scene, and it is the
main practical reason to use this detector — the detections are spread rather than
piled onto the strongest texture.

## Which parameter is binding

- **`saturation` near 1.0** → the cap binds. Raising `max_keypoints` yields more.
- **`saturation` near 0** → `detection_threshold` or `nms_radius` binds. Raising
  the cap does nothing; lower the threshold or the radius instead.

This is the same logic as SIFT's `saturation`, and the same mistake is available:
raising a cap that was never the constraint.

## `keypoints_min` below 150

One frame is starved.

1. **`detection_threshold`** toward 1e-4. The default of 5e-4 is already
   permissive, which is deliberate — it is set so that `max_keypoints` is normally
   what binds, and a scene where it is not is a scene worth looking at.
2. **`nms_radius`** down to 2-3. On a small object filling little of the frame, a
   radius of 4 suppresses genuine neighbouring detections.
3. Check the frame is not simply blurred. SuperPoint degrades gracefully on blur —
   it returns fewer, lower-scoring detections rather than noise — so a low
   `mean_score` alongside a low count is a real signal about the image.

## `spatial_coverage` below 0.35

Rare with this detector, and when it happens the fix is the opposite of the
intuitive one: **raise** `nms_radius` to 6-8. A larger suppression radius forces
the cap to be spent across the frame instead of on a cluster.

Lowering `detection_threshold` also helps by producing candidates in flatter
regions, but only if the cap is not already binding — otherwise the new weak
detections lose to the existing strong ones.

## `max_keypoints`

2048 (default) ≈ 4096 in SIFT. Raise to 4096 when the tracker's
`long_track_fraction` is low and you have established the cap is binding.

Returns fall off faster than with SIFT, because the heatmap NMS already removed
the redundant candidates — the extra detections come from genuinely lower-scoring
regions. Watch `mean_score`: a sharp drop when raising the cap means the extra
keypoints are marginal.

## `resize_long_edge`

Leave unset by default. SuperPoint was trained around 480-640px and its detections
do change with resolution, but coordinates are returned in scene pixels either way,
so on a normally-sized capture the only reason to set it is inference cost.

**It resizes in both directions**, and the upward direction does not do what it
sounds like it does. Upsampling a heavily-downscaled capture — the obvious move when
the loader reported a heavy downscale and the detector looks starved — was measured
to *reduce* the keypoint count by low double-digit percent, not raise it. The reason
is that `nms_radius` and `detection_threshold` are both denominated at inference
resolution: stretch the image and the same real structure spans more pixels, so a
fixed-radius suppression removes relatively more of it. `mean_score` and coverage
barely moved, which is the signature of "the same structure, sampled differently"
rather than "new detail found".

So: upsampling here is not the answer to a starved capture. The pixels the loader
threw away are gone, and interpolation does not bring them back — if the capture is
genuinely short of resolution, the fix belongs at the loader, before the scene was
built. If you do upsample anyway, raise `nms_radius` with it or the two changes
fight each other.

Either direction costs localisation precision. Detections found at 640px and
rescaled to 1600px carry the precision of 640px, which shows up as higher
reprojection error two stages later; detections found on an upsample carry the
precision of the original pixels no matter what sub-pixel refinement reports.

*This used to be downscale-only, and a value above the scene's resolution was
silently ignored — while provenance recorded it as applied. If you are reading an
artifact produced before this module's 1.1.0, a large `resize_long_edge` in its
parameters may not have run.*

## A note on CPU

The reference run above is on CPU because this Docker daemon cannot pass a GPU
through (see `docs/design/DECISIONS.md`). 10.8s for 6 images at 640px is roughly
1.8s per image; on GPU expect one to two orders of magnitude better.

Everything about the *metrics* is unaffected — the model is deterministic in
`inference_mode` and produces identical output on either device. Only the timing
and the `expected_duration_s` calibration differ.
