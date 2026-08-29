---
module: DenseMVS
module_version: 1.0.0
curated_at: 2026-08-11
---

# Tuning DenseMVS

1. `depth_map_completeness` — did the pixels survive at all?
2. `views_contributing` against `input_registered_images` — did every view work?
3. `fusion_ratio` — did the views agree with each other?
4. Only then `point_count`, which is mostly a function of `max_image_size`.

## Reference run

A controlled-rig capture, 8 contiguous images, `max_edge: 1024`, sparse model from
`SparseTriangulation` (4671 points, 8/8 registered), on one A6000 in a container:

| metric | 600 px no geom | 600 px | 1200 px |
|---|---:|---:|---:|
| `point_count` | 46 562 | 47 172 | 128 327 |
| `views_contributing` | 8 | 8 | 8 |
| `depth_map_completeness` | 0.717 | 0.679 | 0.650 |
| `fusion_ratio` | 33.1 | 30.9 | 32.2 |
| `mean_depth_confidence` | null | null | null |
| runtime | 31 s | 75 s | 131 s |

Two things to read off it.

**`geom_consistency` costs completeness and that is what it is for.** 0.717 → 0.679
is the ~5% of pixels that were photometrically plausible in one view and
geometrically impossible across the set. It also cost 44 s and gained 610 points.
The point count barely moves; the *quality* of the points does.

**Completeness falls as resolution rises.** 0.717 → 0.650 from 600 to 1200 px. More
pixels means finer detail per pixel and a harder consistency test, so the fraction
kept goes down while the absolute count goes up 2.7x. Never compare completeness
across different `max_image_size` values.

## The runtime knobs, in the order to reach for them

1. **`max_image_size`** — quadratic in both directions. 600 px to answer "does this
   pipeline work at all" in half a minute, then the real value.
2. **`geom_consistency: false`** — halves the time and is the only one of these
   that changes what the result *means*. A structural check, not a delivery
   setting.
3. **`num_samples`** — linear. 15 → 8 is a real saving with visible noise cost.
4. **`window_step: 2`** — roughly halves the correlation cost above ~1000 px, where
   neighbouring pixels are nearly redundant. Below that it just loses accuracy.

## Nothing survives the filters

`depth_map_completeness` near zero. Four causes, in the order worth checking:

**The poses are wrong.** Check this first, and check it before touching any filter.
Bad poses fail the *geometric* pass while sailing through the photometric one, so
the symptom is completeness that collapses when `geom_consistency` is on and
recovers when it is off. Turning it off is not a fix — it is switching off the
test that caught the problem. Bundle-adjust and re-run.

**The scene is low-texture.** Lower `filter_min_ncc` toward 0.05. Reflective,
transparent and untextured surfaces are where PatchMatch has nothing to correlate,
and no setting invents evidence — this is the case for `DenseVGGT` instead, whose
learned prior fills what it cannot verify.

**The baselines are small.** `filter_min_triangulation_angle` defaults to 3
degrees. A drone or handheld sequence with small steps between frames may need
1.0–1.5, and the depth it then keeps is softer along the ray.

**Each surface is seen by too few views.** Lower `filter_min_num_consistent` to 1.
That is the strictest filter in practice, and at 1 there is no multi-view
verification left — the result is closer to monocular depth than to MVS.

## Fusion produced nothing but completeness is healthy

Then the filters are fine and fusion is the problem: lower
`fusion_min_num_pixels`, or raise `fusion_max_depth_error` if the poses put each
view's surface at a slightly different depth. A `fusion_ratio` near 1 on a
successful run says the same thing more gently — the views are not agreeing, so
each is contributing its own copy.

## The cloud is noisy

Filter harder rather than sampling less — `stride`-style thinning removes points
uniformly, including good ones.

- `filter_min_ncc` to 0.2–0.3 on a well-textured scene.
- `filter_min_num_consistent` to 3–4 on a set with heavy overlap.
- `fusion_min_num_pixels` to 10 on a dense capture. This erodes thin structure and
  rim geometry, which is the trade.

## The cloud has holes where there is clearly surface

Expected, and read the images before tuning: the holes will be on specular
highlights, shadow, uniform paint, or glass. If they are somewhere textured and
well-seen, `filter_min_num_consistent` or
`filter_min_triangulation_angle` is the likely cause.

If the holes matter more than the verification does, `DenseVGGT` will fill them —
with a prediction rather than a measurement, which
[SKILL.md](SKILL.md#measured-against-densevggt-same-scene-same-poses) quantifies.
